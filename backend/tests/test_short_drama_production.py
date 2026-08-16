"""V2.1 shot -> task -> multi-output Take production-loop tests."""
from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base, SessionLocal, init_db
from app.main import app
from app.models import Batch, GenerationType, Node, Resource, ShotTaskLink, Task, TaskResource, User, Workflow, WorkflowVersion
from app.queue.dispatcher import Dispatcher

client = TestClient(app)


def _login(username: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _setup() -> tuple[dict[str, str], int, int, int]:
    init_db()
    admin = _login("admin", "admin123")
    username = f"production-{uuid4().hex[:10]}"
    assert client.post("/api/v1/users", headers=admin, json={
        "username": username, "password": "user12345", "role": "user",
    }).status_code == 201
    headers = _login(username, "user12345")
    project = client.post("/api/v2/short-drama/projects", headers=headers, json={
        "name": "镜头生产闭环", "brief": {"aspect_ratio": "9:16", "quality_tier": "draft"},
    }).json()
    episode = client.post(f"/api/v2/short-drama/projects/{project['id']}/episodes", headers=headers, json={
        "title": "第一集", "target_duration": 20,
    }).json()
    scene = client.post(
        f"/api/v2/short-drama/projects/{project['id']}/episodes/{episode['id']}/scenes",
        headers=headers,
        json={"heading": "夜雨", "location_name": "车站", "target_duration": 8},
    ).json()
    shot = client.post(
        f"/api/v2/short-drama/projects/{project['id']}/scenes/{scene['id']}/shots",
        headers=headers,
        json={"visual_description": "女孩在雨中回头", "action": "缓慢回头", "duration": 4, "status": "ready"},
    ).json()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).one()
        code = f"drama_video_{uuid4().hex[:8]}"
        generation_type = GenerationType(code=code, name="短剧视频", media_type="video", enabled=True)
        db.add(generation_type); db.flush()
        workflow = Workflow(
            owner_id=user.id, generation_type_id=generation_type.id, name="镜头视频工作流",
            media_type="video", status="active",
        )
        db.add(workflow); db.flush()
        version = WorkflowVersion(
            workflow_id=workflow.id, version=1,
            api_json={
                "1": {"class_type": "Text", "inputs": {"text": ""}},
                "2": {"class_type": "Duration", "inputs": {"value": 1}},
            },
            param_schema=[
                {"key": "prompt", "label": "提示词", "type": "textarea", "node": "1", "path": "inputs.text", "required": True, "default": ""},
                {"key": "duration", "label": "时长", "type": "int", "node": "2", "path": "inputs.value", "required": True, "default": 1},
            ],
            output_mapping={},
        )
        db.add(version); db.flush()
        workflow.current_version_id = version.id
        generation_type.default_workflow_id = workflow.id
        db.commit()
        return headers, project["id"], shot["id"], generation_type.id
    finally:
        db.close()


