"""受控模板版本数据集：按作者来源与适用站点计算授权范围，落实归属、权限与幂等规则。

规则摘要：
- 草稿、共享（共享范围）与已启用版本遵守同一归属规则；
- 数据集必须同时记录作者来源和适用站点，缺少授权关系的模板不能进入共享范围；
- 作者变更后历史版本仍归原作者只读，新版本只能由当前作者或授权管理员修改；
- 发布中转移作者出现两个维护者时，最终只有一个带责任边界的已发布版本可读；
- 模板市场只允许本团队维护，其他账户只能查看；
- 重复提交只写入一份，模板市场拒绝重复写入；
- 模板市场沿用既有字段名，受控模板版本数据集新增字段只追加。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MARKET_MODULE = "template"
VERSION_MODULE = "template_version"

# 模板市场既有字段名（沿用，不更名、不重排）
BASE_FIELDS = ["模板编号", "模板名称", "适用站点", "站点类型", "提取逻辑", "内置规则", "使用次数", "作者来源"]
# 受控模板版本数据集新增字段（只追加在既有字段之后）
EXTRA_FIELDS = ["版本号", "共享范围", "授权团队", "授权管理员", "当前作者", "原作者", "责任边界", "授权状态", "历史版本", "可读"]
LIST_FIELDS = BASE_FIELDS + EXTRA_FIELDS

REQUIRED_FIELDS = ["模板编号", "模板名称", "适用站点", "作者来源"]
STATUS_ORDER = ["草稿", "待校验", "已启用", "已停用"]
ACTION_RULES = {"提交校验": "待校验", "启用配置": "已启用", "停用配置": "已停用"}
NEGATIVE_ACTIONS = ["停用配置"]
SCOPE_CHOICES = ["私有", "团队共享", "站点共享"]

OWN_TEAM = "采集一组"  # 模板市场本团队：只允许本团队维护，其他账户只能查看
DEFAULT_ACCOUNT = "值班管理员"  # 缺省账户，同时是默认授权管理员
DEFAULT_ADMIN = "值班管理员"


def split_names(raw: Any) -> list[str]:
    """把逗号（中英文均可）分隔的名字串拆成列表。"""
    return [part.strip() for part in str(raw or "").replace("，", ",").split(",") if part.strip()]


def plain_text(value: Any) -> str:
    """把字段值规整成去空白的字符串；None 视为空串而不是 "None"。"""
    return str(value).strip() if value is not None else ""


def version_no(row: dict[str, Any]) -> int:
    text = str(row.get("版本号", "v0")).lstrip("vV")
    return int(text) if text.isdigit() else 0


class TemplateVersionService:
    """受控模板版本数据集的授权范围计算、归属流转与幂等写入。"""

    # ---------- 身份与权限 ----------
    def resolve_identity(self, account: Any, team: Any) -> tuple[str, str]:
        account_text = str(account or "").strip() or DEFAULT_ACCOUNT
        team_text = str(team or "").strip() or OWN_TEAM
        return account_text, team_text

    def market_maintainable(self, account: str, team: str) -> bool:
        """模板市场只允许本团队维护，其他账户只能查看。"""
        return team == OWN_TEAM or account == DEFAULT_ADMIN

    def can_edit_version(self, row: dict[str, Any], account: str) -> bool:
        """新版本只能由当前作者或授权管理员修改。"""
        return bool(account) and (
            account == plain_text(row.get("当前作者")) or account in split_names(row.get("授权管理员"))
        )

    def edit_permission(self, row: dict[str, Any], account: str, team: str) -> str:
        """按请求身份计算编辑权限，用于核对作者转移后历史版本与新版本的权限。"""
        if row.get("历史版本"):
            return "只读（历史版本归原作者）"
        if self.can_edit_version(row, account):
            return "可编辑"
        if team and team in split_names(row.get("授权团队")):
            return "只读（本团队）"
        return "仅查看"

    def can_use(self, row: dict[str, Any], account: str, team: str) -> bool:
        """数据提取只能引用当前团队有权使用的模板版本。"""
        if not row.get("可读", True):
            return False
        if row.get("授权状态") != "已授权":
            return False  # 缺少授权关系的模板不能进入共享范围，也不可被解析记录引用
        if row.get("共享范围") == "站点共享":
            return True
        if team and team in split_names(row.get("授权团队")):
            return True
        return self.can_edit_version(row, account)

    # ---------- 授权范围计算 ----------
    def compute_scope(self, row: dict[str, Any]) -> dict[str, Any]:
        """缺少授权关系（作者来源或授权团队为空）的模板不能进入共享范围。"""
        has_relation = bool(plain_text(row.get("作者来源"))) and bool(plain_text(row.get("授权团队")))
        if not has_relation:
            row["共享范围"] = "私有"
            row["授权状态"] = "未授权"
        else:
            if row.get("共享范围") not in SCOPE_CHOICES:
                row["共享范围"] = "团队共享"
            row["授权状态"] = "已授权"
        return row

    # ---------- 查询 ----------
    def list_versions(
        self,
        *,
        filters: dict[str, str] | None = None,
        account: Any = None,
        team: Any = None,
        page: int = 1,
        size: int = 200,
    ) -> tuple[list[dict[str, Any]], int]:
        account, team = self.resolve_identity(account, team)
        rows = list(store.rows(VERSION_MODULE))
        for field, expected in (filters or {}).items():
            rows = [row for row in rows if expected.casefold() in str(row.get(field, "")).casefold()]
        total = len(rows)
        start = (page - 1) * size
        return [self.with_permission(row, account, team) for row in rows[start:start + size]], total

    def with_permission(self, row: dict[str, Any], account: str, team: str) -> dict[str, Any]:
        item = dict(row)
        item["编辑权限"] = self.edit_permission(row, account, team)
        return item

    # ---------- 生成与提交（幂等） ----------
    def _next_id(self) -> int:
        return max((int(row.get("id", 0)) for row in store.rows(VERSION_MODULE)), default=0) + 1

    def _exists(self, code: str, version: str) -> bool:
        return any(
            str(row.get("模板编号")) == code and str(row.get("版本号")) == version
            for row in store.rows(VERSION_MODULE)
        )

    def generate_from_market(self, account: Any = None, team: Any = None) -> tuple[list[dict[str, Any]], list[str], str]:
        """计算模板版本授权范围并生成受控模板版本数据集；连续送交只会生成一份。"""
        account, team = self.resolve_identity(account, team)
        if not self.market_maintainable(account, team):
            return [], [], "模板市场只允许本团队维护，其他账户只能查看"
        created: list[dict[str, Any]] = []
        duplicates: list[str] = []
        for row in store.rows(MARKET_MODULE):
            code = plain_text(row.get("模板编号"))
            if not code:
                continue
            if self._exists(code, "v1"):
                duplicates.append(code)
                continue
            author = plain_text(row.get("作者来源"))
            entry: dict[str, Any] = {"id": self._next_id() + len(created)}
            entry.update({field: row.get(field) for field in BASE_FIELDS})
            entry.update({
                "版本号": "v1",
                "共享范围": "团队共享",
                "授权团队": OWN_TEAM,
                "授权管理员": DEFAULT_ADMIN,
                "当前作者": author,
                "原作者": author,
                "责任边界": author,
                "历史版本": False,
                "可读": True,
                "status": row.get("status", STATUS_ORDER[0]),
                "pending": True,
                "abnormal": False,
            })
            self.compute_scope(entry)
            created.append(entry)
        store.rows(VERSION_MODULE).extend(created)
        return created, duplicates, ""

    def submit_version(self, values: dict[str, Any], account: Any = None, team: Any = None) -> tuple[dict[str, Any] | None, str]:
        """送交一条受控模板版本记录；重复提交只写入一份，模板市场拒绝重复写入。"""
        account, team = self.resolve_identity(account, team)
        if not self.market_maintainable(account, team):
            return None, "模板市场只允许本团队维护，其他账户只能查看"
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}（受控模板版本数据集必须同时记录作者来源和适用站点）"
        code = str(values.get("模板编号")).strip()
        version = str(values.get("版本号") or "").strip() or self._next_version(code)
        if self._exists(code, version):
            return None, "重复提交被拒绝：受控模板版本数据集只写入一份，模板市场拒绝重复写入"
        author = str(values.get("作者来源")).strip()
        current_author = str(values.get("当前作者") or author).strip()
        entry: dict[str, Any] = {"id": self._next_id()}
        entry.update({field: values.get(field) for field in BASE_FIELDS})
        entry.update({
            "版本号": version,
            "共享范围": str(values.get("共享范围") or "团队共享"),
            "授权团队": str(values.get("授权团队") or OWN_TEAM),
            "授权管理员": str(values.get("授权管理员") or DEFAULT_ADMIN),
            "当前作者": current_author,
            "原作者": str(values.get("原作者") or author).strip(),
            "责任边界": current_author,
            "历史版本": False,
            "可读": True,
            "status": STATUS_ORDER[0],
            "pending": True,
            "abnormal": False,
        })
        self.compute_scope(entry)
        store.rows(VERSION_MODULE).append(entry)
        return entry, ""

    # ---------- 作者转移与权限冲突 ----------
    def _versions_of(self, code: str) -> list[dict[str, Any]]:
        return [row for row in store.rows(VERSION_MODULE) if str(row.get("模板编号")) == code]

    def _next_version(self, code: str) -> str:
        return f"v{max((version_no(row) for row in self._versions_of(code)), default=0) + 1}"

    def transfer_author(self, code: str, new_author: str, account: Any = None, team: Any = None) -> tuple[dict[str, Any] | None, str]:
        """作者转移：历史版本归原作者只读，新版本只能由当前作者或授权管理员修改。"""
        account, team = self.resolve_identity(account, team)
        if not self.market_maintainable(account, team):
            return None, "模板市场只允许本团队维护，其他账户只能查看"
        code = str(code or "").strip()
        new_author = str(new_author or "").strip()
        if not code:
            return None, "缺少模板编号，无法执行作者转移"
        if not new_author:
            return None, "缺少新作者，无法执行作者转移"
        versions = self._versions_of(code)
        if not versions:
            return None, f"采集模板 {code} 还没有受控版本，请先生成受控模板版本数据集"
        latest = max(versions, key=version_no)
        if plain_text(latest.get("当前作者")) == new_author:
            return None, f"新作者与当前作者「{new_author}」一致，无需转移"
        for row in versions:
            row["历史版本"] = True  # 历史版本仍归原作者只读
        entry: dict[str, Any] = {"id": self._next_id()}
        entry.update({field: latest.get(field) for field in BASE_FIELDS})
        entry.update({
            "版本号": self._next_version(code),
            "共享范围": latest.get("共享范围"),
            "授权团队": latest.get("授权团队"),
            "授权管理员": latest.get("授权管理员"),
            "当前作者": new_author,
            "原作者": latest.get("原作者"),
            "责任边界": new_author,
            "历史版本": False,
            "可读": True,
            "status": STATUS_ORDER[0],
            "pending": True,
            "abnormal": False,
        })
        self.compute_scope(entry)
        store.rows(VERSION_MODULE).append(entry)
        kept = self.resolve_conflicts(code)
        message = f"作者已转移：历史版本归原作者只读，新版本 {entry['版本号']} 只能由当前作者或授权管理员修改"
        if kept is not None:
            message += f"；检测到两个维护者权限冲突，仅保留带责任边界的已发布版本 {kept['版本号']}（责任边界 {kept['责任边界']}）可读"
        return entry, message

    def resolve_conflicts(self, code: str) -> dict[str, Any] | None:
        """发布中出现两个维护者造成权限冲突时，最终只有一个带责任边界的已发布版本可读。"""
        published = [row for row in self._versions_of(code) if row.get("status") == "已启用"]
        maintainers = {plain_text(row.get("责任边界")) for row in published}
        if len(maintainers) <= 1:
            return None
        current = plain_text(max(self._versions_of(code), key=version_no).get("当前作者"))
        kept: dict[str, Any] | None = None
        for row in sorted(published, key=version_no, reverse=True):
            if kept is None and plain_text(row.get("责任边界")) == current:
                row["可读"] = True
                kept = row
            else:
                row["可读"] = False
                row["abnormal"] = True
        if kept is None and published:
            kept = sorted(published, key=version_no, reverse=True)[0]
            kept["可读"] = True
        return kept

    # ---------- 版本状态流转（与模板市场同一归属规则） ----------
    def run_action(self, version_id: int, action: str, account: Any = None, team: Any = None) -> tuple[dict[str, Any] | None, str]:
        account, team = self.resolve_identity(account, team)
        entry: dict[str, Any] | None = None
        for row in store.rows(VERSION_MODULE):
            if int(row.get("id", 0)) == version_id:
                entry = row
                break
        if entry is None:
            return None, f"受控模板版本 {version_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于模板市场可执行范围"
        if not self.market_maintainable(account, team):
            return None, "模板市场只允许本团队维护，其他账户只能查看"
        if entry.get("历史版本"):
            return None, "历史版本归原作者只读，不能执行状态流转"
        if not self.can_edit_version(entry, account):
            return None, "新版本只能由当前作者或授权管理员修改"
        target = ACTION_RULES[action]
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        message = f"受控模板版本已{action}"
        if action == "启用配置":
            kept = self.resolve_conflicts(str(entry.get("模板编号")))
            if kept is not None:
                message += f"；权限冲突已裁决，仅已发布版本 {kept['版本号']}（责任边界 {kept['责任边界']}）可读"
        return entry, message
