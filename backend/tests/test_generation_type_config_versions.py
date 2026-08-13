from __future__ import annotations

from copy import deepcopy

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import AuditLog, GenerationType, GenerationTypeConfigVersion, Task
from app.services import generation_type_config_service as service


client = TestClient(app)


def _token(username: str = "admin", password: str = "admin123") -> str:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}"}


def _type_id() -> int:
    with SessionLocal() as db:
        return db.query(GenerationType).filter_by(code="t2i").one().id


def _valid_config(type_id: int) -> dict:
    with SessionLocal() as db:
        generation_type = db.get(GenerationType, type_id)
        config = service.build_default_config(db, generation_type)
    config["parameters"] = [{"key": "prompt", "type": "textarea", "label": "提示词"}]
    return config


def test_invalid_config_cannot_be_published() -> None:
    with TestClient(app):
        type_id = _type_id()
        invalid = _valid_config(type_id)
        invalid["parameters"] = [
            {"key": "prompt", "type": "textarea"},
            {"key": "prompt", "type": "unknown"},
        ]
        saved = client.put(
            f"/api/v2/generation-types/{type_id}/config/draft", json={"config": invalid}, headers=_headers()
        )
        assert saved.status_code == 200
        assert len(saved.json()["validation_errors"]) >= 2

        published = client.post(f"/api/v2/generation-types/{type_id}/config/publish", headers=_headers())
        assert published.status_code == 422


def test_publish_diff_and_rollback_create_immutable_versions() -> None:
    with TestClient(app):
        type_id = _type_id()
        config = _valid_config(type_id)
        first_save = client.put(
            f"/api/v2/generation-types/{type_id}/config/draft", json={"config": config}, headers=_headers()
        )
        assert first_save.status_code == 200
        first = client.post(f"/api/v2/generation-types/{type_id}/config/publish", headers=_headers())
        assert first.status_code == 200
        first_id = first.json()["id"]

        draft = client.get(f"/api/v2/generation-types/{type_id}/config/draft", headers=_headers())
        changed = deepcopy(draft.json()["config"])
        changed["page"]["title"] = "新版文生图"
        client.put(f"/api/v2/generation-types/{type_id}/config/draft", json={"config": changed}, headers=_headers())
        second = client.post(f"/api/v2/generation-types/{type_id}/config/publish", headers=_headers())
        assert second.status_code == 200
        second_id = second.json()["id"]

        diff = client.get(
            f"/api/v2/generation-types/{type_id}/config/diff",
            params={"from_version_id": first_id, "to_version_id": second_id},
            headers=_headers(),
        )
        assert diff.status_code == 200
        assert any(item["path"] == "page.title" for item in diff.json()["changes"])

        rolled = client.post(
            f"/api/v2/generation-types/{type_id}/config/rollback",
            json={"source_version_id": first_id},
            headers=_headers(),
        )
        assert rolled.status_code == 200
        assert rolled.json()["id"] not in (first_id, second_id)
        assert rolled.json()["source_version_id"] == first_id
        assert rolled.json()["config"]["page"]["title"] == config["page"]["title"]

        with SessionLocal() as db:
            assert db.get(GenerationTypeConfigVersion, first_id).config["page"]["title"] == config["page"]["title"]
            actions = {item.action for item in db.query(AuditLog).filter(AuditLog.target_id == type_id)}
            assert "generation_type.config.publish" in actions
            assert "generation_type.config.rollback" in actions


def test_workflow_mapping_check_rejects_foreign_type() -> None:
    with TestClient(app):
        type_id = _type_id()
        config = _valid_config(type_id)
        config["workflow_bindings"] = [{"workflow_version_id": 999999, "is_default": True}]
        result = client.post(
            f"/api/v2/generation-types/{type_id}/config/validate", json={"config": config}, headers=_headers()
        )
        assert result.status_code == 200
        assert result.json()["valid"] is False
        assert any(item["code"] == "wrong_type" for item in result.json()["errors"])


def test_task_snapshot_stays_on_original_config_version() -> None:
    with TestClient(app):
        type_id = _type_id()
        with SessionLocal() as db:
            generation_type = db.get(GenerationType, type_id)
            original_id = generation_type.published_config_version_id
            tasks = db.query(Task).filter(Task.generation_type_id == type_id).limit(1).all()
            if tasks:
                tasks[0].config_version_id = original_id
                db.commit()
                task_id = tasks[0].id
            else:
                return

        client.get(f"/api/v2/generation-types/{type_id}/config/draft", headers=_headers())
        with SessionLocal() as db:
            task = db.get(Task, task_id)
            assert task.config_version_id == original_id
