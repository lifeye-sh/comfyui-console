"""资源服务：上传、去重、缩略图、列表、软删除。"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Optional

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models import Resource
from app.storage.local_fs import get_storage

logger = logging.getLogger(__name__)

MAX_SIZE = 100 * 1024 * 1024  # 100MB
THUMBNAIL_SIZE = (256, 256)
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v", ".gif"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"}


def _sha256(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def thumbnail_storage_key(storage_key: str) -> str:
    """Return a deterministic thumbnail key for a stored image."""
    stem, _ = os.path.splitext(storage_key)
    return f"{stem}.thumb.jpg"


def infer_media_type(filename: str, mime: str, fallback: str = "image") -> str:
    """Infer the real media type because some ComfyUI video nodes report files under `images`."""
    normalized_mime = (mime or "").lower()
    extension = os.path.splitext(filename or "")[1].lower()
    if normalized_mime.startswith("video/") or extension in VIDEO_EXTENSIONS:
        return "video"
    if normalized_mime.startswith("audio/") or extension in AUDIO_EXTENSIONS:
        return "audio"
    if normalized_mime.startswith("image/"):
        return "image"
    return fallback


def repair_resource_media_types(db: Session) -> int:
    """Correct historical resources whose ComfyUI output bucket hid the real file type."""
    changed = 0
    for resource in db.query(Resource).filter(Resource.deleted_at.is_(None)).all():
        inferred = infer_media_type(resource.filename, resource.mime, resource.media_type)
        if inferred != resource.media_type:
            resource.media_type = inferred
            changed += 1
    if changed:
        db.commit()
    return changed


def build_image_thumbnail(data: bytes) -> tuple[bytes, int, int]:
    """Decode an image and return JPEG thumbnail bytes plus original dimensions."""
    import io

    from PIL import Image

    with Image.open(io.BytesIO(data)) as img:
        width, height = img.size
        thumb = img.copy()
        thumb.thumbnail(THUMBNAIL_SIZE)
        if thumb.mode not in ("RGB", "L"):
            thumb = thumb.convert("RGB")
        elif thumb.mode == "L":
            thumb = thumb.convert("RGB")
        output = io.BytesIO()
        thumb.save(output, format="JPEG", quality=80, optimize=True)
    return output.getvalue(), width, height


def build_video_thumbnail(video_path: str) -> bytes:
    """Extract and scale the first decodable video frame as JPEG bytes."""
    result = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-ss", "0", "-i", video_path,
            "-frames:v", "1", "-vf",
            f"scale={THUMBNAIL_SIZE[0]}:{THUMBNAIL_SIZE[1]}:force_original_aspect_ratio=decrease",
            "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1",
        ],
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError(result.stderr.decode("utf-8", errors="ignore") or "无法提取视频首帧")
    return result.stdout


def probe_media_metadata(media_path: str) -> tuple[int | None, int | None, int | None]:
    """Return width, height and rounded duration using ffprobe when available."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", media_path],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode != 0:
        return None, None, None
    payload = json.loads(result.stdout or "{}")
    video = next((stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"), {})
    duration_value = payload.get("format", {}).get("duration") or next(
        (stream.get("duration") for stream in payload.get("streams", []) if stream.get("duration")), None
    )
    duration = max(0, round(float(duration_value))) if duration_value is not None else None
    return video.get("width"), video.get("height"), duration


def ensure_media_metadata(db: Session, resource: Resource) -> None:
    if resource.media_type not in ("video", "audio") or resource.deleted_at is not None:
        return
    if resource.duration is not None and (resource.media_type == "audio" or (resource.width and resource.height)):
        return
    storage = get_storage()
    if not storage.exists(resource.storage_key):
        return
    try:
        width, height, duration = probe_media_metadata(storage.abs_path(resource.storage_key))
        resource.width = resource.width or width
        resource.height = resource.height or height
        resource.duration = resource.duration if resource.duration is not None else duration
        db.commit()
        db.refresh(resource)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("媒体元数据补全失败 resource=%s: %s", resource.id, exc)


def ensure_thumbnail(db: Session, resource: Resource) -> bool:
    """Create a missing thumbnail for an existing image or video resource on demand."""
    if resource.media_type not in ("image", "video") or resource.deleted_at is not None:
        return False

    storage = get_storage()
    if resource.thumb_key and storage.exists(resource.thumb_key):
        return True
    if not storage.exists(resource.storage_key):
        return False

    try:
        if resource.media_type == "video":
            thumb_data = build_video_thumbnail(storage.abs_path(resource.storage_key))
            width = height = None
        else:
            data = storage.read(resource.storage_key)
            thumb_data, width, height = build_image_thumbnail(data)
        thumb_key = thumbnail_storage_key(resource.storage_key)
        storage.save_bytes(thumb_data, thumb_key)
        resource.thumb_key = thumb_key
        resource.width = resource.width or width
        resource.height = resource.height or height
        db.commit()
        db.refresh(resource)
        return True
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("历史媒体缩略图补全失败 resource=%s: %s", resource.id, exc)
        return False


async def upload_resource(
    db: Session,
    file: UploadFile,
    owner_id: Optional[int],
    direction: str = "input",
    media_type: str = "image",
) -> Resource:
    data = await file.read()
    if len(data) > MAX_SIZE:
        raise ValueError("文件超过大小上限")

    sha = _sha256(data)
    existing = db.query(Resource).filter(
        Resource.sha256 == sha, Resource.owner_id == owner_id, Resource.deleted_at.is_(None)
    ).first()
    if existing:
        return existing

    ext = os.path.splitext(file.filename or "")[1] or ""
    safe_name = (file.filename or f"{sha[:16]}{ext}").replace("/", "_")
    key = f"resources/{datetime.now(timezone.utc):%Y-%m}/{sha[:16]}/{safe_name}"
    get_storage().save_bytes(data, key)

    mime = file.content_type or "application/octet-stream"
    width = height = None
    thumb_key: Optional[str] = None
    if media_type == "image" and mime.startswith("image/"):
        try:
            thumb_data, width, height = build_image_thumbnail(data)
            thumb_key = thumbnail_storage_key(key)
            get_storage().save_bytes(thumb_data, thumb_key)
        except Exception as e:  # noqa: BLE001
            logger.warning("缩略图生成失败: %s", e)

    from app.services.resource_folder_service import ensure_upload_folder
    r = Resource(
        owner_id=owner_id,
        folder_id=ensure_upload_folder(db, owner_id).id if owner_id else None,
        media_type=media_type,
        direction=direction,
        filename=safe_name,
        mime=mime,
        size=len(data),
        sha256=sha,
        storage_key=key,
        thumb_key=thumb_key,
        width=width,
        height=height,
        visibility="private",
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def get(db: Session, rid: int) -> Optional[Resource]:
    return db.get(Resource, rid)


def list_resources(
    db: Session,
    owner_id: int,
    media_type: Optional[str] = None,
    direction: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    folder_id: Optional[int] = None,
) -> tuple[list[Resource], int]:
    repair_resource_media_types(db)
    q = db.query(Resource).filter(Resource.deleted_at.is_(None), Resource.owner_id == owner_id)
    if folder_id is not None:
        q = q.filter(Resource.folder_id == folder_id)
    if media_type:
        q = q.filter(Resource.media_type == media_type)
    if direction:
        q = q.filter(Resource.direction == direction)
    if keyword:
        q = q.filter(Resource.filename.contains(keyword))
    total = q.count()
    items = q.order_by(Resource.id.desc()).offset(offset).limit(limit).all()
    return items, total


def soft_delete(db: Session, r: Resource) -> None:
    r.deleted_at = datetime.now(timezone.utc)
    db.commit()
