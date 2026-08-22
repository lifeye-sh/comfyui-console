"""工作流服务增强：测试执行。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.comfy.client import ComfyUIClient
from app.comfy.prompt_builder import build_prompt, parse_size_value
from app.core.events import publish_task_event
from app.models import GenerationType, Node, Resource, Task, TaskResource, Workflow, WorkflowVersion
from app.schemas.schemas import WorkflowCreateIn, WorkflowVersionIn


def create_workflow(db: Session, body: WorkflowCreateIn, owner_id: Optional[int]) -> Workflow:
    if body.generation_type_id is not None:
        generation_type = db.get(GenerationType, body.generation_type_id)
        if not generation_type or generation_type.deleted_at is not None:
            raise ValueError("生成类型不存在")
        if generation_type.media_type != body.media_type:
            raise ValueError("工作流媒体类型与生成类型不一致")
    wf = Workflow(
        owner_id=owner_id,
        generation_type_id=body.generation_type_id,
        name=body.name,
        description=body.description,
        media_type=body.media_type,
        tags=body.tags,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return wf


def patch_workflow(db: Session, workflow: Workflow, name: Optional[str]) -> Workflow:
    if name is not None:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("工作流名称不能为空")
        workflow.name = cleaned_name
    db.commit()
    db.refresh(workflow)
    return workflow


def add_version(db: Session, workflow_id: int, body: WorkflowVersionIn) -> WorkflowVersion:
    wf = db.get(Workflow, workflow_id)
    if not wf:
        raise ValueError("工作流不存在")
    next_version = (wf.current_version_id and len(wf.versions) + 1) or 1
    v = WorkflowVersion(
        workflow_id=workflow_id,
        version=next_version,
        ui_json=body.ui_json,
        api_json=body.api_json,
        param_schema=body.param_schema,
        output_mapping=body.output_mapping,
    )
    db.add(v)
    db.flush()
    wf.current_version_id = v.id
    db.commit()
    db.refresh(v)
    return v


def list_workflows(
    db: Session,
    media_type: Optional[str] = None,
    generation_type_code: Optional[str] = None,
) -> list[Workflow]:
    """列出工作流；传入生成类型时严格限制为该类型自己的工作流。"""
    q = db.query(Workflow).filter(Workflow.status == "active")
    if media_type:
        q = q.filter(Workflow.media_type == media_type)

    if generation_type_code:
        gt = db.query(GenerationType).filter(GenerationType.code == generation_type_code).first()
        if not gt:
            return []
        q = q.filter(Workflow.generation_type_id == gt.id)

    return q.order_by(Workflow.id.desc()).all()


def get_version(db: Session, version_id: int) -> Optional[WorkflowVersion]:
    return db.get(WorkflowVersion, version_id)


def validate_task_params(
    db: Session,
    version: WorkflowVersion,
    params: dict,
    user_id: Optional[int] = None,
) -> tuple[dict, list[str]]:
    """Filter and validate task params against the selected workflow version."""
    from app.services.generation_type_service import get_select_options

    source = params if isinstance(params, dict) else {}
    clean: dict = {}
    errors: list[str] = []
    for spec in version.param_schema or []:
        if not isinstance(spec, dict):
            continue
        key = str(spec.get("key") or "").strip()
        if not key:
            continue
        value = source.get(key)
        if value in (None, "", []):
            if spec.get("required"):
                errors.append(f"缺少必填参数：{spec.get('label') or key}")
            continue
        kind = spec.get("type")
        if kind == "size":
            parsed_size = parse_size_value(value)
            if not parsed_size:
                errors.append(f"参数“{spec.get('label') or key}”不是有效尺寸")
                continue
            source_key = str(spec.get("options_from") or "")
            options = get_select_options(db, source_key) if source_key else []
            allowed_sizes = {
                parse_size_value(item.get("value")) for item in options if isinstance(item, dict)
            }
            allowed_sizes.discard(None)
            if allowed_sizes and parsed_size not in allowed_sizes:
                errors.append(f"参数“{spec.get('label') or key}”不是有效选项")
                continue
            value = f"{parsed_size[0]}x{parsed_size[1]}"
        if kind in {"int", "seed"} and (not isinstance(value, int) or isinstance(value, bool)):
            errors.append(f"参数“{spec.get('label') or key}”必须是整数")
            continue
        if kind in {"float", "slider"} and (not isinstance(value, (int, float)) or isinstance(value, bool)):
            errors.append(f"参数“{spec.get('label') or key}”必须是数字")
            continue
        if kind == "bool" and not isinstance(value, bool):
            errors.append(f"参数“{spec.get('label') or key}”必须是开关值")
            continue
        if kind in {"text", "textarea"} and not isinstance(value, str):
            errors.append(f"参数“{spec.get('label') or key}”必须是文本")
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if spec.get("min") is not None and value < spec["min"]:
                errors.append(f"参数“{spec.get('label') or key}”小于最小值")
                continue
            if spec.get("max") is not None and value > spec["max"]:
                errors.append(f"参数“{spec.get('label') or key}”大于最大值")
                continue
        if kind == "select":
            options = spec.get("options") or get_select_options(db, str(spec.get("options_from") or ""))
            allowed = [item.get("value") for item in options if isinstance(item, dict)]
            if allowed and value not in allowed:
                errors.append(f"参数“{spec.get('label') or key}”不是有效选项")
                continue
        if kind in {"image", "video", "audio"}:
            raw_ids = value if isinstance(value, list) else [value]
            if not spec.get("multiple") and len(raw_ids) > 1:
                errors.append(f"参数“{spec.get('label') or key}”只允许选择一个素材")
                continue
            max_items = int(spec.get("max_items") or 0)
            if max_items and len(raw_ids) > max_items:
                errors.append(f"参数“{spec.get('label') or key}”最多选择 {max_items} 个素材")
                continue
            resource_ids: list[int] = []
            invalid_media = False
            for raw_id in raw_ids:
                try:
                    resource_id = int(raw_id)
                except (TypeError, ValueError):
                    errors.append(f"参数“{spec.get('label') or key}”素材编号无效")
                    invalid_media = True
                    break
                resource = db.get(Resource, resource_id)
                if not resource or resource.deleted_at is not None or resource.media_type != kind:
                    errors.append(f"参数“{spec.get('label') or key}”素材不存在或类型不匹配")
                    invalid_media = True
                    break
                if user_id is not None and resource.owner_id not in (None, user_id) and resource.visibility != "public":
                    errors.append(f"参数“{spec.get('label') or key}”无权访问该素材")
                    invalid_media = True
                    break
                resource_ids.append(resource_id)
            if invalid_media:
                continue
            value = resource_ids if spec.get("multiple") else resource_ids[0]
        clean[key] = value

        # --- 遮罩参数校验：{key}__mask 引用一张带 alpha 通道的 PNG Resource ---
        if kind == "image":
            mask_key = f"{key}__mask"
            mask_value = source.get(mask_key)
            if mask_value in (None, "", 0):
                continue
            try:
                mask_rid = int(mask_value)
            except (TypeError, ValueError):
                errors.append(f"参数“{spec.get('label') or key}”的遮罩素材编号无效")
                continue
            if mask_rid <= 0:
                continue
            mask_resource = db.get(Resource, mask_rid)
            if not mask_resource or mask_resource.deleted_at is not None or mask_resource.media_type != "image":
                errors.append(f"参数“{spec.get('label') or key}”的遮罩素材不存在或不是图片")
                continue
            if user_id is not None and mask_resource.owner_id not in (None, user_id) and mask_resource.visibility != "public":
                errors.append(f"参数“{spec.get('label') or key}”的遮罩素材无权访问")
                continue
            clean[mask_key] = mask_rid
    return clean, errors


async def test_execute(db: Session, version_id: int, node_id: int, params: dict, user_id: Optional[int]) -> dict:
    """在指定节点用给定参数执行一次工作流版本，不经过队列。"""
    v = get_version(db, version_id)
    if not v:
        raise ValueError("工作流版本不存在")
    node = db.get(Node, node_id)
    if not node:
        raise ValueError("节点不存在")

    client = ComfyUIClient(node.id, node.base_url, node.ws_url)
    try:
        prompt = build_prompt(v.api_json, v.param_schema, params)
        client_id = f"console-test-v{version_id}-u{user_id}"
        resp = await client.post_prompt(prompt, client_id)
        prompt_id = resp["prompt_id"]

        # 轮询等待完成（最多 300 秒）
        for _ in range(300):
            await asyncio.sleep(1)
            hist = await client.get_history(prompt_id)
            entry = hist.get(prompt_id)
            if not entry:
                continue
            status = entry.get("status", {}) or {}
            if status.get("completed"):
                return {"ok": True, "prompt_id": prompt_id, "outputs": entry.get("outputs", {})}
            if status.get("status_str") == "error":
                return {"ok": False, "prompt_id": prompt_id, "error": str(status.get("messages"))}
        return {"ok": False, "prompt_id": prompt_id, "error": "测试执行超时"}
    finally:
        await client.aclose()
