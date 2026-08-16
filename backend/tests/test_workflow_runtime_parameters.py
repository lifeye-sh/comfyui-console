from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import GenerationType
from app.schemas.schemas import BatchCreateIn, BatchRowIn, WorkflowCreateIn, WorkflowVersionIn
from app.services import batch_service, generation_type_config_service, workflow_service


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _workflow(db: Session, generation_type: GenerationType, name: str, schema: list[dict]):
    workflow = workflow_service.create_workflow(
        db,
        WorkflowCreateIn(name=name, media_type="image", generation_type_id=generation_type.id),
        owner_id=None,
    )
    version = workflow_service.add_version(
        db,
        workflow.id,
        WorkflowVersionIn(
            api_json={"1": {"class_type": "TestNode", "inputs": {"text": ""}}},
            param_schema=schema,
            output_mapping={},
        ),
    )
    return workflow, version


def test_runtime_config_keeps_parameters_with_each_pinned_workflow() -> None:
    with _session() as db:
        generation_type = GenerationType(
            media_type="image", code="dynamic-forms", name="动态表单", param_template=[], enabled=True
        )
        db.add(generation_type)
        db.commit()
        db.refresh(generation_type)
        first, first_version = _workflow(db, generation_type, "提示词工作流", [
            {"key": "prompt", "label": "提示词", "type": "textarea", "required": True, "node": "1", "path": "inputs.text"}
        ])
        second, second_version = _workflow(db, generation_type, "标题工作流", [
            {"key": "title", "label": "标题", "type": "text", "required": True, "node": "1", "path": "inputs.text"}
        ])
        config = {
            "schema_version": 2,
            "parameters": [],
            "parameter_schemes": [],
            "workflow_bindings": [
                {"workflow_id": first.id, "workflow_version_id": first_version.id, "is_default": True},
                {"workflow_id": second.id, "workflow_version_id": second_version.id, "is_default": False},
            ],
        }

        runtime = generation_type_config_service.build_runtime_workflows(db, generation_type, config)

        assert [item["workflow_version_id"] for item in runtime] == [first_version.id, second_version.id]
        assert [item["parameters"][0]["key"] for item in runtime] == ["prompt", "title"]
        assert runtime[0]["is_default"] is True


def test_batch_validates_against_selected_workflow_schema() -> None:
    with _session() as db:
        generation_type = GenerationType(
            media_type="image", code="workflow-validation", name="工作流校验", param_template=[], enabled=True
        )
        db.add(generation_type)
        db.commit()
        db.refresh(generation_type)
        _, version = _workflow(db, generation_type, "标题工作流", [
            {"key": "title", "label": "标题", "type": "text", "required": True, "node": "1", "path": "inputs.text"}
        ])
        batch = batch_service.create_batch(
            db,
            BatchCreateIn(
                name="动态参数批次",
                generation_type_id=generation_type.id,
                rows=[
                    BatchRowIn(workflow_version_id=version.id, params={"title": "有效", "unknown": "丢弃"}),
                    BatchRowIn(workflow_version_id=version.id, params={"prompt": "错误字段"}),
                ],
            ),
            user_id=None,
        )

        result = batch_service.submit_batch(db, batch)

        assert result == {"ok": True, "enqueued": 1, "invalid": 1}
        assert batch.tasks[0].params == {"title": "有效"}
        assert batch.tasks[1].status == "DRAFT"
        assert "缺少必填参数：标题" in (batch.tasks[1].error or "")


def test_composite_size_is_validated_and_normalized_for_selected_workflow() -> None:
    with _session() as db:
        generation_type = GenerationType(
            media_type="image", code="composite-size", name="复合尺寸", param_template=[], enabled=True
        )
        db.add(generation_type)
        db.commit()
        db.refresh(generation_type)
        _, version = _workflow(db, generation_type, "尺寸工作流", [{
            "key": "size", "label": "图片尺寸", "type": "size", "required": True,
            "options_from": "image_size",
            "targets": {
                "width": {"node": "1", "path": "inputs.text"},
                "height": {"node": "1", "path": "inputs.text"},
            },
        }])
        batch = batch_service.create_batch(
            db,
            BatchCreateIn(
                name="尺寸批次",
                generation_type_id=generation_type.id,
                rows=[
                    BatchRowIn(workflow_version_id=version.id, params={"size": "1088×1920"}),
                    BatchRowIn(workflow_version_id=version.id, params={"size": "111x222"}),
                ],
            ),
            user_id=None,
        )

        result = batch_service.submit_batch(db, batch)

        assert result["enqueued"] == 1
        assert result["invalid"] == 1
        assert batch.tasks[0].params == {"size": "1088x1920"}
        assert "不是有效选项" in (batch.tasks[1].error or "")


def test_composite_size_configuration_requires_both_targets() -> None:
    with _session() as db:
        generation_type = GenerationType(
            media_type="image", code="size-config", name="尺寸配置", param_template=[], enabled=True
        )
        db.add(generation_type)
        db.commit()
        db.refresh(generation_type)
        workflow, version = _workflow(db, generation_type, "缺少高度映射", [{
            "key": "size", "label": "图片尺寸", "type": "size", "required": True,
            "options_from": "image_size",
            "targets": {
                "width": {"node": "1", "path": "inputs.text"},
                "height": {"node": "", "path": ""},
            },
        }])
        config = generation_type_config_service.build_default_config(db, generation_type)
        config["schema_version"] = 2
        config["workflow_bindings"] = [{
            "workflow_id": workflow.id, "workflow_version_id": version.id, "is_default": True,
        }]

        result = generation_type_config_service.validate_config(db, generation_type, config)

        assert result["valid"] is False
        assert any(item["path"].endswith("targets.height") for item in result["errors"])
