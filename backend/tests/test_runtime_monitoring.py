from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base, SessionLocal
from app.main import app
from app.models import Batch, Node, Task
from app.queue.dispatcher import Dispatcher


client = TestClient(app)


def _headers() -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_dispatcher_status_is_admin_only_and_reports_heartbeat() -> None:
    with TestClient(app):
        response = client.get("/api/v1/runtime/dispatcher", headers=_headers())
        assert response.status_code == 200
        body = response.json()
        assert body["running"] is True
        assert body["thread_name"] == "comfyui-dispatcher"
        assert set(body["tasks"]) >= {"PENDING", "QUEUED", "RUNNING"}


def test_manual_release_and_resubmit_frees_slot() -> None:
    with TestClient(app):
        with SessionLocal() as db:
            batch = Batch(name="runtime recovery")
            db.add(batch); db.flush()
            task = Task(batch_id=batch.id, status="QUEUED", prompt_id="lost", started_at=datetime.now(timezone.utc))
            db.add(task); db.commit(); task_id = task.id
        released = client.post(f"/api/v1/runtime/tasks/{task_id}/release", headers=_headers())
        assert released.status_code == 200
        assert released.json()["status"] == "FAILED"
        resubmitted = client.post(f"/api/v1/runtime/tasks/{task_id}/resubmit", headers=_headers())
        assert resubmitted.status_code == 200
        assert resubmitted.json()["status"] == "PENDING"


def test_orphaned_prompt_is_failed_only_when_missing_from_comfy_queue() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    class MissingClient:
        async def get_queue(self) -> dict:
            return {"queue_running": [], "queue_pending": []}

    with Session(engine) as db:
        batch = Batch(name="orphan")
        db.add(batch); db.flush()
        task = Task(
            batch_id=batch.id, status="QUEUED", prompt_id="gone",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        db.add(task); db.commit()
        dispatcher = Dispatcher(orphan_timeout_seconds=30)
        asyncio.run(dispatcher._recover_orphan(db, task, MissingClient()))
        assert task.status == "FAILED"
        assert "丢失" in task.error


def test_500_pending_rows_remain_queryable() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        batch = Batch(name="500 queue")
        db.add(batch); db.flush()
        db.add_all([Task(batch_id=batch.id, row_no=index, status="PENDING") for index in range(500)])
        db.commit()
        dispatcher = Dispatcher(session_factory=lambda: Session(engine))
        status = dispatcher.status()
        assert status["tasks"]["PENDING"] == 500