def test_compile_create_idempotency_and_multi_output_take_lifecycle() -> None:
    headers, project_id, shot_id, generation_type_id = _setup()
    base = {"shot_ids": [shot_id], "generation_type_id": generation_type_id}

    compiled = client.post(
        f"/api/v2/short-drama/projects/{project_id}/production/compile", headers=headers, json=base,
    )
    assert compiled.status_code == 200, compiled.text
    assert compiled.json()[0]["params"]["duration"] == 4
    assert "女孩在雨中回头" in compiled.json()[0]["params"]["prompt"]
    assert compiled.json()[0]["validation_errors"] == []

    create_body = {**base, "idempotency_key": "first-generation", "submit": False}
    created = client.post(
        f"/api/v2/short-drama/projects/{project_id}/production/tasks", headers=headers, json=create_body,
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["created_task_ids"][0]
    repeated = client.post(
        f"/api/v2/short-drama/projects/{project_id}/production/tasks", headers=headers, json=create_body,
    )
    assert repeated.status_code == 201
    assert repeated.json()["created_task_ids"] == []
    assert repeated.json()["existing_task_ids"] == [task_id]

    db = SessionLocal()
    try:
        task = db.get(Task, task_id); task.status = "SUCCESS"
        for index in (1, 2):
            resource = Resource(
                owner_id=task.user_id, media_type="video", direction="output",
                filename=f"take-{index}.mp4", mime="video/mp4", size=index * 100,
                sha256=f"{index:064d}", storage_key=f"test/take-{index}.mp4",
                width=576, height=1024, duration=4,
            )
            db.add(resource); db.flush()
            db.add(TaskResource(task_id=task.id, resource_id=resource.id, role="output"))
        db.commit()
    finally:
        db.close()

    reconciled = client.post(
        f"/api/v2/short-drama/projects/{project_id}/tasks/{task_id}/reconcile", headers=headers,
    )
    assert reconciled.status_code == 200, reconciled.text
    assert len(reconciled.json()) == 2
    assert all(item["resource"]["width"] == 576 and item["resource"]["duration"] == 4 for item in reconciled.json())
    repeated_sync = client.post(
        f"/api/v2/short-drama/projects/{project_id}/tasks/{task_id}/reconcile", headers=headers,
    )
    assert len(repeated_sync.json()) == 2

    takes = repeated_sync.json(); first, second = takes[0], takes[1]
    selected = client.post(f"/api/v2/short-drama/projects/{project_id}/takes/{first['id']}/select", headers=headers)
    assert selected.status_code == 200 and selected.json()["is_selected"] is True
    assert client.delete(f"/api/v2/short-drama/projects/{project_id}/takes/{first['id']}", headers=headers).status_code == 422
    assert client.post(f"/api/v2/short-drama/projects/{project_id}/takes/{first['id']}/unselect", headers=headers).status_code == 200
    assert client.delete(f"/api/v2/short-drama/projects/{project_id}/takes/{first['id']}", headers=headers).status_code == 200

    regen_body = {"review_note": "动作幅度过小", "parameter_overrides": {"duration": 5}, "idempotency_key": "redo-1"}
    regenerated = client.post(
        f"/api/v2/short-drama/projects/{project_id}/takes/{second['id']}/regenerate", headers=headers, json=regen_body,
    )
    assert regenerated.status_code == 200, regenerated.text
    same = client.post(
        f"/api/v2/short-drama/projects/{project_id}/takes/{second['id']}/regenerate", headers=headers, json=regen_body,
    )
    assert same.status_code == 200 and same.json()["task_id"] == regenerated.json()["task_id"]

    overview = client.get(
        f"/api/v2/short-drama/projects/{project_id}/shots/{shot_id}/production", headers=headers,
    )
    assert overview.status_code == 200
    assert len(overview.json()["takes"]) == 1
    assert len(overview.json()["tasks"]) == 2


def test_successful_comfy_execution_is_not_failed_when_output_registration_breaks() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(username="dispatcher-user", password_hash="x", role="user", status="active")
        node = Node(name="test-node", base_url="http://127.0.0.1:8188", status="online")
        batch = Batch(user_id=None, name="compensation", source="short_drama")
        db.add_all([user, node, batch]); db.flush()
        batch.user_id = user.id
        task = Task(
            batch_id=batch.id, user_id=user.id, params={}, status="QUEUED",
            node_id=node.id, prompt_id="completed-prompt",
        )
        db.add(task); db.flush()
        link = ShotTaskLink(
            owner_id=user.id, shot_id=999, task_id=task.id, purpose="generate",
            status="linked", idempotency_key="dispatch-compensation",
        )
        db.add(link); db.commit()

        class FakeClient:
            async def get_history(self, prompt_id: str) -> dict:
                return {prompt_id: {"status": {"completed": True}, "outputs": {"10": {"images": [{"filename": "done.png"}]}}}}

        class BrokenCollector(Dispatcher):
            def _get_client(self, _node: Node) -> FakeClient: return FakeClient()
            async def _collect_outputs(self, *_args, **_kwargs) -> None: raise RuntimeError("storage temporarily unavailable")
            async def _publish(self, *_args, **_kwargs) -> None: return None

        asyncio.run(BrokenCollector()._finalize_completed(db))
        db.refresh(task); db.refresh(link)
        assert task.status == "SUCCESS"
        assert task.error is None
        assert link.status == "output_collect_failed"
        assert link.sync_attempts == 1
        assert link.output_payload["10"]["images"][0]["filename"] == "done.png"
