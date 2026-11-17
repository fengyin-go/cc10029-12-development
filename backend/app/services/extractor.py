"""数据提取 DAG 图服务：生成节点、边示例结构与流转规则。

同时维护模板解析记录台账：数据提取读取受控模板版本数据集生成解析记录，
解析记录只能引用当前团队有权使用的模板版本，且拒绝生成重复结果。
"""
from __future__ import annotations

import datetime
from typing import Any

from app.services.template_version import VERSION_MODULE, TemplateVersionService
from app.store import store

MODULE = "extractor"
PARSE_MODULE = "extractor_parse"
REQUIRED_FIELDS = ["模板编号", "模板名称", "输入URL"]
STATUS_ORDER = ["草稿", "待校验", "已启用", "已停用"]
ACTION_RULES = {"提交校验": "待校验", "启用配置": "已启用", "停用配置": "已停用"}
NEGATIVE_ACTIONS = ["停用配置"]

# 模板解析记录台账字段：引用受控模板版本数据集的处理结果
PARSE_FIELDS = ["记录编号", "模板编号", "模板名称", "版本号", "适用站点", "作者来源", "当前作者", "共享范围", "责任边界", "使用团队", "解析时间"]

version_service = TemplateVersionService()


def csv_cell(value: Any) -> str:
    text = str(value) if value is not None else ""
    if text and text[0] in "=+-@":
        text = "'" + text
    return '"' + text.replace('"', '""') + '"'


class ExtractorService:
    def get_graph(self) -> dict[str, Any]:
        rows = store.rows(MODULE)
        nodes: list[dict] = []
        edges: list[dict] = []
        for i, row in enumerate(rows):
            nodes.append({"id": int(row.get("id", i+1)), "name": str(row.get(list(row.keys())[1] if len(row)>1 else "name", "")), "status": str(row.get("status", STATUS_ORDER[0])),
                          **{k: row[k] for k in row if k not in ("id","status","pending","abnormal")}})
        for i in range(len(nodes)-1):
            edges.append({"from": nodes[i]["id"], "to": nodes[i+1]["id"], "label": "依赖"})
        return {"nodes": nodes, "edges": edges}

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [f for f in REQUIRED_FIELDS if not str(values.get(f) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(r.get("id",0)) for r in rows), default=0) + 1}
        entry.update({f: values.get(f) for f in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"提取模板 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于数据提取可执行范围"
        target = ACTION_RULES[action]
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"提取模板已{action}"

    def raw_data(self) -> tuple[list[dict], list[dict]]:
        g = self.get_graph()
        return g["nodes"], g["edges"]

    # ---------- 模板解析记录台账 ----------
    def list_parse_records(
        self,
        *,
        filters: dict[str, str] | None = None,
        page: int = 1,
        size: int = 200,
    ) -> tuple[list[dict[str, Any]], int]:
        """模板解析记录台账：受控模板版本数据集的处理结果会反映到这里。"""
        rows = list(store.rows(PARSE_MODULE))
        for field, expected in (filters or {}).items():
            rows = [row for row in rows if expected.casefold() in str(row.get(field, "")).casefold()]
        total = len(rows)
        start = (page - 1) * size
        return rows[start:start + size], total

    def generate_parse_records(self, account: Any = None, team: Any = None) -> tuple[list[dict[str, Any]], list[tuple[str, str]], int]:
        """读取受控模板版本数据集生成模板解析记录。

        解析记录只能引用当前团队有权使用的模板版本；重复生成会被拒绝。
        返回 (新建记录, 被拒绝的重复键, 当前团队有权使用的版本数)。
        """
        account, team = version_service.resolve_identity(account, team)
        usable = [
            row for row in store.rows(VERSION_MODULE)
            if version_service.can_use(row, account, team)
        ]
        existing = {
            (str(row.get("模板编号")), str(row.get("版本号")), str(row.get("使用团队")))
            for row in store.rows(PARSE_MODULE)
        }
        created: list[dict[str, Any]] = []
        duplicates: list[tuple[str, str]] = []
        next_id = max((int(row.get("id", 0)) for row in store.rows(PARSE_MODULE)), default=0) + 1
        next_seq = max(
            (int(str(row.get("记录编号", "PARSE-0000")).removeprefix("PARSE-")) for row in store.rows(PARSE_MODULE)
             if str(row.get("记录编号", "")).removeprefix("PARSE-").isdigit()),
            default=0,
        ) + 1
        today = datetime.date.today().isoformat()
        for row in usable:
            key = (str(row.get("模板编号")), str(row.get("版本号")), team)
            if key in existing:
                duplicates.append((key[0], key[1]))
                continue
            record: dict[str, Any] = {
                "id": next_id,
                "记录编号": f"PARSE-{next_seq:04d}",
                "模板编号": row.get("模板编号"),
                "模板名称": row.get("模板名称"),
                "版本号": row.get("版本号"),
                "适用站点": row.get("适用站点"),
                "作者来源": row.get("作者来源"),
                "当前作者": row.get("当前作者"),
                "共享范围": row.get("共享范围"),
                "责任边界": row.get("责任边界"),
                "使用团队": team,
                "解析时间": today,
                "status": "已生成",
                "pending": False,
                "abnormal": False,
            }
            next_id += 1
            next_seq += 1
            existing.add(key)
            created.append(record)
        store.rows(PARSE_MODULE).extend(created)
        return created, duplicates, len(usable)
