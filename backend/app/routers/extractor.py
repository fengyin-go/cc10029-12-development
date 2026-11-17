"""数据提取 DAG 拓扑接口：返回节点、连线图结构。

模板解析记录台账接口也挂在这里：数据提取读取受控模板版本数据集生成解析记录，
只引用当前团队有权使用的模板版本，并拒绝生成重复结果。
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.schemas import ActionPayload, ActionResult, EntryPayload, PageResult
from app.services.extractor import PARSE_FIELDS, ExtractorService, csv_cell

router = APIRouter(prefix="/api/extractor", tags=["数据提取"])
service = ExtractorService()
LIST_FIELDS = ["模板编号", "模板名称", "输入URL", "字段映射", "清洗规则", "输出格式", "版本号", "生效批次"]
STATUSES = ["草稿", "待校验", "已启用", "已停用"]


@router.get("")
def get_graph() -> dict[str, Any]:
    """返回节点与边组成的 DAG 图数据。"""
    return service.get_graph()


# ---------- 模板解析记录台账（必须声明在 /{entry_id} 之前） ----------

@router.get("/parse-records", response_model=PageResult[dict])
def list_parse_records(
    request: Request,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=200, ge=1, le=1000),
) -> PageResult[dict]:
    """模板解析记录台账：受控模板版本数据集的处理结果会反映到本台账。"""
    filters = {
        key: value.strip()
        for key, value in request.query_params.items()
        if key in PARSE_FIELDS and value.strip()
    }
    items, total = service.list_parse_records(filters=filters, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/parse-records", response_model=ActionResult)
def generate_parse_records(payload: dict[str, Any] = Body(default_factory=dict)) -> ActionResult:
    """读取受控模板版本数据集生成模板解析记录；重复生成会被拒绝。"""
    created, duplicates, usable = service.generate_parse_records(
        account=payload.get("account"), team=payload.get("team"))
    if not created:
        if duplicates:
            return ActionResult(ok=False, message="数据提取拒绝生成重复结果：模板解析记录已存在，只保留一份")
        return ActionResult(ok=False, message="解析记录只能引用当前团队有权使用的模板版本，当前没有可引用的受控版本")
    message = f"已读取受控模板版本数据集，生成 {len(created)} 条模板解析记录"
    if duplicates:
        message += f"，数据提取拒绝生成重复结果 {len(duplicates)} 条"
    return ActionResult(ok=True, message=message)


@router.get("/export")
def export_entries() -> StreamingResponse:
    nodes, edges = service.raw_data()
    buf = io.StringIO(newline="")
    writer = csv.writer(buf)
    writer.writerow(["type", "id", "name", "from", "to", "label", "status"])
    for node in nodes:
        writer.writerow(["node", node.get("id",""), csv_cell(node.get("name","")), "", "", "", node.get("status","")])
    for edge in edges:
        writer.writerow(["edge", "", "", edge.get("from",""), edge.get("to",""), edge.get("label",""), ""])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=extractor.csv"})


@router.get("/{entry_id}")
def get_entry(entry_id: int) -> dict:
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"提取模板 {entry_id} 不存在")
    return entry


@router.post("")
def create_entry(payload: EntryPayload) -> ActionResult:
    entry_or_none, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="提取模板已登记", entry=entry_or_none)


@router.post("/{entry_id}/actions")
def run_action(entry_id: int, payload: ActionPayload) -> ActionResult:
    entry_or_none, message = service.run_action(entry_id, payload.action)
    if entry_or_none is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry_or_none)
