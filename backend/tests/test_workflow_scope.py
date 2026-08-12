from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import GenerationType
from app.schemas.schemas import BatchCreateIn, BatchRowIn, WorkflowCreateIn, WorkflowVersionIn
from app.services import batch_service, generation_type_service, workflow_service


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _generation_type(db: Session, code: str, name: str) -> GenerationType:
    item = GenerationType(
        media_type="image",
        code=code,
        name=name,
        param_template=[],
        enabled=True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _workflow_with_version(db: Session, generation_type: GenerationType, name: str):
    workflow = workflow_service.create_workflow(db, WorkflowCreateIn(
        name=name,
        media_type="image",
        generation_type_id=generation_type.id,
    ), owner_id=None)
    version = workflow_service.add_version(db, workflow.id, WorkflowVersionIn(
        api_json={},
        param_schema=[],
        output_mapping={},
    ))
    return workflow, version


def test_workflow_list_is_strictly_scoped_by_generation_type() -> None:
    with _session() as db:
        text_to_image = _generation_type(db, "scope-t2i", "文生图")
        image_to_image = _generation_type(db, "scope-i2i", "图生图")
        own, _ = _workflow_with_version(db, text_to_image, "文生图工作流")
        _workflow_with_version(db, image_to_image, "图生图工作流")

        result = workflow_service.list_workflows(db, generation_type_code="scope-t2i")

        assert [workflow.id for workflow in result] == [own.id]


def test_default_workflow_must_belong_to_same_generation_type() -> None:
    with _session() as db:
        text_to_image = _generation_type(db, "default-t2i", "文生图")
        image_to_image = _generation_type(db, "default-i2i", "图生图")
        _, foreign_version = _workflow_with_version(db, image_to_image, "图生图工作流")

        with pytest.raises(ValueError, match="当前生成类型自己的工作流"):
            generation_type_service.set_default_workflow(db, text_to_image, foreign_version.id)


def test_row_workflow_selection_is_saved_and_used() -> None:
    with _session() as db:
        generation_type = _generation_type(db, "row-workflow", "行工作流")
        _, version = _workflow_with_version(db, generation_type, "指定工作流")
        batch = batch_service.create_batch(db, BatchCreateIn(
            name="指定工作流批次",
            generation_type_id=generation_type.id,
            rows=[BatchRowIn(
                generation_type_id=generation_type.id,
                workflow_version_id=version.id,
                params={"prompt": "test"},
            )],
        ), user_id=None)

        assert batch.tasks[0].workflow_version_id == version.id
        result = batch_service.submit_batch(db, batch)
        assert result["enqueued"] == 1
        assert batch.tasks[0].workflow_version_id == version.id
        assert batch.tasks[0].status == "PENDING"


def test_workflow_name_can_be_updated() -> None:
    with _session() as db:
        generation_type = _generation_type(db, "rename-workflow", "重命名类型")
        workflow, _ = _workflow_with_version(db, generation_type, "旧名称")

        updated = workflow_service.patch_workflow(db, workflow, "  新名称  ")

        assert updated.name == "新名称"
        with pytest.raises(ValueError, match="名称不能为空"):
            workflow_service.patch_workflow(db, updated, "   ")
