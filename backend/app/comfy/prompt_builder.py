"""Prompt 构建器：按 ParamSchema 注入参数到工作流 API JSON。"""
from __future__ import annotations

import copy
import random
from typing import Any


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
        node_id = str(spec["node"])
        path = spec["path"]  # 如 "inputs.text"
        parts = path.split(".")
        node = prompt.get(node_id)
        if node is None:
            continue
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
