from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.v1.resources import generation_info
from app.api.v1.tasks import output_summaries, recheck_task
from app.db import Base
from app.models import Batch, GenerationType, Node, Resource, ShotTaskLink, Task, TaskResource
from app.services import task_service


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _create_batch_and_type(db: Session) -> tuple[Batch, GenerationType]:
    generation_type = GenerationType(
        media_type="image",
        code="test-image",
        name="测试图片生成",
        param_template=[],
    )
    db.add(generation_type)
    db.flush()
    batch = Batch(name="测试批次", generation_type_id=generation_type.id)
    db.add(batch)
    db.flush()
    return batch, generation_type


def test_list_tasks_filters_creation_time_and_generation_type() -> None:
    with _session() as db:
        batch, generation_type = _create_batch_and_type(db)
        now = datetime.now()
        db.add_all([
            Task(
                batch_id=batch.id,
                generation_type_id=generation_type.id,
                status="DRAFT",
                created_at=now,
            ),
            Task(
                batch_id=batch.id,
                generation_type_id=generation_type.id,
                status="SUCCESS",
                created_at=now - timedelta(days=2),
            ),
        ])
        db.commit()

        items, total = task_service.list_tasks(
            db,
            generation_type_id=generation_type.id,
            created_from=now - timedelta(hours=1),
            created_to=now + timedelta(hours=1),
        )

        assert total == 1
        assert items[0].status == "DRAFT"


def test_list_tasks_converts_aware_local_day_boundaries_to_naive_utc() -> None:
    with _session() as db:
        batch, generation_type = _create_batch_and_type(db)
        db.add_all([
            Task(batch_id=batch.id, generation_type_id=generation_type.id, status="DRAFT", created_at=datetime(2026, 8, 12, 15, 59, 59)),
            Task(batch_id=batch.id, generation_type_id=generation_type.id, status="SUCCESS", created_at=datetime(2026, 8, 12, 16, 0, 0)),
        ])
        db.commit()
        china = timezone(timedelta(hours=8))
        items, total = task_service.list_tasks(
            db,
            created_from=datetime(2026, 8, 13, 0, 0, tzinfo=china),
            created_to=datetime(2026, 8, 14, 0, 0, tzinfo=china),
        )
        assert total == 1
        assert items[0].status == "SUCCESS"


def test_list_tasks_can_be_scoped_to_current_user() -> None:
    with _session() as db:
        batch, generation_type = _create_batch_and_type(db)
        db.add_all([
            Task(batch_id=batch.id, user_id=11, generation_type_id=generation_type.id, status="DRAFT"),
            Task(batch_id=batch.id, user_id=22, generation_type_id=generation_type.id, status="DRAFT"),
        ])
        db.commit()

        items, total = task_service.list_tasks(db, user_id=11)

        assert total == 1
        assert items[0].user_id == 11


def test_list_tasks_supports_server_side_keyword_and_pagination() -> None:
    with _session() as db:
        batch, generation_type = _create_batch_and_type(db)
        db.add_all([
            Task(batch_id=batch.id, generation_type_id=generation_type.id, status="SUCCESS", params={"prompt": "分页目标 A"}),
            Task(batch_id=batch.id, generation_type_id=generation_type.id, status="FAILED", params={"prompt": "分页目标 B"}),
            Task(batch_id=batch.id, generation_type_id=generation_type.id, status="SUCCESS", params={"prompt": "其他任务"}),
        ])
        db.commit()

        first, total = task_service.list_tasks(db, limit=1, offset=0, keyword="分页目标")
        second, second_total = task_service.list_tasks(db, limit=1, offset=1, keyword="分页目标")

        assert total == second_total == 2
        assert len(first) == len(second) == 1
        assert first[0].id != second[0].id
        assert "分页目标" in first[0].params["prompt"]
        assert "分页目标" in second[0].params["prompt"]


