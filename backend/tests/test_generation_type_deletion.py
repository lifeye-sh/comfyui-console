from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Batch, GenerationType, Task


client = TestClient(app)


def _headers() -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_disabled_generation_type_without_tasks_can_be_deleted() -> None:
    with TestClient(app):
        with SessionLocal() as db:
            item = GenerationType(
                media_type="image", code="deletable-unused-type", name="可删除类型",
                param_template=[], enabled=False,
            )
            db.add(item)
            db.commit()
            db.refresh(item)
            type_id = item.id

        listing = client.get("/api/v1/generation-types", headers=_headers())
        row = next(item for item in listing.json() if item["id"] == type_id)
        assert row["can_delete"] is True

        deleted = client.delete(f"/api/v2/generation-types/{type_id}", headers=_headers())

        assert deleted.status_code == 204
        assert all(item["id"] != type_id for item in client.get(
            "/api/v1/generation-types", headers=_headers()
        ).json())
        assert client.get(f"/api/v2/generation-types/{type_id}/config", headers=_headers()).status_code == 404


def test_generation_type_with_any_task_record_cannot_be_deleted() -> None:
    with TestClient(app):
        with SessionLocal() as db:
            item = GenerationType(
                media_type="video", code="used-disabled-type", name="已使用类型",
                param_template=[], enabled=False,
            )
            db.add(item)
            db.flush()
            batch = Batch(name="历史批次", generation_type_id=item.id)
            db.add(batch)
            db.flush()
            db.add(Task(batch_id=batch.id, generation_type_id=None, status="DRAFT", params={}))
            db.commit()
            type_id = item.id

        listing = client.get("/api/v1/generation-types", headers=_headers())
        row = next(item for item in listing.json() if item["id"] == type_id)
        assert row["can_delete"] is False

        deleted = client.delete(f"/api/v2/generation-types/{type_id}", headers=_headers())

        assert deleted.status_code == 409
        assert "已经产生任务" in deleted.json()["message"]
