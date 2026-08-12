from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Resource, User
from app.services import resource_folder_service


def _db() -> tuple[Session, int]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    user = User(username="folder-user", password_hash="x")
    db.add(user); db.commit(); db.refresh(user)
    return db, user.id


def test_unlimited_folder_tree_and_cycle_guard() -> None:
    db, owner_id = _db()
    try:
        parent_id = None
        folders = []
        for index in range(12):
            folder = resource_folder_service.create(db, owner_id, f"第{index + 1}层", parent_id)
            folders.append(folder); parent_id = folder.id
        tree = resource_folder_service.tree(db, owner_id)
        current = next(item for item in tree if item["id"] == folders[0].id)
        for folder in folders[1:]:
            current = next(item for item in current["children"] if item["id"] == folder.id)
        with pytest.raises(ValueError, match="自身或子文件夹"):
            resource_folder_service.update(db, owner_id, folders[0].id, None, folders[-1].id, True)
    finally:
        db.close()


def test_generated_folder_uses_date_and_task_name() -> None:
    db, owner_id = _db()
    try:
        folder = resource_folder_service.ensure_task_result_folder(db, owner_id, 29, "动作迁移", datetime(2026, 8, 12, 10, 30))
        db.commit()
        assert folder.name == "29-动作迁移"
        assert folder.system_key == "task_results:2026-08-12:task:29"
    finally:
        db.close()


def test_generated_folder_does_not_require_system_tzdata(monkeypatch) -> None:
    db, owner_id = _db()
    try:
        import zoneinfo
        monkeypatch.setattr(zoneinfo, "ZoneInfo", lambda _key: (_ for _ in ()).throw(RuntimeError("tzdata missing")))
        folder = resource_folder_service.ensure_task_result_folder(db, owner_id, 30, "文生图")
        db.commit()
        assert folder.system_key.startswith("task_results:")
        assert folder.system_key.endswith(":task:30")
    finally:
        db.close()


def test_move_resources_is_owner_scoped() -> None:
    db, owner_id = _db()
    try:
        target = resource_folder_service.create(db, owner_id, "项目A", None)
        resource = Resource(owner_id=owner_id, media_type="image", direction="output", filename="a.png", storage_key="a.png")
        db.add(resource); db.commit(); db.refresh(resource)
        assert resource_folder_service.move_resources(db, owner_id, [resource.id], target.id) == 1
        assert db.get(Resource, resource.id).folder_id == target.id
    finally:
        db.close()
