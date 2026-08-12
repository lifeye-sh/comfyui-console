"""素材文件夹、任务结果自动归档与目录移动。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import GenerationType, Resource, ResourceFolder, Task, TaskResource

CHINA_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")


def _find_system(db: Session, owner_id: int, system_key: str) -> ResourceFolder | None:
    return db.query(ResourceFolder).filter(
        ResourceFolder.owner_id == owner_id,
        ResourceFolder.system_key == system_key,
        ResourceFolder.deleted_at.is_(None),
    ).first()


def ensure_unorganized_folder(db: Session, owner_id: int) -> ResourceFolder:
    folder = _find_system(db, owner_id, "task_results") or _find_system(db, owner_id, "unorganized")
    if folder:
        folder.name = "任务结果"
        folder.folder_type = "task_results"
        folder.system_key = "task_results"
        return folder
    folder = ResourceFolder(owner_id=owner_id, name="任务结果", folder_type="task_results", system_key="task_results")
    db.add(folder)
    db.flush()
    return folder


def ensure_upload_folder(db: Session, owner_id: int) -> ResourceFolder:
    folder = _find_system(db, owner_id, "uploads")
    if folder:
        return folder
    folder = ResourceFolder(owner_id=owner_id, name="上传素材", folder_type="uploads", system_key="uploads")
    db.add(folder)
    db.flush()
    return folder


def ensure_task_result_folder(
    db: Session,
    owner_id: int,
    task_id: int,
    task_type: str,
    created_at: datetime | None = None,
) -> ResourceFolder:
    root = ensure_unorganized_folder(db, owner_id)
    local_time = created_at or datetime.now(CHINA_TIMEZONE)
    if local_time.tzinfo:
        local_time = local_time.astimezone(CHINA_TIMEZONE)
    date_text = local_time.strftime("%Y-%m-%d")
    date_key = f"task_results:{date_text}"
    date_folder = _find_system(db, owner_id, date_key)
    if not date_folder:
        date_folder = db.query(ResourceFolder).filter(
            ResourceFolder.owner_id == owner_id, ResourceFolder.parent_id == root.id,
            ResourceFolder.name == date_text, ResourceFolder.folder_type == "date",
            ResourceFolder.deleted_at.is_(None),
        ).first()
        if date_folder:
            date_folder.system_key = date_key
    if not date_folder:
        date_folder = ResourceFolder(
            owner_id=owner_id, parent_id=root.id, name=date_text,
            folder_type="date", system_key=date_key,
        )
        db.add(date_folder)
        db.flush()
    task_key = f"{date_key}:task:{task_id}"
    task_folder = _find_system(db, owner_id, task_key)
    if not task_folder:
        task_folder = ResourceFolder(
            owner_id=owner_id, parent_id=date_folder.id,
            name=f"{task_id}-{task_type or '未知类型'}",
            folder_type="task", system_key=task_key,
        )
        db.add(task_folder)
        db.flush()
    return task_folder


def tree(db: Session, owner_id: int) -> list[dict]:
    folders = db.query(ResourceFolder).filter(
        ResourceFolder.owner_id == owner_id, ResourceFolder.deleted_at.is_(None)
    ).order_by(ResourceFolder.sort_order, ResourceFolder.name).all()
    resource_stats = db.query(Resource.folder_id, Resource.media_type, func.count(Resource.id)).filter(
        Resource.owner_id == owner_id, Resource.deleted_at.is_(None)
    ).group_by(Resource.folder_id, Resource.media_type).all()
    counts: dict[int | None, int] = {}
    media_types: dict[int | None, list[str]] = {}
    for folder_id, media_type, count in resource_stats:
        counts[folder_id] = counts.get(folder_id, 0) + count
        media_types.setdefault(folder_id, []).append(media_type)
    nodes = {f.id: {"id": f.id, "parent_id": f.parent_id, "name": f.name, "folder_type": f.folder_type,
                    "system_key": f.system_key, "resource_count": counts.get(f.id, 0),
                    "media_types": media_types.get(f.id, []), "children": []} for f in folders}
    roots: list[dict] = []
    for folder in folders:
        node = nodes[folder.id]
        if folder.parent_id in nodes:
            nodes[folder.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


def create(db: Session, owner_id: int, name: str, parent_id: int | None) -> ResourceFolder:
    clean = name.strip()
    if not clean:
        raise ValueError("文件夹名称不能为空")
    if parent_id:
        parent = owned_folder(db, owner_id, parent_id)
        if parent.folder_type != "normal":
            raise ValueError("系统文件夹下不能新建普通文件夹")
    duplicate = db.query(ResourceFolder).filter(
        ResourceFolder.owner_id == owner_id, ResourceFolder.parent_id == parent_id,
        ResourceFolder.name == clean, ResourceFolder.deleted_at.is_(None),
    ).first()
    if duplicate:
        raise ValueError("同级文件夹名称已存在")
    folder = ResourceFolder(owner_id=owner_id, parent_id=parent_id, name=clean, folder_type="normal")
    db.add(folder); db.commit(); db.refresh(folder)
    return folder


def owned_folder(db: Session, owner_id: int, folder_id: int) -> ResourceFolder:
    folder = db.get(ResourceFolder, folder_id)
    if not folder or folder.owner_id != owner_id or folder.deleted_at:
        raise ValueError("文件夹不存在")
    return folder


def _descendant_ids(db: Session, owner_id: int, folder_id: int) -> set[int]:
    children = db.query(ResourceFolder).filter(ResourceFolder.owner_id == owner_id, ResourceFolder.deleted_at.is_(None)).all()
    by_parent: dict[int | None, list[int]] = {}
    for item in children:
        by_parent.setdefault(item.parent_id, []).append(item.id)
    result, stack = set(), [folder_id]
    while stack:
        current = stack.pop()
        for child_id in by_parent.get(current, []):
            if child_id not in result:
                result.add(child_id); stack.append(child_id)
    return result


def update(db: Session, owner_id: int, folder_id: int, name: str | None, parent_id: int | None, move: bool) -> ResourceFolder:
    folder = owned_folder(db, owner_id, folder_id)
    if folder.folder_type != "normal":
        raise ValueError("系统文件夹不能修改")
    if name is not None:
        clean = name.strip()
        if not clean: raise ValueError("文件夹名称不能为空")
        folder.name = clean
    if move:
        if parent_id == folder.id or (parent_id and parent_id in _descendant_ids(db, owner_id, folder.id)):
            raise ValueError("不能移动到自身或子文件夹")
        if parent_id:
            target = owned_folder(db, owner_id, parent_id)
            if target.folder_type != "normal": raise ValueError("不能移动到系统文件夹")
        folder.parent_id = parent_id
    duplicate = db.query(ResourceFolder).filter(
        ResourceFolder.owner_id == owner_id, ResourceFolder.parent_id == folder.parent_id,
        ResourceFolder.name == folder.name, ResourceFolder.id != folder.id,
        ResourceFolder.deleted_at.is_(None),
    ).first()
    if duplicate: raise ValueError("同级文件夹名称已存在")
    db.commit(); db.refresh(folder)
    return folder


def move_resources(db: Session, owner_id: int, resource_ids: list[int], folder_id: int | None) -> int:
    if folder_id is not None:
        owned_folder(db, owner_id, folder_id)
    resources = db.query(Resource).filter(
        Resource.id.in_(resource_ids), Resource.owner_id == owner_id, Resource.deleted_at.is_(None)
    ).all()
    if len(resources) != len(set(resource_ids)): raise ValueError("部分素材不存在或无权限")
    for resource in resources: resource.folder_id = folder_id
    db.commit()
    return len(resources)


def delete(db: Session, owner_id: int, folder_id: int) -> int:
    folder = owned_folder(db, owner_id, folder_id)
    if folder.folder_type != "normal":
        raise ValueError("系统文件夹不能删除")
    folder_ids = {folder.id, *_descendant_ids(db, owner_id, folder.id)}
    resources = db.query(Resource).filter(
        Resource.owner_id == owner_id, Resource.folder_id.in_(folder_ids), Resource.deleted_at.is_(None)
    ).all()
    for resource in resources:
        resource.folder_id = ensure_upload_folder(db, owner_id).id
    now = datetime.now(CHINA_TIMEZONE)
    db.query(ResourceFolder).filter(ResourceFolder.id.in_(folder_ids)).update(
        {ResourceFolder.deleted_at: now}, synchronize_session=False
    )
    db.commit()
    return len(resources)


def archive_existing(db: Session) -> int:
    changed = 0
    # 所有任务输出（包括已处于旧图片/视频目录中的素材）迁入对应任务目录。
    links = db.query(TaskResource).filter(TaskResource.role == "output").order_by(TaskResource.id).all()
    linked_resource_ids: set[int] = set()
    for link in links:
        resource = db.get(Resource, link.resource_id)
        task = db.get(Task, link.task_id)
        if not resource or not task or not resource.owner_id or resource.deleted_at:
            continue
        generation_type = db.get(GenerationType, task.generation_type_id) if task.generation_type_id else None
        folder = ensure_task_result_folder(
            db, resource.owner_id, task.id, generation_type.name if generation_type else "未知类型",
            task.finished_at or resource.created_at,
        )
        linked_resource_ids.add(resource.id)
        if resource.folder_id != folder.id:
            resource.folder_id = folder.id
            changed += 1
    # 非任务素材若未归档或仍在旧媒体目录，统一归入“上传素材”。
    old_media_ids = {folder.id for folder in db.query(ResourceFolder).filter(ResourceFolder.folder_type == "media").all()}
    for resource in db.query(Resource).filter(Resource.owner_id.is_not(None), Resource.deleted_at.is_(None)).all():
        if resource.id in linked_resource_ids:
            continue
        if resource.folder_id is None or resource.folder_id in old_media_ids:
            upload_folder = ensure_upload_folder(db, resource.owner_id)
            if resource.folder_id != upload_folder.id:
                resource.folder_id = upload_folder.id
                changed += 1
    # 清理已搬空的旧图片/视频/音频系统目录。
    old_media_folders = db.query(ResourceFolder).filter(ResourceFolder.folder_type == "media", ResourceFolder.deleted_at.is_(None)).all()
    old_media_changed = False
    for folder in old_media_folders:
        if not db.query(Resource).filter(Resource.folder_id == folder.id, Resource.deleted_at.is_(None)).first():
            folder.deleted_at = datetime.now(CHINA_TIMEZONE)
            old_media_changed = True
    if old_media_changed:
        db.flush()
    # 删除旧规则遗留的空日期目录。
    old_date_folders = db.query(ResourceFolder).filter(
        ResourceFolder.folder_type == "date",
        ResourceFolder.system_key.like("unorganized:%"),
        ResourceFolder.deleted_at.is_(None),
    ).all()
    for folder in old_date_folders:
        has_resources = db.query(Resource).filter(Resource.folder_id == folder.id, Resource.deleted_at.is_(None)).first()
        has_children = db.query(ResourceFolder).filter(
            ResourceFolder.parent_id == folder.id, ResourceFolder.deleted_at.is_(None)
        ).first()
        if not has_resources and not has_children:
            folder.deleted_at = datetime.now(CHINA_TIMEZONE)
    if changed: db.commit()
    else: db.commit()
    return changed
