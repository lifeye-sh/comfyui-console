"""Advisory video planning rules. Findings never block task execution."""
from __future__ import annotations

from typing import Any


MAX_VIDEO_DURATION_SECONDS = 15.0
VIDEO_DURATION_KEYS = frozenset({"duration", "video_duration", "seconds"})


def duration_errors(media_type: str | None, params: dict[str, Any] | None) -> list[str]:
    if media_type != "video" or not isinstance(params, dict):
        return []
    errors: list[str] = []
    for key, value in params.items():
        if str(key).strip().lower() not in VIDEO_DURATION_KEYS or value in (None, ""):
            continue
        try:
            duration = float(value)
        except (TypeError, ValueError):
            continue
        if duration > MAX_VIDEO_DURATION_SECONDS:
            errors.append(f"参数“{key}”建议将单次视频时长控制在 15 秒内（不影响继续生成）")
    return errors
