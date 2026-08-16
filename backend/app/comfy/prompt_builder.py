"""Prompt 构建器：按 ParamSchema 注入参数到工作流 API JSON。"""
from __future__ import annotations

import copy
import random
import re
from typing import Any

from app.comfy.value_normalizers import normalize_h3_aspect_ratio


def parse_size_value(value: Any) -> tuple[int, int] | None:
    """Parse a maintained size value such as 1088x1920 or 1088×1920."""
    if isinstance(value, dict):
        value = f"{value.get('width', '')}x{value.get('height', '')}"
    match = re.fullmatch(r"\s*(\d+)\s*[xX×*]\s*(\d+)\s*", str(value or ""))
    if not match:
        return None
    width, height = int(match.group(1)), int(match.group(2))
    return (width, height) if width > 0 and height > 0 else None


def _inject(prompt: dict[str, Any], target_spec: dict, value: Any, fallback_key: str) -> None:
    node = prompt.get(str(target_spec.get("node") or ""))
    path = str(target_spec.get("path") or "")
    if node is None or not path:
        return
    parts = path.split(".")
    target = node
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    field = parts[-1]
    if field not in target:
        if fallback_key in target:
            field = fallback_key
        else:
            return
    target[field] = value


def build_prompt(api_json: dict[str, Any], param_schema: list[dict], params: dict[str, Any]) -> dict[str, Any]:
    """根据参数表把用户参数注入到 API JSON 副本，返回可提交的 prompt。

    支持类型：text/textarea/int/float/bool/select/seed/image/video/audio
    image/video/audio 类型参数值为节点文件名（已上传），直接回填。
    seed 类型：未提供且 random=True 时生成随机种子。
    """
    prompt = copy.deepcopy(api_json)
    by_key = {p["key"]: p for p in param_schema}
    effective_params = dict(params)
    for key, value in effective_params.items():
        spec = by_key.get(key)
        if not spec:
            continue
        # 多媒体参数保存的是资源 ID，必须先上传到 ComfyUI，再由调度器写入文件名。
        # 这里直接注入会在错误映射下创建无效字段，并保留工作流原始素材。
        if spec.get("type") in ("image", "video", "audio"):
            continue
        if spec.get("type") == "size":
            parsed = parse_size_value(value)
            if not parsed:
                continue
            targets = spec.get("targets") if isinstance(spec.get("targets"), dict) else {}
            _inject(prompt, targets.get("width") or {}, parsed[0], "width")
            _inject(prompt, targets.get("height") or {}, parsed[1], "height")
            continue
        node_id = str(spec["node"])
        path = spec["path"]  # 如 "inputs.text"
        parts = path.split(".")
        node = prompt.get(node_id)
        if node is None:
            continue
        # H3's ResolutionSelector validates against the complete display value
        # (for example ``16:9 (Widescreen)``). Historical settings and tasks may
        # still contain the former shorthand ``16:9``. Limit the compatibility
        # conversion to H3-backed fields so unrelated aspect-ratio nodes keep
        # their native value format.
        if (
            spec.get("options_from") == "h3_aspect_ratio"
            or (
                key in {"aspect_ratio", "h3_aspect_ratio"}
                and node.get("class_type") == "ResolutionSelector"
            )
        ):
            value = normalize_h3_aspect_ratio(value)
        target = node
        for p in parts[:-1]:
            target = target.setdefault(p, {})
        if spec["type"] == "seed" and (value is None or value == ""):
            if spec.get("random", True):
                value = random.randint(0, 2**32 - 1)
            else:
                value = 0
        field = parts[-1]
        if field not in target:
            if key in target:
                field = key
            elif key == "duration" and "value" in target:
                field = "value"
            else:
                continue
        target[field] = value
    return prompt