def test_tasks_can_be_deleted_in_every_lifecycle_state() -> None:
    with _session() as db:
        batch, generation_type = _create_batch_and_type(db)
        draft = Task(batch_id=batch.id, generation_type_id=generation_type.id, status="DRAFT")
        success = Task(batch_id=batch.id, generation_type_id=generation_type.id, status="SUCCESS")
        running = Task(batch_id=batch.id, generation_type_id=generation_type.id, status="RUNNING")
        db.add_all([draft, success, running])
        db.flush()
        resource = Resource(media_type="image", direction="output", filename="kept.png", storage_key="resources/kept.png")
        db.add(resource)
        db.flush()
        db.add(TaskResource(task_id=running.id, resource_id=resource.id, role="output"))
        db.commit()
        draft_id = draft.id
        success_id = success.id
        running_id = running.id

        task_service.delete_task(db, draft)
        task_service.delete_task(db, success)
        task_service.delete_task(db, running)
        assert db.get(Task, draft_id) is None
        assert db.get(Task, success_id) is None
        assert db.get(Task, running_id) is None
        assert db.get(Resource, resource.id) is not None
        assert db.query(TaskResource).filter(TaskResource.task_id == running_id).count() == 0


def test_success_or_failed_task_can_be_regenerated_without_overwriting_source() -> None:
    with _session() as db:
        batch, generation_type = _create_batch_and_type(db)
        source = Task(
            batch_id=batch.id,
            row_no=3,
            generation_type_id=generation_type.id,
            workflow_version_id=None,
            status="SUCCESS",
            priority=7,
            params={"prompt": "一只猫", "seed": 42},
        )
        db.add(source)
        db.commit()

        regenerated = task_service.regenerate(db, source)

        assert regenerated.id != source.id
        assert regenerated.status == "PENDING"
        assert regenerated.params == source.params
        assert regenerated.row_no == source.row_no
        assert regenerated.priority == source.priority
        assert db.get(Task, source.id).status == "SUCCESS"


def test_active_task_cannot_be_regenerated() -> None:
    with _session() as db:
        batch, generation_type = _create_batch_and_type(db)
        task = Task(batch_id=batch.id, generation_type_id=generation_type.id, status="RUNNING")
        db.add(task)
        db.commit()

        with pytest.raises(ValueError, match="仅已完成或失败的任务可以重新生成"):
            task_service.regenerate(db, task)


def test_execute_with_edited_params_creates_new_task_without_changing_source() -> None:
    with _session() as db:
        batch, generation_type = _create_batch_and_type(db)
        source = Task(
            batch_id=batch.id,
            row_no=2,
            generation_type_id=generation_type.id,
            status="SUCCESS",
            priority=4,
            params={"prompt": "原参数", "seed": 1},
        )
        db.add(source)
        db.commit()

        executed = task_service.execute_with_params(db, source, {"prompt": "修改后", "seed": 99})

        assert executed.id != source.id
        assert executed.status == "PENDING"
        assert executed.params == {"prompt": "修改后", "seed": 99}
        assert executed.batch_id == source.batch_id
        assert executed.generation_type_id == source.generation_type_id
        assert db.get(Task, source.id).params == {"prompt": "原参数", "seed": 1}


def test_execute_with_params_preserves_original_multimedia_values() -> None:
    with _session() as db:
        batch, generation_type = _create_batch_and_type(db)
        generation_type.param_template = [
            {"key": "input_image", "type": "image"},
            {"key": "input_video", "type": "video"},
            {"key": "prompt", "type": "textarea"},
        ]
        source = Task(
            batch_id=batch.id,
            generation_type_id=generation_type.id,
            status="SUCCESS",
            params={"input_image": 10, "input_video": 20, "prompt": "原提示词"},
        )
        db.add(source)
        db.commit()

        executed = task_service.execute_with_params(
            db,
            source,
            {"input_image": 99, "input_video": 88, "prompt": "修改后"},
        )

        assert executed.params == {"input_image": 10, "input_video": 20, "prompt": "修改后"}


