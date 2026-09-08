"""Schemas for staged short-drama Markdown imports."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

StructuredDataType = Literal["script", "assets", "video_prompts"]


class StructuredImportPreviewOut(BaseModel):
    data_type: StructuredDataType
    filename: str
    checksum: str
    parsed_data: dict[str, Any]


class StructuredImportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    owner_id: int
    project_id: int
    batch_key: str
    data_type: str
    filename: str
    checksum: str
    parsed_data: dict[str, Any]
    status: str
    error: str
    created_at: datetime
    updated_at: datetime


class StructuredImportApplyOut(BaseModel):
    item: StructuredImportOut
    applied_counts: dict[str, int]
    idempotent: bool = False
