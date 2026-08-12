"""认证、用户、节点、工作流、批次、任务、资源、提示词 Pydantic 模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---- auth ----
class LoginIn(BaseModel):
    username: str
    password: str

class RefreshIn(BaseModel):
    refresh_token: str

class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role: str
    status: str

class UserCreateIn(BaseModel):
    username: str
    password: str
    role: str = "user"

class UserPatchIn(BaseModel):
    password: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None

# ---- nodes ----
class NodeBase(BaseModel):
    name: str
    base_url: str
    ws_url: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    max_concurrent: int = 1

class NodeCreateIn(NodeBase):
    pass

class NodePatchIn(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    ws_url: Optional[str] = None
    tags: Optional[list[str]] = None
    max_concurrent: Optional[int] = None
    status: Optional[str] = None

class NodeOut(NodeBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str

# ---- workflows ----
class WorkflowVersionIn(BaseModel):
    ui_json: Optional[dict] = None
    api_json: dict
    param_schema: list[dict] = Field(default_factory=list)
    output_mapping: dict = Field(default_factory=dict)

class WorkflowCreateIn(BaseModel):
    name: str
    description: str = ""
    media_type: str = "image"
    generation_type_id: Optional[int] = None
    tags: list[str] = Field(default_factory=list)

class WorkflowPatchIn(BaseModel):
    name: Optional[str] = None

class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str
    media_type: str
    generation_type_id: Optional[int]
    tags: list[str]
    status: str
    current_version_id: Optional[int]

class WorkflowVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    workflow_id: int
    version: int
    param_schema: list[dict]
    output_mapping: dict

# ---- generation types ----
class GenerationTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    media_type: str
    code: str
    name: str
    default_workflow_id: Optional[int]
    param_template: list
    menu_order: int
    enabled: bool

class DefaultWorkflowIn(BaseModel):
    workflow_version_id: int

class GenerationTypePatchIn(BaseModel):
    param_template: Optional[dict] = None
    enabled: Optional[bool] = None
    menu_order: Optional[int] = None

# ---- batches & tasks ----
class BatchRowIn(BaseModel):
    row_no: int = 0
    generation_type_id: Optional[int] = None
    workflow_version_id: Optional[int] = None
    params: dict = Field(default_factory=dict)

class BatchCreateIn(BaseModel):
    name: str = ""
    generation_type_id: Optional[int] = None
    workflow_version_id: Optional[int] = None
    global_params: dict = Field(default_factory=dict)
    rows: list[BatchRowIn] = Field(default_factory=list)

class BatchPatchIn(BaseModel):
    name: Optional[str] = None
    global_params: Optional[dict] = None

class BatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    generation_type_id: Optional[int]
    workflow_version_id: Optional[int]
    global_params: dict
    source: str
    is_template: bool
    submitted_at: Optional[datetime]

class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    batch_id: int
    row_no: int
    generation_type_id: Optional[int]
    workflow_version_id: Optional[int]
    params: dict
    status: str
    priority: int
    node_id: Optional[int]
    prompt_id: Optional[str]
    retries: int
    error: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime

class TaskExecuteIn(BaseModel):
    params: dict = Field(default_factory=dict)

class TaskEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: str
    progress: int
    payload: dict
    created_at: datetime

# ---- resources ----
class ResourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    owner_id: Optional[int]
    folder_id: Optional[int]
    media_type: str
    direction: str
    filename: str
    mime: str
    size: int
    sha256: Optional[str]
    thumb_key: Optional[str]
    width: Optional[int]
    height: Optional[int]
    duration: Optional[int]
    visibility: str
    created_at: datetime

class ResourcePatchIn(BaseModel):
    visibility: Optional[str] = None

# ---- prompts ----
class PromptCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    sort_order: int

class PromptCategoryCreateIn(BaseModel):
    name: str

class PromptCreateIn(BaseModel):
    name: str
    content: str
    negative_content: str = ""
    category_id: Optional[int] = None
    tags: list[str] = Field(default_factory=list)
    remark: str = ""
    visibility: str = "private"

class PromptPatchIn(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    negative_content: Optional[str] = None
    category_id: Optional[int] = None
    tags: Optional[list[str]] = None
    remark: Optional[str] = None
    visibility: Optional[str] = None

class PromptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    owner_id: Optional[int]
    name: str
    content: str
    negative_content: str
    category_id: Optional[int]
    tags: list[str]
    remark: str
    visibility: str

# ---- shares ----
class ShareCreateIn(BaseModel):
    resource_id: int
    password: Optional[str] = None
    expires_hours: Optional[int] = None
    allow_download: bool = True

class ShareOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    resource_id: int
    token: str
    expires_at: Optional[datetime]
    allow_download: bool
    created_by: Optional[int]
    revoked_at: Optional[datetime]

# ---- audit ----
class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: Optional[int]
    action: str
    target_type: Optional[str]
    target_id: Optional[int]
    detail: Optional[str]
    ip: Optional[str]
    created_at: datetime
