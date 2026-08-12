"""ComfyUI API JSON 解析：自动识别节点类型、推荐参数映射和输出节点。"""
from __future__ import annotations

from typing import Any

GENERIC_INPUT_FIELDS = {
    "image": "image",
    "video": "video",
    "audio": "audio",
    "text": "text",
    "textarea": "text",
    "float": "Float",
    "int": "value",
    "bool": "value",
    "select": "value",
    "seed": "value",
}


def preferred_input_field(param_type: str) -> str:
    """按平台约定返回自定义输入节点的标准字段名。"""
    return GENERIC_INPUT_FIELDS.get(param_type, "value")


def title_matches_parameter(title: str, key: str, label: str) -> bool:
    """判断节点标题是否对应模板参数，兼容中英文标题与常用别名。"""
    normalized = title.lower().replace("_", "").replace(" ", "")
    candidates = {key.lower().replace("_", ""), label.lower().replace(" ", "")}
    aliases = {
        "frame_rate": ("帧率", "framerate", "fps"),
        "frame_load_cap": ("加载帧数上限", "frameloadcap"),
        "skip_seconds": ("跳过秒数", "跳过", "starttime", "skipseconds"),
        "resolution": ("分辨率", "resolution", "1080p", "720p", "576p", "480p"),
        "motion_algorithm": ("动作算法", "pose计算方式", "pose算法", "algorithm"),
        "expression_enabled": ("表情开启", "开启表情", "expressionenabled"),
        "expression_strength": ("表情强度", "expressionstrength"),
        "camera_enabled": ("运镜开启", "开启运镜", "cameraenabled"),
        "camera_strength": ("运镜强度", "camerastrength"),
        "lora_strength": ("lora强度", "lorastrength"),
        "multi_reference_enabled": ("多参开启", "multireferenceenabled"),
        "multi_reference_count": ("多参图数", "multireferencecount"),
    }
    candidates.update(value.lower().replace(" ", "") for value in aliases.get(key, ()))
    return any(candidate and candidate in normalized for candidate in candidates)


def match_input_field(inputs: dict, param_type: str, explicit_field: str | None = None) -> str | None:
    """明确节点规则优先；通用节点严格按约定字段匹配，且字段必须真实存在。"""
    if explicit_field and explicit_field in inputs:
        return explicit_field
    scalar_candidates = {
        "int": ("value", "Float", "text"),
        "bool": ("value", "Float", "text"),
        "select": ("value", "Float", "text"),
        "seed": ("value", "Float", "text"),
        "float": ("Float", "value", "text"),
    }
    for candidate in scalar_candidates.get(param_type, (preferred_input_field(param_type),)):
        if candidate in inputs:
            return candidate
    # 文本节点历史上也可能使用 value，但仅作为兼容回退。
    if param_type in ("text", "textarea"):
        for candidate in ("text", "value", "Float"):
            if candidate in inputs:
                return candidate
    return None

# ComfyUI 常见节点类型 → 参数类型映射规则
# 当节点的 class_type 匹配时，自动识别对应输入字段的参数类型
NODE_TYPE_RULES: dict[str, dict[str, Any]] = {
    "CLIPTextEncode": {
        "params": {"text": {"type": "textarea", "label": "提示词"}},
        "is_prompt": True,
    },
    "CLIPTextEncodeNegative": {
        "params": {"text": {"type": "textarea", "label": "负面提示词"}},
        "is_negative_prompt": True,
    },
    "KSampler": {
        "params": {
            "seed": {"type": "seed", "label": "随机种子", "random": True},
            "steps": {"type": "int", "label": "采样步数", "default": 20},
            "cfg": {"type": "float", "label": "CFG", "default": 7.0},
            "denoise": {"type": "float", "label": "去噪强度", "default": 1.0},
        },
    },
    "KSamplerAdvanced": {
        "params": {
            "seed": {"type": "seed", "label": "随机种子", "random": True},
            "steps": {"type": "int", "label": "采样步数", "default": 20},
            "cfg": {"type": "float", "label": "CFG", "default": 7.0},
            "denoise": {"type": "float", "label": "去噪强度", "default": 1.0},
        },
    },
    "EmptyLatentImage": {
        "params": {
            "width": {"type": "select", "label": "宽度", "options_from": "image_width", "default": 720},
            "height": {"type": "select", "label": "高度", "options_from": "image_height", "default": 1280},
            "batch_size": {"type": "int", "label": "批次大小", "default": 1},
        },
    },
    "EmptySD3LatentImage": {
        "params": {
            "width": {"type": "select", "label": "宽度", "options_from": "image_width", "default": 1024},
            "height": {"type": "select", "label": "高度", "options_from": "image_height", "default": 1024},
        },
    },
    "EmptyHunyuanLatentVideo": {
        "params": {
            "width": {"type": "select", "label": "宽度", "options_from": "video_width", "default": 848},
            "height": {"type": "select", "label": "高度", "options_from": "video_height", "default": 480},
            "length": {"type": "select", "label": "帧数", "options_from": "video_length", "default": 73},
            "batch_size": {"type": "int", "label": "批次大小", "default": 1},
        },
    },
    "LoadImage": {
        "params": {"image": {"type": "image", "label": "输入图片"}},
        "is_input_image": True,
    },
    "LoadAudio": {
        "params": {"audio": {"type": "audio", "label": "输入音频"}},
    },
    "LoadVideo": {
        "params": {"video": {"type": "video", "label": "输入视频"}},
    },
    "VAEDecode": {
        "is_output": True,
        "output_type": "image",
    },
    "SaveImage": {
        "is_output": True,
        "output_type": "image",
    },
    "SaveAnimatedPNG": {
        "is_output": True,
        "output_type": "image",
    },
    "SaveWEBP": {
        "is_output": True,
        "output_type": "image",
    },
    "VHS_VideoCombine": {
        "is_output": True,
        "output_type": "video",
    },
    "SaveAudio": {
        "is_output": True,
        "output_type": "audio",
    },
}


