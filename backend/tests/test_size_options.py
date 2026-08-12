from __future__ import annotations

import re

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.v1.settings import SelectOptionItemIn
from app.db import Base
from app.models import GenerationType
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


def test_unmapped_video_params_do_not_override_workflow_owned_values() -> None:
    api_json = {"10": {"class_type": "VideoNode", "inputs": {"length": ["6", 1], "fps": 30}}}

    prompt = build_prompt(api_json, [], {"duration": 5, "length": 121, "fps": 24})

    assert prompt == api_json
