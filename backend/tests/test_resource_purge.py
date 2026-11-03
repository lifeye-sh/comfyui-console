from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Resource, Take, TaskResource
from app.services import resource_service
from app.storage.local_fs import LocalFSStorage


def _recycled_resource(storage: LocalFSStorage, filename: str = "output.png") -> Resource:
    key = f"resources/test/{filename}"
    thumb_key = resource_service.thumbnail_storage_key(key)
    storage.save_bytes(b"image", key)
    storage.save_bytes(b"thumb", thumb_key)
    return Resource(
        owner_id=1,
        media_type="image",
        direction="output",
        filename=filename,
        mime="image/png",
        size=5,
        storage_key=key,
        thumb_key=thumb_key,
        visibility="private",
        deleted_at=datetime.now(timezone.utc),
    )


def test_permanent_delete_removes_unprotected_resource_and_task_link(tmp_path, monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    storage = LocalFSStorage(str(tmp_path))
    monkeypatch.setattr(resource_service, "get_storage", lambda: storage)

    with Session(engine) as db:
        resource = _recycled_resource(storage)
        db.add(resource)
        db.flush()
        resource_id = resource.id
        storage_key = resource.storage_key
        thumb_key = resource.thumb_key
        db.add(TaskResource(task_id=999, resource_id=resource_id, role="output"))
        db.commit()

        outcome, reason = resource_service.permanently_delete_resource(db, resource)

        assert (outcome, reason) == ("deleted", None)
        assert db.get(Resource, resource_id) is None
        assert db.query(TaskResource).filter_by(resource_id=resource_id).count() == 0
        assert not storage.exists(storage_key)
        assert thumb_key is not None and not storage.exists(thumb_key)


def test_permanent_delete_restores_resource_used_by_take(tmp_path, monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    storage = LocalFSStorage(str(tmp_path))
    monkeypatch.setattr(resource_service, "get_storage", lambda: storage)

    with Session(engine) as db:
        resource = _recycled_resource(storage, "take.png")
        db.add(resource)
        db.flush()
        resource_id = resource.id
        storage_key = resource.storage_key
        take = Take(owner_id=1, shot_id=999, scope="start", resource_id=resource_id, take_no=1)
        db.add(take)
        db.commit()
        take_id = take.id

        outcome, reason = resource_service.permanently_delete_resource(db, resource)

        assert outcome == "restored"
        assert reason is not None and "镜头版本" in reason
        restored = db.get(Resource, resource_id)
        assert restored is not None and restored.deleted_at is None
        assert db.get(Take, take_id) is not None
        assert storage.exists(storage_key)
