"""工作流服务增强：测试执行。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.comfy.client import ComfyUIClient
from app.comfy.prompt_builder import build_prompt
from app.core.events import publish_task_event
from app.models import GenerationType, Node, Resource, Task, TaskResource, Workflow, WorkflowVersion
from app.schemas.schemas import WorkflowCreateIn, WorkflowVersionIn


def create_workflow(db: Session, body: WorkflowCreateIn, owner_id: Optional[int]) -> Workflow:
    if body.generation_type_id is not None:
        generation_type = db.get(GenerationType, body.generation_type_id)
        if not generation_type:
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
