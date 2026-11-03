"""资源服务：上传、去重、缩略图、列表、软删除。"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Optional

from fastapi import UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.models import Resource
from app.storage.local_fs import get_storage

logger = logging.getLogger(__name__)

MAX_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
UPLOAD_CHUNK_SIZE = 1024 * 1024
THUMBNAIL_SIZE = (1024, 1024)
THUMBNAIL_VERSION = "v2-hd"
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v", ".gif"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"}
CROP_RATIOS = {
    "1:1": (1, 1),
    "4:3": (4, 3),
    "3:4": (3, 4),
    "3:2": (3, 2),
    "2:3": (2, 3),
    "16:9": (16, 9),
    "9:16": (9, 16),
    "21:9": (21, 9),
}


def _sha256(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def thumbnail_storage_key(storage_key: str) -> str:
    """Return a deterministic thumbnail key for a stored image."""
    stem, _ = os.path.splitext(storage_key)
    return f"{stem}.thumb-{THUMBNAIL_VERSION}.jpg"


def infer_media_type(filename: str, mime: str, fallback: str = "image") -> str:
    """Infer the real media type because some ComfyUI video nodes report files under `images`."""
    normalized_mime = (mime or "").lower()
    extension = os.path.splitext(filename or "")[1].lower()
    if normalized_mime.startswith("video/") or extension in VIDEO_EXTENSIONS:
        return "video"
    if normalized_mime.startswith("audio/") or extension in AUDIO_EXTENSIONS:
        return "audio"
    if normalized_mime.startswith("text/") or extension in {".txt", ".json", ".md", ".csv", ".xml", ".yaml", ".yml"}:
        return "text"
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

    return build_image_thumbnail_from_source(io.BytesIO(data))


def build_image_thumbnail_from_source(source: object) -> tuple[bytes, int, int]:
    """Decode an image source without requiring the original file in memory."""
    import io

    from PIL import Image

    with Image.open(source) as img:
        width, height = img.size
        thumb = img.copy()
        thumb.thumbnail(THUMBNAIL_SIZE)
        if thumb.mode not in ("RGB", "L"):
            thumb = thumb.convert("RGB")
        elif thumb.mode == "L":
            thumb = thumb.convert("RGB")
        output = io.BytesIO()
        thumb.save(output, format="JPEG", quality=90, optimize=True, progressive=True)
    return output.getvalue(), width, height


def centered_crop_box(width: int, height: int, aspect_ratio: str) -> tuple[int, int, int, int]:
    """Return the largest centered crop box matching a supported aspect ratio."""
    ratio = CROP_RATIOS.get(aspect_ratio)
    if not ratio:
        raise ValueError("不支持的图片比例")
    if width <= 0 or height <= 0:
        raise ValueError("图片尺寸无效")
    target = ratio[0] / ratio[1]
    current = width / height
    if current > target:
        crop_width = max(1, min(width, round(height * target)))
        left = (width - crop_width) // 2
        return left, 0, left + crop_width, height
    crop_height = max(1, min(height, round(width / target)))
    top = (height - crop_height) // 2
    return 0, top, width, top + crop_height


def build_cropped_image(
    source: object, aspect_ratio: str
) -> tuple[bytes, int, int, str, str, tuple[int, int, int, int]]:
    """Center-crop one static image and return encoded bytes plus output metadata."""
    from PIL import Image, ImageOps

    with Image.open(source) as opened:
        if getattr(opened, "is_animated", False):
            raise ValueError("暂不支持动图裁剪")
        source_format = (opened.format or "PNG").upper()
        image = ImageOps.exif_transpose(opened)
        box = centered_crop_box(image.width, image.height, aspect_ratio)
        cropped = image.crop(box)
        output_format = source_format if source_format in {"JPEG", "PNG", "WEBP"} else "PNG"
        extension = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[output_format]
        mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}[output_format]
        if output_format == "JPEG" and cropped.mode not in {"RGB", "L"}:
            cropped = cropped.convert("RGB")
        output = io.BytesIO()
        save_options: dict[str, object] = {"format": output_format}
        if output_format == "JPEG":
            save_options.update(quality=95, optimize=True)
        elif output_format == "PNG":
            save_options.update(optimize=True)
        else:
            save_options.update(quality=95, method=6)
        cropped.save(output, **save_options)
        return output.getvalue(), cropped.width, cropped.height, extension, mime, box


def crop_image_resource(db: Session, resource: Resource, aspect_ratio: str) -> Resource:
    """Create a cropped resource beside its source without modifying the original."""
    if resource.media_type != "image":
        raise ValueError("仅支持图片裁剪")
    storage = get_storage()
    if not storage.exists(resource.storage_key):
        raise ValueError("原始图片文件不存在")

    data, width, height, extension, mime, box = build_cropped_image(
        storage.abs_path(resource.storage_key), aspect_ratio
    )
    sha = _sha256(data)
    stem = os.path.splitext(os.path.basename(resource.filename))[0][:180]
    ratio_label = aspect_ratio.replace(":", "x")
    filename = f"{stem}_crop_{ratio_label}{extension}"
    key = f"resources/{datetime.now(timezone.utc):%Y-%m}/{sha[:16]}/{filename}"
    thumb_key = thumbnail_storage_key(key)
    saved_keys: list[str] = []
    try:
        storage.save_bytes(data, key)
        saved_keys.append(key)
        thumb_data, _, _ = build_image_thumbnail(data)
        storage.save_bytes(thumb_data, thumb_key)
        saved_keys.append(thumb_key)
        cropped = Resource(
            owner_id=resource.owner_id,
            folder_id=resource.folder_id,
            media_type="image",
            direction="output",
            filename=filename,
            mime=mime,
            size=len(data),
            sha256=sha,
            storage_key=key,
            thumb_key=thumb_key,
            width=width,
            height=height,
            visibility=resource.visibility,
            meta={"source_image": resource.id, "crop_ratio": aspect_ratio, "crop_box": list(box)},
        )
        db.add(cropped)
        db.commit()
        db.refresh(cropped)
        return cropped
    except Exception:
        db.rollback()
        for saved_key in saved_keys:
            try:
                storage.delete(saved_key)
            except Exception:  # noqa: BLE001
                pass
        raise


def build_video_thumbnail(video_path: str) -> bytes:
    """Extract and scale the first decodable video frame as JPEG bytes."""
    result = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-ss", "0", "-i", video_path,
            "-frames:v", "1", "-vf",
            f"scale={THUMBNAIL_SIZE[0]}:{THUMBNAIL_SIZE[1]}:force_original_aspect_ratio=decrease",
            "-q:v", "2", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1",
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
    current_thumb_key = thumbnail_storage_key(resource.storage_key)
    if resource.thumb_key == current_thumb_key and storage.exists(current_thumb_key):
        return True
    if not storage.exists(resource.storage_key):
        return False

    if storage.exists(current_thumb_key):
        resource.thumb_key = current_thumb_key
        db.commit()
        db.refresh(resource)
        return True

    try:
        if resource.media_type == "video":
            thumb_data = build_video_thumbnail(storage.abs_path(resource.storage_key))
            width = height = None
        else:
            data = storage.read(resource.storage_key)
            thumb_data, width, height = build_image_thumbnail(data)
        storage.save_bytes(thumb_data, current_thumb_key)
        resource.thumb_key = current_thumb_key
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
    size = 0
    hasher = hashlib.sha256()
    while chunk := await file.read(UPLOAD_CHUNK_SIZE):
        size += len(chunk)
        if size > MAX_SIZE:
            raise ValueError("文件不能超过 2GB")
        hasher.update(chunk)
    sha = hasher.hexdigest()
    await file.seek(0)
    existing = db.query(Resource).filter(
        Resource.sha256 == sha, Resource.owner_id == owner_id, Resource.deleted_at.is_(None)
    ).first()
    if existing:
        return existing

    ext = os.path.splitext(file.filename or "")[1] or ""
    safe_name = (file.filename or f"{sha[:16]}{ext}").replace("/", "_")
    key = f"resources/{datetime.now(timezone.utc):%Y-%m}/{sha[:16]}/{safe_name}"
    storage = get_storage()
    await run_in_threadpool(storage.save_file, file.file, key)

    mime = file.content_type or "application/octet-stream"
    width = height = None
    thumb_key: Optional[str] = None
    if media_type == "image" and mime.startswith("image/"):
        try:
            thumb_data, width, height = build_image_thumbnail_from_source(storage.abs_path(key))
            thumb_key = thumbnail_storage_key(key)
            storage.save_bytes(thumb_data, thumb_key)
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
        size=size,
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


def storage_summary(db: Session, owner_id: int) -> dict[str, int]:
    """Return per-owner logical storage usage, counting each stored file key once."""
    owner_resources = db.query(Resource).filter(Resource.owner_id == owner_id)
    active_count = owner_resources.filter(Resource.deleted_at.is_(None)).count()
    recycle_bin_count = owner_resources.filter(Resource.deleted_at.is_not(None)).count()

    all_files = db.query(
        Resource.storage_key.label("storage_key"),
        func.max(Resource.size).label("size"),
    ).filter(
        Resource.owner_id == owner_id,
    ).group_by(Resource.storage_key).subquery()
    active_files = db.query(
        Resource.storage_key.label("storage_key"),
        func.max(Resource.size).label("size"),
    ).filter(
        Resource.owner_id == owner_id,
        Resource.deleted_at.is_(None),
    ).group_by(Resource.storage_key).subquery()

    total_bytes = int(db.query(func.coalesce(func.sum(all_files.c.size), 0)).scalar() or 0)
    active_bytes = int(db.query(func.coalesce(func.sum(active_files.c.size), 0)).scalar() or 0)
    return {
        "total_bytes": total_bytes,
        "active_bytes": active_bytes,
        "recycle_bin_bytes": max(0, total_bytes - active_bytes),
        "total_count": active_count + recycle_bin_count,
        "active_count": active_count,
        "recycle_bin_count": recycle_bin_count,
    }


def soft_delete(db: Session, r: Resource) -> None:
    r.deleted_at = datetime.now(timezone.utc)
    db.commit()


def permanently_delete_resource(db: Session, resource: Resource) -> tuple[str, str | None]:
    """Purge a recycled resource, or restore it when active business records still use it."""
    from app.models import ProjectResourceLink, Share, SourceDocument, Take, TaskResource

    resource_id = resource.id
    protected_by: list[str] = []
    if db.query(Take.id).filter(Take.resource_id == resource_id).first():
        protected_by.append("镜头版本")
    if db.query(SourceDocument.id).filter(SourceDocument.resource_id == resource_id).first():
        protected_by.append("短剧源文档")
    if db.query(ProjectResourceLink.id).filter(ProjectResourceLink.resource_id == resource_id).first():
        protected_by.append("项目素材")
    if db.query(Share.id).filter(Share.resource_id == resource_id).first():
        protected_by.append("分享链接")
    if protected_by:
        resource.deleted_at = None
        db.commit()
        db.refresh(resource)
        return "restored", f"仍被{'、'.join(protected_by)}使用，已自动恢复"

    stem, _ = os.path.splitext(resource.storage_key or "")
    storage_keys = {
        key for key in (
            resource.storage_key,
            resource.thumb_key,
            f"{stem}.thumb.jpg" if stem else None,
            thumbnail_storage_key(resource.storage_key) if resource.storage_key else None,
        ) if key
    }
    try:
        db.query(TaskResource).filter(TaskResource.resource_id == resource_id).delete(synchronize_session=False)
        db.delete(resource)
        db.flush()
        db.commit()
    except Exception:
        db.rollback()
        raise

    storage = get_storage()
    for key in storage_keys:
        try:
            storage.delete(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("永久删除素材文件失败 resource=%s key=%s: %s", resource_id, key, exc)
    return "deleted", None
