from __future__ import annotations

import asyncio
import io

from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.v1.workflows import parse_json
from app.comfy.prompt_builder import build_prompt
from app.db import Base
from app.models import Batch, GenerationType, Resource, Task, TaskResource
from app.queue import dispatcher as dispatcher_module
from app.queue.dispatcher import Dispatcher
from app.storage.local_fs import LocalFSStorage


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (64, 64), "#336699").save(output, format="PNG")
    return output.getvalue()


class FakeClient:
    async def upload_image(self, data: bytes, filename: str) -> dict:
        return {"name": "selected.png", "subfolder": "inputs", "type": "input"}

    async def get_view_bytes(self, filename: str, subfolder: str = "", type_: str = "output") -> bytes:
        return _png_bytes() if filename.endswith(".png") else b"media-content"


def test_multimedia_resource_id_is_not_injected_into_prompt() -> None:
    api_json = {"10": {"class_type": "LoadImage", "inputs": {"image": "original.png"}}}
    schema = [{
        "key": "input_image",
        "type": "image",
        "node": "10",
        "path": "inputs.input_image",
    }]

    prompt = build_prompt(api_json, schema, {"input_image": 123})

    assert prompt["10"]["inputs"] == {"image": "original.png"}


def test_video_params_fix_legacy_duration_mapping_but_preserve_workflow_defaults() -> None:
    api_json = {
        "1": {"class_type": "MiniMaxVideo", "inputs": {
            "width": ["18", 0], "height": ["18", 1], "length": ["6", 1],
        }},
        "11": {"class_type": "PrimitiveFloat", "inputs": {"value": 15}, "_meta": {"title": "Float (duration)"}},
        "12": {"class_type": "CreateVideo", "inputs": {"fps": 30}},
    }
    schema = [{
        "key": "duration", "type": "int", "node": "11", "path": "inputs.duration",
    }]

    prompt = build_prompt(api_json, schema, {
        "duration": 5, "width": 720, "height": 1280, "length": 121, "fps": 24,
    })

    assert prompt["11"]["inputs"] == {"value": 5}
    assert prompt["1"]["inputs"] == {
        "width": ["18", 0], "height": ["18", 1], "length": ["6", 1],
    }
    assert prompt["12"]["inputs"]["fps"] == 30


def test_legacy_image_mapping_replaces_real_load_image_input(tmp_path, monkeypatch) -> None:
    storage = LocalFSStorage(str(tmp_path))
    monkeypatch.setattr(dispatcher_module, "get_storage", lambda: storage)
    storage.save_bytes(_png_bytes(), "inputs/source.png")

    with _session() as db:
        batch = Batch(name="input test")
        resource = Resource(
            media_type="image",
            direction="input",
            filename="source.png",
            storage_key="inputs/source.png",
        )
        db.add_all([batch, resource])
        db.flush()
        task = Task(batch_id=batch.id, status="PENDING", params={"input_image": resource.id})
        db.add(task)
        db.commit()
        prompt = {"10": {"class_type": "LoadImage", "inputs": {"image": "original.png"}}}
        schema = [{
            "key": "input_image",
            "type": "image",
            "node": "10",
            "path": "inputs.input_image",
        }]

        result = asyncio.run(Dispatcher()._upload_inputs(db, FakeClient(), prompt, schema, task))

        assert result["10"]["inputs"]["image"] == "inputs/selected.png"
        assert "input_image" not in result["10"]["inputs"]
        link = db.query(TaskResource).filter_by(task_id=task.id, role="input").one()
        assert link.resource_id == resource.id


def test_parser_maps_template_image_to_actual_loader_field() -> None:
    with _session() as db:
        result = parse_json(object(), {
            "generation_type_code": "i2i",
            "api_json": {
                "10": {"class_type": "LoadImage", "inputs": {"image": "original.png"}},
                "20": {"class_type": "SaveImage", "inputs": {}},
            },
        }, db)

        input_image = next(item for item in result["param_schema"] if item["key"] == "input_image")
        assert input_image["node"] == "10"
        assert input_image["path"] == "inputs.image"


def test_parser_without_generation_type_uses_automatic_detection() -> None:
    with _session() as db:
        result = parse_json(object(), {
            "api_json": {
                "10": {"class_type": "LoadImage", "inputs": {"image": "original.png"}},
                "20": {"class_type": "SaveImage", "inputs": {}},
            },
        }, db)

        assert any(node["id"] == "10" for node in result["nodes"])
        assert result["output_mapping"]["image"] == ["20"]
        assert result["media_type"] == "image"


