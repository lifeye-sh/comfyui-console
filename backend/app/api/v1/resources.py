"""资源路由 /api/v1/resources。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.core.deps import CurrentUser, DBSession
from app.models import Batch, GenerationType, Resource, Task, TaskResource
from app.services import resource_service
from app.storage.local_fs import get_storage
from app.schemas.schemas import ResourceOut, ResourcePatchIn
from pydantic import BaseModel

router = APIRouter(prefix="/resources", tags=["resources"])


class ResourceMoveIn(BaseModel):
    folder_id: int | None = None


class ResourceBatchMoveIn(BaseModel):
    resource_ids: list[int]
    folder_id: int | None = None


@router.post("", response_model=ResourceOut, status_code=201)
async def upload(
    user: CurrentUser,
    db: DBSession,
    file: UploadFile = File(...),
    media_type: str = "image",
    direction: str = "input",
) -> ResourceOut:
    try:
        r = await resource_service.upload_resource(db, file, user.id, direction, media_type)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return ResourceOut.model_validate(r)


@router.get("", response_model=list[ResourceOut])
def list_(
    user: CurrentUser,
    db: DBSession,
    media_type: str | None = None,
    direction: str | None = None,
    keyword: str | None = None,
    limit: int = 50,
    offset: int = 0,
    folder_id: int | None = None,
) -> list[ResourceOut]:
    items, _ = resource_service.list_resources(db, user.id, media_type, direction, keyword, limit, offset, folder_id)
    return [ResourceOut.model_validate(i) for i in items]


@router.post("/batch-move")
def batch_move(body: ResourceBatchMoveIn, user: CurrentUser, db: DBSession) -> dict:
    try:
        from app.services import resource_folder_service
        return {"moved": resource_folder_service.move_resources(db, user.id, body.resource_ids, body.folder_id)}
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/{rid}/generation-info")
def generation_info(rid: int, user: CurrentUser, db: DBSession) -> dict:
    r = resource_service.get(db, rid)
    if not r or r.deleted_at or (r.owner_id is not None and r.owner_id != getattr(user, "id", None)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "资源不存在")
    link = db.query(TaskResource).filter(
        TaskResource.resource_id == rid,
        TaskResource.role == "output",
    ).order_by(TaskResource.id.desc()).first()
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "该素材不是任务生成文件")
    task = db.get(Task, link.task_id)
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "来源任务不存在")
    generation_type = db.get(GenerationType, task.generation_type_id) if task.generation_type_id else None
    batch = db.get(Batch, task.batch_id)
    return {
        "task_id": task.id,
        "task_status": task.status,
        "batch_id": task.batch_id,
        "batch_name": batch.name if batch else None,
        "generation_type_id": task.generation_type_id,
        "generation_type_name": generation_type.name if generation_type else None,
        "generation_type_code": generation_type.code if generation_type else None,
        "workflow_version_id": task.workflow_version_id,
        "params": task.params or {},
        "created_at": task.created_at,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
    }


@router.get("/{rid}/file")
def get_file(rid: int, user: CurrentUser, db: DBSession):
    r = resource_service.get(db, rid)
    if not r or r.deleted_at or r.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "资源不存在")
    storage = get_storage()
    if not storage.exists(r.storage_key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "资源文件不存在")
    return FileResponse(
        storage.abs_path(r.storage_key),
        media_type=r.mime,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/{rid}/thumb")
def get_thumb(rid: int, user: CurrentUser, db: DBSession):
    r = resource_service.get(db, rid)
    if not r or r.deleted_at or r.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "资源不存在")
    if not resource_service.ensure_thumbnail(db, r):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "缩略图不存在")
    storage = get_storage()
    return FileResponse(
        storage.abs_path(r.thumb_key),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.patch("/{rid}", response_model=ResourceOut)
def patch(rid: int, body: ResourcePatchIn, user: CurrentUser, db: DBSession) -> ResourceOut:
    r = resource_service.get(db, rid)
    if not r or r.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "资源不存在")
    if body.visibility:
        r.visibility = body.visibility
    db.commit()
    db.refresh(r)
    return ResourceOut.model_validate(r)


@router.post("/{rid}/move")
def move(rid: int, body: ResourceMoveIn, user: CurrentUser, db: DBSession) -> dict:
    try:
        from app.services import resource_folder_service
        return {"moved": resource_folder_service.move_resources(db, user.id, [rid], body.folder_id)}
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/{rid}", response_model=ResourceOut)
def get_one(rid: int, user: CurrentUser, db: DBSession) -> ResourceOut:
    r = resource_service.get(db, rid)
    if not r or r.deleted_at or (r.owner_id is not None and r.owner_id != getattr(user, "id", None)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "资源不存在")
    resource_service.ensure_media_metadata(db, r)
    return ResourceOut.model_validate(r)


@router.delete("/{rid}", status_code=204)
def delete(rid: int, user: CurrentUser, db: DBSession) -> None:
    r = resource_service.get(db, rid)
    if not r or r.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "资源不存在")
    resource_service.soft_delete(db, r)


# ---- 回收站 ----
@router.get("/recycle/list", response_model=list[ResourceOut])
def list_recycle(user: CurrentUser, db: DBSession) -> list[ResourceOut]:
    from app.models import Resource
    query = db.query(Resource).filter(Resource.deleted_at.is_not(None))
    if user.role != "admin":
        query = query.filter(Resource.owner_id == user.id)
    items = query.order_by(Resource.id.desc()).all()
    return [ResourceOut.model_validate(r) for r in items]


@router.post("/{rid}/restore", response_model=ResourceOut)
def restore(rid: int, user: CurrentUser, db: DBSession) -> ResourceOut:
    r = resource_service.get(db, rid)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "资源不存在")
    if r.owner_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权恢复")
    r.deleted_at = None
    db.commit()
    db.refresh(r)
    return ResourceOut.model_validate(r)


@router.delete("/{rid}/permanent", status_code=204)
def permanent_delete(rid: int, user: CurrentUser, db: DBSession) -> None:
    from app.core.deps import require_admin
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "仅管理员可彻底删除")
    r = resource_service.get(db, rid)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "资源不存在")
    # 删除物理文件
    if r.storage_key:
        try:
            get_storage().delete(r.storage_key)
        except Exception:
            pass
    if r.thumb_key:
        try:
            get_storage().delete(r.thumb_key)
        except Exception:
            pass
    db.delete(r)
    db.commit()


# ---- 参考视频抽帧 ----
@router.post("/{rid}/frames", response_model=list[ResourceOut])
def extract_frames(
    rid: int,
    user: CurrentUser,
    db: DBSession,
    timestamps: str = "",  # 逗号分隔的时间点（秒），如 "1.5,3.0,5.0"
    interval: float = 0,  # 间隔（秒），>0 时按间隔抽帧
) -> list[ResourceOut]:
    r = resource_service.get(db, rid)
    if not r or r.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "资源不存在")
    if r.owner_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问")
    if r.media_type != "video":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "仅支持视频抽帧")
    import asyncio, hashlib, io, os, subprocess, tempfile
    # 下载到临时文件
    data = get_storage().read(r.storage_key)
    tmp_in = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    tmp_in.write(data)
    tmp_in.close()
    tmp_dir = tempfile.mkdtemp()
    try:
        tlist = []
        if interval > 0:
            # 按间隔抽帧
            import subprocess as sp
            # 获取时长
            probe = sp.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", tmp_in.name],
                capture_output=True, text=True
            )
            duration = float(probe.stdout.strip() or "0")
            t = 0.0
            while t < duration:
                tlist.append(t)
                t += interval
        elif timestamps:
            tlist = [float(x) for x in timestamps.split(",") if x.strip()]
        else:
            tlist = [1.0]

        results: list[ResourceOut] = []
        for i, t in enumerate(tlist):
            out_file = os.path.join(tmp_dir, f"frame_{i:04d}.jpg")
            sp.run(
                ["ffmpeg", "-y", "-ss", str(t), "-i", tmp_in.name, "-frames:v", "1", "-q:v", "2", out_file],
                capture_output=True
            )
            if not os.path.exists(out_file):
                continue
            frame_data = open(out_file, "rb").read()
            sha = hashlib.sha256(frame_data).hexdigest()
            key = f"resources/frames/{sha[:8]}/frame_{i:04d}.jpg"
            get_storage().save_bytes(frame_data, key)
            from app.models import Resource as R, TaskResource
            frame_r = R(
                owner_id=user.id,
                media_type="image",
                direction="output",
                filename=f"{r.filename}_frame_{i:04d}.jpg",
                mime="image/jpeg",
                size=len(frame_data),
                sha256=sha,
                storage_key=key,
                visibility="private",
                meta={"source_video": r.id, "timestamp": t},
            )
            db.add(frame_r)
            db.flush()
            results.append(ResourceOut.model_validate(frame_r))
        db.commit()
        return results
    finally:
        os.unlink(tmp_in.name)
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
