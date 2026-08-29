from __future__ import annotations

import re

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.v1.settings import SelectOptionItemIn
from app.db import Base
from app.models import GenerationType, Setting
from app.services import generation_type_service
from app.comfy.prompt_builder import build_prompt


def test_size_option_catalog_matches_supported_dimensions() -> None:
    image_sizes = generation_type_service.DEFAULT_SELECT_OPTIONS["image_size"]
    video_sizes = generation_type_service.DEFAULT_SELECT_OPTIONS["video_size"]

    assert len(image_sizes) == 11
    assert len(video_sizes) == 17
    assert {item["value"] for item in image_sizes} >= {"1280x720", "1024x1024", "720x1280"}
    assert {item["value"] for item in video_sizes} >= {"832x480", "720x1280", "1792x768"}
    assert all(re.fullmatch(r"\d+x\d+", item["value"]) for item in image_sizes + video_sizes)


def test_h3_aspect_ratio_catalog_matches_supported_values() -> None:
    ratios = generation_type_service.DEFAULT_SELECT_OPTIONS["h3_aspect_ratio"]

    assert [item["value"] for item in ratios] == [
        "1:1 (Square)",
        "2:3 (Portrait Photo)",
        "3:2 (Photo)",
        "3:4 (Portrait Standard)",
        "4:3 (Standard)",
        "9:16 (Portrait Widescreen)",
        "16:9 (Widescreen)",
        "21:9 (Ultrawide)",
    ]
    assert generation_type_service.DEFAULT_SELECT_VALUES["h3_aspect_ratio"] == "16:9 (Widescreen)"
    assert "h3_aspect_ratio" in generation_type_service.MAINTAINABLE_SELECT_OPTION_KEYS


def test_menu_exposes_combined_size_options() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(GenerationType(
            media_type="image",
            code="size-test",
            name="尺寸测试",
            param_template=[],
            enabled=True,
        ))
        db.commit()

        menu = generation_type_service.menu_tree(db)

        assert menu["image"][0]["media_type"] == "image"
        assert menu["image"][0]["size_options"] == generation_type_service.DEFAULT_SELECT_OPTIONS["image_size"]
        assert menu["image"][0]["size_default"] == "1088x1920"


def test_select_option_defaults_are_configurable() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        generation_type_service.save_select_options(
            db,
            "video_fps",
            [{"label": "24 fps", "value": 24}, {"label": "30 fps", "value": 30}],
            30,
        )
        assert generation_type_service.get_select_default(db, "video_fps") == 30


def test_custom_select_option_project_can_be_created_edited_and_deleted() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        project = generation_type_service.create_select_option_project(db, "自定义模型", "string")
        generation_type_service.save_select_options(
            db,
            project["key"],
            [{"label": "模型 A", "value": "model-a"}, {"label": "模型 B", "value": "model-b"}],
            "model-b",
        )

        definitions = generation_type_service.get_select_option_definitions(db)
        assert any(item["key"] == project["key"] and item["custom"] for item in definitions)
        assert generation_type_service.get_select_default(db, project["key"]) == "model-b"
        assert generation_type_service.get_all_select_options(db)[project["key"]][0]["value"] == "model-a"

        generation_type_service.delete_select_option_project(db, project["key"])
        assert not generation_type_service.is_select_option_project(db, project["key"])
        assert db.get(Setting, project["key"]) is None


def test_settings_accepts_string_size_value() -> None:
    item = SelectOptionItemIn(label="16:9 · 1280×720", value="1280x720")
    assert item.value == "1280x720"


def test_video_generation_types_expose_duration_except_motion_transfer() -> None:
    video_codes = [code for media_type, code, _name, _order in generation_type_service.BUILTIN_TYPES if media_type == "video"]
    assert video_codes
    for code in video_codes:
        if code == "motion_transfer":
            assert not any(item["key"] == "duration" for item in generation_type_service.PARAM_TEMPLATES[code])
            continue
        duration = next(item for item in generation_type_service.PARAM_TEMPLATES[code] if item["key"] == "duration")
        assert duration["unit"] == "秒"
        assert duration["default"] == 5
        assert duration["max"] == 15


def test_unmapped_video_params_do_not_override_workflow_owned_values() -> None:
    api_json = {"10": {"class_type": "VideoNode", "inputs": {"length": ["6", 1], "fps": 30}}}

    prompt = build_prompt(api_json, [], {"duration": 5, "length": 121, "fps": 24})

    assert prompt == api_json


def test_composite_size_parameter_injects_width_and_height_targets() -> None:
    api_json = {
        "10": {"class_type": "SizeNode", "inputs": {"width": 512, "height": 512}},
        "11": {"class_type": "Primitive", "inputs": {"value": 1}},
    }
    schema = [{
        "key": "size",
        "type": "size",
        "options_from": "image_size",
        "targets": {
            "width": {"node": "10", "path": "inputs.width"},
            "height": {"node": "11", "path": "inputs.value"},
        },
    }]

    prompt = build_prompt(api_json, schema, {"size": "1088×1920"})

    assert prompt["10"]["inputs"] == {"width": 1088, "height": 512}
    assert prompt["11"]["inputs"]["value"] == 1920


def test_h3_aspect_ratio_shorthand_is_normalized_before_prompt_submission() -> None:
    api_json = {
        "115": {
            "class_type": "ResolutionSelector",
            "inputs": {"aspect_ratio": "1:1 (Square)"},
        },
    }
    schema = [{
        "key": "aspect_ratio",
        "type": "select",
        "options_from": "h3_aspect_ratio",
        "node": "115",
        "path": "inputs.aspect_ratio",
    }]

    prompt = build_prompt(api_json, schema, {"aspect_ratio": "16:9"})

    assert prompt["115"]["inputs"]["aspect_ratio"] == "16:9 (Widescreen)"


def test_seed_select_options_repairs_legacy_h3_values() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Setting(
            key="h3_aspect_ratio",
            value=[{"label": "16:9 (Widescreen)", "value": "16:9"}],
        ))
        db.add(Setting(key="h3_aspect_ratio_default", value="16:9"))
        db.commit()

        generation_type_service.seed_select_options(db)

        assert db.get(Setting, "h3_aspect_ratio").value[0]["value"] == "16:9 (Widescreen)"
        assert db.get(Setting, "h3_aspect_ratio_default").value == "16:9 (Widescreen)"


def test_saving_h3_options_normalizes_legacy_values_immediately() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        generation_type_service.save_select_options(
            db,
            "h3_aspect_ratio",
            [{"label": "16:9 (Widescreen)", "value": "16:9"}],
            "16:9",
        )

        assert db.get(Setting, "h3_aspect_ratio").value[0]["value"] == "16:9 (Widescreen)"
        assert db.get(Setting, "h3_aspect_ratio_default").value == "16:9 (Widescreen)"
