from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GenerationTypeConfigSaveIn(BaseModel):
    config: dict[str, Any]


class GenerationTypeConfigVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    generation_type_id: int
    version: int
    status: str
    config: dict[str, Any]
    validation_errors: list[dict[str, Any]]
    source_version_id: int | None
    created_by: int | None
    published_by: int | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ConfigValidationOut(BaseModel):
    valid: bool
    errors: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    workflow_checks: list[dict[str, Any]] = Field(default_factory=list)


class ConfigDiffOut(BaseModel):
    from_version_id: int
    to_version_id: int
    changes: list[dict[str, Any]]


class ConfigRollbackIn(BaseModel):
    source_version_id: int
