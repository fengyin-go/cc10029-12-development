"""模板市场接口：维护采集模板，覆盖提交校验、启用配置、停用配置等动作。

受控模板版本数据集接口也挂在这里：计算授权范围、生成数据集、作者转移与版本流转，
全部沿用模板市场的受控权限（只允许本团队维护，其他账户只能查看）。
"""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.schemas import ActionPayload, ActionResult, EntryPayload, PageResult
from app.services.template import TemplateService
from app.services.template_version import LIST_FIELDS as VERSION_LIST_FIELDS
from app.services.template_version import TemplateVersionService

router = APIRouter(prefix="/api/template", tags=["模板市场"])

service = TemplateService()
version_service = TemplateVersionService()

LIST_FIELDS = ["模板编号", "模板名称", "适用站点", "站点类型", "提取逻辑", "内置规则", "使用次数", "作者来源"]
STATUSES = ["草稿", "待校验", "已启用", "已停用"]


def query_filters(request: Request) -> dict[str, str]:
    """只接受当前模块声明过的字段，忽略分页等保留参数。"""
    return {
        key: value.strip()
        for key, value in request.query_params.items()
        if key in LIST_FIELDS and value.strip()
    }


def version_filters(request: Request) -> dict[str, str]:
    """受控模板版本数据集沿用模板市场既有字段名，新增字段只追加，筛选同样放行。"""
    return {
        key: value.strip()
        for key, value in request.query_params.items()
        if key in VERSION_LIST_FIELDS and value.strip()
    }


# ---------- 受控模板版本数据集（必须声明在 /{entry_id} 之前） ----------

@router.get("/versions", response_model=PageResult[dict])
def list_versions(
    request: Request,
    account: str | None = Query(default=None, description="当前账户，缺省为值班管理员"),
    team: str | None = Query(default=None, description="当前团队，缺省为模板市场本团队"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=200, ge=1, le=1000),
) -> PageResult[dict]:
    """按站点等条件查看模板作者、版本和共享范围，并按当前身份给出编辑权限。"""
    items, total = version_service.list_versions(
        filters=version_filters(request), account=account, team=team, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/versions/generate", response_model=ActionResult)
def generate_versions(payload: dict[str, Any] = Body(default_factory=dict)) -> ActionResult:
    """计算模板版本授权范围并生成受控模板版本数据集；连续送交只会生成一份。"""
    created, duplicates, error = version_service.generate_from_market(
        account=payload.get("account"), team=payload.get("team"))
    if error:
        return ActionResult(ok=False, message=error)
    if not created:
        return ActionResult(ok=False, message="受控模板版本数据集已存在，模板市场拒绝重复写入")
    message = f"已计算模板版本授权范围并生成 {len(created)} 份受控模板版本数据集"
    if duplicates:
        message += f"，拒绝重复写入 {len(duplicates)} 份"
    return ActionResult(ok=True, message=message)


@router.post("/versions", response_model=ActionResult)
def submit_version(payload: dict[str, Any] = Body(default_factory=dict)) -> ActionResult:
    """送交一条受控模板版本记录；重复提交只写入一份，模板市场拒绝重复写入。"""
    entry, error = version_service.submit_version(
        payload, account=payload.get("account"), team=payload.get("team"))
    if error:
        return ActionResult(ok=False, message=error)
    return ActionResult(ok=True, message="受控模板版本数据集已写入", entry=entry)


@router.post("/versions/transfer", response_model=ActionResult)
def transfer_author(payload: dict[str, Any] = Body(default_factory=dict)) -> ActionResult:
    """作者转移：历史版本归原作者只读，新版本只能由当前作者或授权管理员修改。"""
    entry, message = version_service.transfer_author(
        str(payload.get("模板编号", "")), str(payload.get("新作者", "")),
        account=payload.get("account"), team=payload.get("team"))
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/versions/{version_id}/actions", response_model=ActionResult)
def run_version_action(version_id: int, payload: dict[str, Any] = Body(default_factory=dict)) -> ActionResult:
    """受控版本状态流转，与模板市场同一归属规则；发布会裁决维护者权限冲突。"""
    entry, message = version_service.run_action(
        version_id, str(payload.get("action", "")).strip(),
        account=payload.get("account"), team=payload.get("team"))
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


# ---------- 模板市场既有接口 ----------


@router.get("", response_model=PageResult[dict])
def list_entries(
    request: Request,
    keyword: str | None = Query(default=None, description="按模板编号检索"),
    status: str | None = Query(default=None, description="草稿、待校验、已启用、已停用"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> PageResult[dict]:
    """按页面字段、模板编号关键字与状态过滤模板市场列表。"""
    items, total = service.list_entries(
        filters=query_filters(request), keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries(
    request: Request,
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> StreamingResponse:
    """下载当前筛选条件下的 UTF-8 CSV；必须声明在 /{entry_id} 之前。"""
    items, _ = service.list_entries(
        filters=query_filters(request), keyword=keyword, status=status, page=1, size=1000000)
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["id", *LIST_FIELDS, "status"])
    for item in items:
        row = []
        for value in [item.get("id"), *(item.get(field, "") for field in LIST_FIELDS), item.get("status", "")]:
            text = "" if value is None else str(value)
            row.append("'" + text if text.startswith(("=", "+", "-", "@")) else text)
        writer.writerow(row)
    return StreamingResponse(
        iter([output.getvalue()]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="template.csv"'})


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条采集模板明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"采集模板 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: dict[str, object]) -> ActionResult:
    """登记一条采集模板，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="采集模板已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: ActionPayload) -> ActionResult:
    """对单条采集模板执行提交校验、启用配置、停用配置；不允许的动作会被拦下并说明原因。"""
    entry, message = service.run_action(entry_id, payload.action.strip())
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
