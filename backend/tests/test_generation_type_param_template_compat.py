"""Regression coverage for legacy generation-type parameter JSON."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import GenerationType
from app.schemas.schemas import GenerationTypeOut
from app.services.generation_type_service import normalize_param_template, seed_builtin_types


def test_legacy_empty_object_is_normalized_for_generation_type_output() -> None:
    item = GenerationType(
        id=9999, media_type="image", code="legacy-custom", name="旧配置",
        param_template={}, menu_order=999, enabled=True,
    )
    output = GenerationTypeOut.model_validate(item)
    assert output.param_template == []


def test_builtin_legacy_object_recovers_builtin_parameters() -> None:
    parameters = normalize_param_template({}, "t2i")
    assert isinstance(parameters, list)
    assert any(item.get("key") == "prompt" for item in parameters)


def test_seed_does_not_overwrite_existing_parameter_design() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    custom_parameters = [
        {"key": "custom_prompt", "type": "textarea", "label": "自定义提示词"},
    ]
    with Session(engine) as db:
        generation_type = GenerationType(
            media_type="image",
            code="t2i",
            name="文生图",
            menu_order=1,
            enabled=True,
            param_template=custom_parameters,
        )
        db.add(generation_type)
        db.commit()

        seed_builtin_types(db)
        db.refresh(generation_type)

        assert generation_type.param_template == custom_parameters