def parse_api_json(api_json: dict[str, Any]) -> dict[str, Any]:
    """解析 ComfyUI API JSON，返回识别结果：
    - nodes: 所有节点列表（id, class_type, title?）
    - param_schema: 自动推荐的参数映射
    - output_mapping: 自动推荐的输出节点
    - suggested_name: 推荐的工作流名称
    """
    nodes_info: list[dict] = []
    param_schema: list[dict] = []
    output_mapping: dict[str, list[str]] = {}
    has_prompt = False
    has_negative = False
    is_video_workflow = any("video" in str(node.get("class_type", "")).lower() for node in api_json.values())

    for node_id, node in api_json.items():
        class_type = node.get("class_type", "")
        inputs = node.get("inputs", {})
        title = node.get("_meta", {}).get("title", "") if isinstance(node.get("_meta"), dict) else ""

        node_entry: dict = {
            "id": node_id,
            "class_type": class_type,
            "title": title or class_type,
            "inputs": list(inputs.keys()),
        }
        nodes_info.append(node_entry)

        rule = NODE_TYPE_RULES.get(class_type)
        if not rule:
            if is_video_workflow:
                title_lower = title.lower()
                if "duration" in title_lower and "value" in inputs and not any(p["key"] == "duration" for p in param_schema):
                    param_schema.append({
                        "key": "duration", "node": node_id, "path": "inputs.value",
                        "type": "float", "label": "视频时长", "unit": "秒",
                    })
            continue

        # 识别提示词
        rule_params = rule.get("params", {})
        if rule.get("is_prompt") and not has_prompt:
            for field, spec in rule_params.items():
                param_schema.append({
                    "key": "prompt",
                    "node": node_id,
                    "path": f"inputs.{field}",
                    **spec,
                })
            has_prompt = True
        elif rule.get("is_negative_prompt") and not has_negative:
            for field, spec in rule_params.items():
                param_schema.append({
                    "key": "negative_prompt",
                    "node": node_id,
                    "path": f"inputs.{field}",
                    **spec,
                })
            has_negative = True
        else:
            # 通用参数
            for field, spec in rule_params.items():
                # 避免重复 key
                if not any(p["key"] == spec.get("label", field) or p["key"] == field for p in param_schema):
                    key = field
                    param_schema.append({
                        "key": key,
                        "node": node_id,
                        "path": f"inputs.{field}",
                        **spec,
                    })

        # 识别输出节点
        if rule.get("is_output"):
            out_type = rule.get("output_type", "image")
            if out_type not in output_mapping:
                output_mapping[out_type] = []
            output_mapping[out_type].append(node_id)

    # 推荐工作流名称：基于主要采样器或第一个节点的 class_type
    sampler = next((n for n in nodes_info if "Sampler" in n["class_type"]), None)
    if sampler:
        suggested_name = sampler["title"]
    elif nodes_info:
        suggested_name = nodes_info[0]["title"]
    else:
        suggested_name = "未命名工作流"

    return {
        "nodes": nodes_info,
        "param_schema": param_schema,
        "output_mapping": output_mapping,
        "suggested_name": suggested_name,
        "media_type": _guess_media_type(nodes_info, output_mapping),
    }


def _guess_media_type(nodes: list[dict], output_mapping: dict) -> str:
    """根据输出节点猜测媒体类型。"""
    if "video" in output_mapping:
        return "video"
    if "audio" in output_mapping:
        return "audio"
    if "image" in output_mapping:
        return "image"
    # 没有明确输出节点时，根据节点类型猜
    for n in nodes:
        if "Video" in n["class_type"] or "video" in n["class_type"].lower():
            return "video"
        if "Audio" in n["class_type"] or "audio" in n["class_type"].lower():
            return "audio"
    return "image"
