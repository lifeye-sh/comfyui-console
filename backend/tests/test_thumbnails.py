"""Thumbnail generation and historical backfill tests."""
from __future__ import annotations

import io
from types import SimpleNamespace

from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Resource
from app.services import resource_service
from app.storage.local_fs import LocalFSStorage


def _png_bytes(width: int = 1200, height: int = 800) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (width, height), "#336699").save(output, format="PNG")
    return output.getvalue()


def test_build_image_thumbnail() -> None:
    thumbnail, width, height = resource_service.build_image_thumbnail(_png_bytes())

    assert (width, height) == (1200, 800)
    with Image.open(io.BytesIO(thumbnail)) as image:
        assert image.format == "JPEG"
        assert max(image.size) == 1024
        assert image.width <= 1024
        assert image.height <= 1024


def test_video_mime_or_extension_overrides_comfy_image_bucket() -> None:
    assert resource_service.infer_media_type("output.mp4", "video/mp4", "image") == "video"
    assert resource_service.infer_media_type("output.webm", "application/octet-stream", "image") == "video"
    assert resource_service.infer_media_type("output.png", "image/png", "video") == "image"


def test_ensure_thumbnail_backfills_existing_resource(tmp_path, monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    storage = LocalFSStorage(str(tmp_path))
    monkeypatch.setattr(resource_service, "get_storage", lambda: storage)

    original_key = "resources/2026-08/example/image.png"
    storage.save_bytes(_png_bytes(), original_key)

    with Session(engine) as db:
        resource = Resource(
            media_type="image",
            direction="output",
            filename="image.png",
            mime="image/png",
            size=1,
            storage_key=original_key,
            visibility="private",
        )
        db.add(resource)
        db.commit()
        db.refresh(resource)

        assert resource_service.ensure_thumbnail(db, resource) is True
        assert resource.thumb_key is not None
        assert storage.exists(resource.thumb_key)
        assert (resource.width, resource.height) == (1200, 800)


def test_ensure_thumbnail_upgrades_legacy_low_resolution_thumbnail(tmp_path, monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    storage = LocalFSStorage(str(tmp_path))
    monkeypatch.setattr(resource_service, "get_storage", lambda: storage)

    original_key = "resources/2026-08/example/legacy.png"
    legacy_thumb_key = "resources/2026-08/example/legacy.thumb.jpg"
    storage.save_bytes(_png_bytes(), original_key)
    legacy = io.BytesIO()
    Image.new("RGB", (256, 171), "#336699").save(legacy, format="JPEG")
    storage.save_bytes(legacy.getvalue(), legacy_thumb_key)

    with Session(engine) as db:
        resource = Resource(
            media_type="image",
            direction="output",
            filename="legacy.png",
            mime="image/png",
            size=1,
            storage_key=original_key,
            thumb_key=legacy_thumb_key,
            visibility="private",
        )
        db.add(resource)
        db.commit()
        db.refresh(resource)

        assert resource_service.ensure_thumbnail(db, resource) is True
        assert resource.thumb_key == resource_service.thumbnail_storage_key(original_key)
        assert resource.thumb_key != legacy_thumb_key
        with Image.open(storage.abs_path(resource.thumb_key)) as upgraded:
            assert max(upgraded.size) == 1024


def test_ensure_thumbnail_extracts_and_caches_video_first_frame(tmp_path, monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    storage = LocalFSStorage(str(tmp_path))
    monkeypatch.setattr(resource_service, "get_storage", lambda: storage)
    jpeg, _, _ = resource_service.build_image_thumbnail(_png_bytes(640, 360))
    monkeypatch.setattr(
        resource_service.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=jpeg, stderr=b""),
    )
    video_key = "resources/2026-08/example/video.mp4"
    storage.save_bytes(b"fake-video", video_key)

    with Session(engine) as db:
        resource = Resource(
            media_type="video", direction="output", filename="video.mp4",
            mime="video/mp4", size=10, storage_key=video_key, visibility="private",
        )
        db.add(resource)
        db.commit()

        assert resource_service.ensure_thumbnail(db, resource) is True
        assert resource.thumb_key is not None
        assert storage.exists(resource.thumb_key)
