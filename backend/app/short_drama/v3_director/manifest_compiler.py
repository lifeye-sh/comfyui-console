"""Manifest 编译器：ProductionIntent → 现有生产链路（Task/Take）桥接。

契约见实施计划第 8 轮：
- 校验失败不创建任务；全部通过才进入现有 Task/Batch 创建模式
- 创建 V3ManifestItemTaskLink（幂等），输出回写 Take 后更新 ManifestItem 状态
- 保留无 Manifest 的 _prompt fallback（本模块不改动现有 production_service）
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Batch,
    GenerationType,
    Resource,
    ShotTaskLink,
    Task,
    V3ManifestItem,
    V3ManifestItemTaskLink,
)
from app.short_drama.v3_director import production_intent_service
from app.short_drama.v3_director.production_intent_service import (
    ManifestCompileError,
    ProductionIntent,
)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def shot_link_cls_query(db: Session, task_id: int) -> ShotTaskLink | None:
    return db.query(ShotTaskLink).filter(ShotTaskLink.task_id == task_id).first()


def compile_preview(
    db: Session,
    owner_id: int,
    project_id: int,
    manifest_id: int,
    generation_type_id: int,
    workflow_version_id: int | None,
    item_ids: list[int] | None = None,
    overrides: dict[str, Any] | None = None,
    per_item_overrides: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """编译预览：返回逐条 ProductionIntent，不创建任何任务。"""
    manifest, intents = production_intent_service.build_intents(
        db, owner_id, project_id, manifest_id, generation_type_id, workflow_version_id,
        item_ids, overrides, per_item_overrides,
    )
    return {
        "manifest_id": manifest.id,
        "manifest_version": manifest.version,
        "generation_type_id": generation_type_id,
        "workflow_version_id": workflow_version_id,
        "intents": [intent.out() for intent in intents],
        "total": len(intents),
        "error_count": sum(1 for i in intents if i.validation_errors),
        "ok_count": sum(1 for i in intents if not i.validation_errors),
    }


def create_tasks_from_manifest(
    db: Session,
    owner_id: int,
    project_id: int,
    manifest_id: int,
    generation_type_id: int,
    workflow_version_id: int | None,
    idempotency_key: str,
    submit: bool = True,
    item_ids: list[int] | None = None,
    overrides: dict[str, Any] | None = None,
    per_item_overrides: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """从已审批 Manifest 创建生产任务（幂等）。

    - 任何 intent 存在校验错误 → 整批拒绝（与现有 create_tasks 行为一致）
    - 幂等：相同 (owner, manifest_item, idempotency_key) 不重复创建
    - 创建 Batch/Task 与现有生产链路一致，另建 V3ManifestItemTaskLink
    """
    manifest, intents = production_intent_service.build_intents(
        db, owner_id, project_id, manifest_id, generation_type_id, workflow_version_id,
        item_ids, overrides, per_item_overrides,
    )
    errors = [issue for intent in intents for issue in intent.validation_errors]
    if errors:
        raise ManifestCompileError(
            "清单编译校验失败：" + "；".join(str(issue.get("message", "")) for issue in errors)
        )

    created_links: list[V3ManifestItemTaskLink] = []
    existing_links: list[V3ManifestItemTaskLink] = []
    pending: list[ProductionIntent] = []
    for intent in intents:
        key = f"manifest-item:{intent.manifest_item_id}:{idempotency_key}"
        existing = db.query(V3ManifestItemTaskLink).filter(
            V3ManifestItemTaskLink.owner_id == owner_id,
            V3ManifestItemTaskLink.idempotency_key == key,
        ).first()
        if existing:
            existing_links.append(existing)
        else:
            pending.append(intent)

    batch: Batch | None = None
    created_tasks: list[Task] = []
    if pending:
        generation_type = db.get(GenerationType, generation_type_id)
        batch = Batch(
            user_id=owner_id,
            name=f"V3 清单 v{manifest.version} 生产",
            generation_type_id=generation_type_id,
            workflow_version_id=pending[0].workflow_version_id,
            global_params={},
            source="short_drama_v3",
            submitted_at=_now() if submit else None,
        )
        db.add(batch)
        db.flush()
        for index, intent in enumerate(pending):
            task = Task(
                batch_id=batch.id,
                row_no=index,
                user_id=owner_id,
                generation_type_id=generation_type_id,
                workflow_version_id=intent.workflow_version_id,
                config_version_id=generation_type.published_config_version_id if generation_type else None,
                params=intent.params,
                status="PENDING" if submit else "DRAFT",
            )
            db.add(task)
            db.flush()
            created_tasks.append(task)
            key = f"manifest-item:{intent.manifest_item_id}:{idempotency_key}"
            link = V3ManifestItemTaskLink(
                owner_id=owner_id,
                project_id=project_id,
                manifest_item_id=intent.manifest_item_id,
                task_id=task.id,
                generation_type_id=generation_type_id,
                workflow_version_id=intent.workflow_version_id,
                link_status="linked",
                idempotency_key=key,
            )
            db.add(link)
            created_links.append(link)
            # 更新 ManifestItem 状态为 queued
            item = db.get(V3ManifestItem, intent.manifest_item_id)
            if item:
                item.status = "queued"
        db.add(AuditLog(
            user_id=owner_id,
            action="v3.manifest.compile",
            target_type="v3_generation_manifest",
            target_id=manifest.id,
            detail=f"items={len(pending)};batch={batch.id};submit={submit}",
        ))
        db.commit()
        db.refresh(batch)
        for link in created_links:
            db.refresh(link)
    else:
        db.commit()

    return {
        "manifest_id": manifest.id,
        "batch_id": batch.id if batch else None,
        "created_tasks": [t.id for t in created_tasks],
        "existing_task_ids": [link.task_id for link in existing_links],
        "created_link_ids": [link.id for link in created_links],
        "existing_link_ids": [link.id for link in existing_links],
        "created": len(created_tasks),
        "reused": len(existing_links),
        "submitted": submit,
    }


def manifest_task_links(
    db: Session,
    owner_id: int,
    project_id: int,
    manifest_id: int,
) -> list[dict[str, Any]]:
    """查看 Manifest 全部任务链接与任务状态。"""
    from app.models import V3GenerationManifest

    manifest = db.query(V3GenerationManifest).filter(
        V3GenerationManifest.id == manifest_id,
        V3GenerationManifest.project_id == project_id,
    ).first()
    if not manifest:
        raise ManifestCompileError("生成清单不存在")

    links = (
        db.query(V3ManifestItemTaskLink)
        .join(V3ManifestItem, V3ManifestItem.id == V3ManifestItemTaskLink.manifest_item_id)
        .filter(
            V3ManifestItemTaskLink.owner_id == owner_id,
            V3ManifestItem.manifest_id == manifest.id,
        )
        .order_by(V3ManifestItemTaskLink.id.desc())
        .all()
    )
    out: list[dict[str, Any]] = []
    for link in links:
        task = db.get(Task, link.task_id)
        out.append({
            "id": link.id,
            "manifest_item_id": link.manifest_item_id,
            "asset_stable_key": db.get(V3ManifestItem, link.manifest_item_id).asset_stable_key if link.manifest_item_id else None,
            "task_id": link.task_id,
            "task_status": task.status if task else None,
            "task_error": task.error if task else None,
            "output_resource_id": link.output_resource_id,
            "take_id": link.take_id,
            "generation_type_id": link.generation_type_id,
            "workflow_version_id": link.workflow_version_id,
            "link_status": link.link_status,
            "sync_error": link.sync_error,
            "created_at": link.created_at,
        })
    return out


def refresh_manifest_status(db: Session, owner_id: int, project_id: int, manifest_id: int) -> dict[str, Any]:
    """根据任务链接状态刷新 ManifestItem 状态（Take 回写后的状态同步）。

    状态迁移：
    - 任务成功且有 Take → item.status = "generated"
    - 任务失败 → item.status = "failed"
    - 任务运行中 → item.status = "queued" 保持
    """
    from app.models import ShotTaskLink, Take, V3GenerationManifest

    manifest = db.query(V3GenerationManifest).filter(
        V3GenerationManifest.id == manifest_id,
        V3GenerationManifest.project_id == project_id,
    ).first()
    if not manifest:
        raise ManifestCompileError("生成清单不存在")

    links = (
        db.query(V3ManifestItemTaskLink)
        .join(V3ManifestItem, V3ManifestItem.id == V3ManifestItemTaskLink.manifest_item_id)
        .filter(
            V3ManifestItemTaskLink.owner_id == owner_id,
            V3ManifestItem.manifest_id == manifest.id,
        )
        .all()
    )
    changed = 0
    summary = {"generated": 0, "failed": 0, "queued": 0}
    for link in links:
        item = db.get(V3ManifestItem, link.manifest_item_id)
        task = db.get(Task, link.task_id)
        if not item or not task:
            continue
        if task.status == "SUCCESS":
            # 关联输出：资产级清单项（无 Shot）直接关联输出 Resource；
            # 若任务挂有 ShotTaskLink，则复用现有 reconcile 生成 Take 并关联。
            from app.models import TaskResource, Take as TakeModel
            if link.output_resource_id is None:
                output_resource = (
                    db.query(Resource)
                    .join(TaskResource, TaskResource.resource_id == Resource.id)
                    .filter(
                        TaskResource.task_id == task.id,
                        TaskResource.role == "output",
                        Resource.deleted_at.is_(None),
                    )
                    .order_by(TaskResource.id)
                    .first()
                )
                if output_resource:
                    link.output_resource_id = output_resource.id
            shot_link = shot_link_cls_query(db, task.id)
            if shot_link is not None:
                try:
                    from app.short_drama.production_service import reconcile_task_outputs
                    takes = reconcile_task_outputs(db, task.id)
                except Exception:
                    takes = []
                if takes and link.take_id is None:
                    link.take_id = takes[0].id
                elif link.take_id is None:
                    any_take = db.query(TakeModel).filter(TakeModel.source_task_id == task.id).first()
                    if any_take:
                        link.take_id = any_take.id
            link.link_status = "synced"
            link.sync_error = ""
            if item.status != "generated":
                item.status = "generated"
                changed += 1
            summary["generated"] += 1
        elif task.status == "FAILED":
            link.link_status = "failed"
            link.sync_error = (task.error or "")[:4000]
            if item.status != "failed":
                item.status = "failed"
                changed += 1
            summary["failed"] += 1
        else:
            summary["queued"] += 1
    db.commit()
    return {
        "manifest_id": manifest.id,
        "changed_items": changed,
        "summary": summary,
    }