def test_recheck_uses_one_event_loop_for_comfy_client_and_output_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _session() as db:
        batch, generation_type = _create_batch_and_type(db)
        node = Node(name="test-node", base_url="http://comfy.test")
        db.add(node)
        db.flush()
        task = Task(
            batch_id=batch.id,
            user_id=11,
            generation_type_id=generation_type.id,
            node_id=node.id,
            prompt_id="prompt-1",
            status="FAILED",
        )
        db.add(task)
        db.flush()
        db.add(ShotTaskLink(
            owner_id=11,
            shot_id=999,
            task_id=task.id,
            purpose="director",
            status="linked",
            idempotency_key="recheck-loop-test",
        ))
        db.commit()
        task_id = task.id
        loop_ids: list[int] = []
        shot_sync_calls: list[tuple[str, int]] = []

        class FakeClient:
            def __init__(self, *_args: object) -> None:
                pass

            async def get_history(self, prompt_id: str) -> dict:
                loop_ids.append(id(asyncio.get_running_loop()))
                return {prompt_id: {"status": {"completed": True}, "outputs": {}}}

            async def aclose(self) -> None:
                loop_ids.append(id(asyncio.get_running_loop()))

        async def collect_outputs(*_args: object) -> None:
            loop_ids.append(id(asyncio.get_running_loop()))

        def mark_output_payload(_db: Session, synced_task_id: int, _payload: dict) -> None:
            shot_sync_calls.append(("payload", synced_task_id))

        def reconcile_task_outputs(_db: Session, synced_task_id: int) -> list:
            shot_sync_calls.append(("reconcile", synced_task_id))
            return []

        from app.queue.dispatcher import dispatcher

        monkeypatch.setattr("app.comfy.client.ComfyUIClient", FakeClient)
        monkeypatch.setattr(dispatcher, "_collect_outputs", collect_outputs)
        monkeypatch.setattr("app.short_drama.production_service.mark_output_payload", mark_output_payload)
        monkeypatch.setattr("app.short_drama.production_service.reconcile_task_outputs", reconcile_task_outputs)

        result = asyncio.run(
            recheck_task(task_id, SimpleNamespace(id=11, role="user"), db)  # type: ignore[arg-type]
        )

        assert result["ok"] is True
        assert result["take_sync_pending"] is False
        assert db.get(Task, task_id).status == "SUCCESS"
        assert shot_sync_calls == [("payload", task_id), ("reconcile", task_id)]
        assert len(loop_ids) == 3
        assert len(set(loop_ids)) == 1


def test_generated_resource_returns_source_task_parameters() -> None:
    with _session() as db:
        batch, generation_type = _create_batch_and_type(db)
        task = Task(
            batch_id=batch.id,
            generation_type_id=generation_type.id,
            status="SUCCESS",
            params={"prompt": "一只猫", "width": 1024},
        )
        resource = Resource(
            media_type="image",
            direction="output",
            filename="cat.png",
            storage_key="resources/cat.png",
        )
        db.add_all([task, resource])
        db.flush()
        db.add(TaskResource(task_id=task.id, resource_id=resource.id, role="output"))
        db.commit()

        result = generation_info(resource.id, object(), db)

        assert result["task_id"] == task.id
        assert result["generation_type_name"] == "测试图片生成"
        assert result["params"]["prompt"] == "一只猫"


def test_output_summaries_are_batched_scoped_and_limited_for_task_list() -> None:
    with _session() as db:
        batch, generation_type = _create_batch_and_type(db)
        own = Task(batch_id=batch.id, user_id=11, generation_type_id=generation_type.id, status="SUCCESS")
        other = Task(batch_id=batch.id, user_id=22, generation_type_id=generation_type.id, status="SUCCESS")
        db.add_all([own, other])
        db.flush()
        resources = [
            Resource(owner_id=11, media_type="image", direction="output", filename=f"own-{index}.png", storage_key=f"resources/own-{index}.png")
            for index in range(4)
        ]
        foreign = Resource(owner_id=22, media_type="image", direction="output", filename="foreign.png", storage_key="resources/foreign.png")
        db.add_all([*resources, foreign])
        db.flush()
        db.add_all([TaskResource(task_id=own.id, resource_id=item.id, role="output") for item in resources])
        db.add(TaskResource(task_id=other.id, resource_id=foreign.id, role="output"))
        db.commit()

        result = output_summaries(f"{own.id},{other.id}", SimpleNamespace(id=11, role="user"), db)

        assert set(result) == {own.id}
        assert [item["filename"] for item in result[own.id]] == ["own-0.png", "own-1.png", "own-2.png"]
