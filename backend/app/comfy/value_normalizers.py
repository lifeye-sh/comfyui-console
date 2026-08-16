"""Normalize maintained UI values to the exact values required by ComfyUI nodes."""
from __future__ import annotations

from typing import Any


H3_ASPECT_RATIO_ALIASES: dict[str, str] = {
    "1:1": "1:1 (Square)",
    "2:3": "2:3 (Portrait Photo)",
    "3:2": "3:2 (Photo)",
    "3:4": "3:4 (Portrait Standard)",
    "4:3": "4:3 (Standard)",
    "9:16": "9:16 (Portrait Widescreen)",
    "16:9": "16:9 (Widescreen)",
    "21:9": "21:9 (Ultrawide)",
}


def normalize_h3_aspect_ratio(value: Any) -> Any:
    """Return the full ResolutionSelector enum while preserving unknown values."""
    if not isinstance(value, str):
        return value
    return H3_ASPECT_RATIO_ALIASES.get(value.strip(), value)
