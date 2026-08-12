from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.v1.resources import generation_info
from app.db import Base
from app.models import Batch, GenerationType, Resource, Task, TaskResource
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


def test_only_draft_task_can_be_deleted() -> None:
    with _session() as db:
        batch, generation_type = _create_batch_and_type(db)
        draft = Task(batch_id=batch.id, generation_type_id=generation_type.id, status="DRAFT")
        success = Task(batch_id=batch.id, generation_type_id=generation_type.id, status="SUCCESS")
        db.add_all([draft, success])
        db.commit()
        draft_id = draft.id

        task_service.delete_draft(db, draft)
        assert db.get(Task, draft_id) is None
        with pytest.raises(ValueError, match="仅草稿任务可以删除"):
            task_service.delete_draft(db, success)


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