def test_parser_uses_conventional_input_fields_for_custom_nodes() -> None:
    with _session() as db:
        result = parse_json(object(), {
            "generation_type_code": "motion_transfer",
            "api_json": {
                "1": {"class_type": "easy int", "inputs": {"value": 24}, "_meta": {"title": "帧率"}},
                "2": {"class_type": "easy boolean", "inputs": {"value": True}, "_meta": {"title": "表情开启"}},
                "3": {"class_type": "CYBERPUNKHT", "inputs": {"Float": 0.8}, "_meta": {"title": "表情强度"}},
                "4": {"class_type": "VHS_LoadVideoFFmpeg", "inputs": {"video": "old.mp4"}, "_meta": {"title": "原始视频"}},
                "5": {"class_type": "LoadImage", "inputs": {"image": "old.png"}, "_meta": {"title": "目标人物图"}},
                "6": {"class_type": "PrimitiveFloat", "inputs": {"value": 0}, "_meta": {"title": "跳过秒数"}},
            },
        }, db)

        schema = {item["key"]: item for item in result["param_schema"]}
        assert schema["frame_rate"]["path"] == "inputs.value"
        assert schema["expression_enabled"]["path"] == "inputs.value"
        assert schema["expression_strength"]["path"] == "inputs.Float"
        assert schema["source_video"]["path"] == "inputs.video"
        assert schema["target_image"]["path"] == "inputs.image"
        assert schema["skip_seconds"]["path"] == "inputs.value"
        assert schema["skip_seconds"]["node"] == "6"


def test_scalar_parser_accepts_value_float_or_text_by_existing_node_field() -> None:
    with _session() as db:
        result = parse_json(object(), {
            "generation_type_code": "motion_transfer",
            "api_json": {
                "1": {"class_type": "Custom", "inputs": {"text": "30"}, "_meta": {"title": "帧率"}},
                "2": {"class_type": "Custom", "inputs": {"Float": 1}, "_meta": {"title": "表情开启"}},
                "3": {"class_type": "Custom", "inputs": {"value": 0.8}, "_meta": {"title": "表情强度"}},
            },
        }, db)
        schema = {item["key"]: item for item in result["param_schema"]}
        assert schema["frame_rate"]["path"] == "inputs.text"
        assert schema["expression_enabled"]["path"] == "inputs.Float"
        assert schema["expression_strength"]["path"] == "inputs.value"


def test_v2_parser_uses_supplied_draft_parameters_instead_of_legacy_template() -> None:
    with _session() as db:
        result = parse_json(object(), {
            "generation_type_code": "t2i",
            "parameters": [
                {"key": "custom_strength", "type": "float", "label": "自定义强度", "help": "页面说明"},
                {"key": "reference", "type": "image", "label": "参考图"},
            ],
            "api_json": {
                "1": {"class_type": "Custom", "inputs": {"Float": 0.7}, "_meta": {"title": "自定义强度"}},
                "2": {"class_type": "LoadImage", "inputs": {"image": "old.png"}, "_meta": {"title": "参考图"}},
            },
        }, db)

        schema = {item["key"]: item for item in result["param_schema"]}
        assert set(schema) == {"custom_strength", "reference"}
        assert schema["custom_strength"]["path"] == "inputs.Float"
        assert schema["reference"]["path"] == "inputs.image"
        assert "help" not in schema["custom_strength"]


def test_parser_maps_text_and_audio_to_standard_fields() -> None:
    with _session() as db:
        result = parse_json(object(), {
            "generation_type_code": "digital_human",
            "api_json": {
                "1": {"class_type": "CustomText", "inputs": {"text": "hello"}, "_meta": {"title": "正向提示词"}},
                "2": {"class_type": "LoadAudio", "inputs": {"audio": "voice.wav"}, "_meta": {"title": "音频1"}},
            },
        }, db)
        schema = {item["key"]: item for item in result["param_schema"]}
        assert schema["prompt"]["path"] == "inputs.text"
        assert schema["audio_1"]["path"] == "inputs.audio"


def test_task_collects_multiple_image_and_video_outputs(tmp_path, monkeypatch) -> None:
    storage = LocalFSStorage(str(tmp_path))
    monkeypatch.setattr(dispatcher_module, "get_storage", lambda: storage)

    with _session() as db:
        batch = Batch(name="output test")
        db.add(batch)
        db.flush()
        task = Task(batch_id=batch.id, status="RUNNING", params={})
        db.add(task)
        db.commit()
        outputs = {
            "30": {"images": [
                {"filename": "first.png", "type": "output"},
                {"filename": "second.png", "type": "output"},
            ]},
            "40": {
                "videos": [{"filename": "clip.mp4", "type": "output"}],
                "gifs": [{"filename": "clip.mp4", "type": "output"}],
            },
        }

        asyncio.run(Dispatcher()._collect_outputs(db, task, FakeClient(), outputs))
        db.flush()

        links = db.query(TaskResource).filter_by(task_id=task.id, role="output").all()
        resources = [db.get(Resource, link.resource_id) for link in links]
        assert len(resources) == 3
        assert [resource.media_type for resource in resources].count("image") == 2
        assert [resource.media_type for resource in resources].count("video") == 1
        assert next(resource for resource in resources if resource.media_type == "video").mime == "video/mp4"
