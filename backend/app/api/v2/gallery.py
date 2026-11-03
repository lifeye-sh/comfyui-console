"""Workflow bindings and idempotent submission for the gallery subproject."""
from uuid import UUID, uuid4
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from app.core.deps import AdminUser, CurrentUser, DBSession
from app.models import Batch, Task, Setting, Workflow, WorkflowVersion, GenerationType, Resource, ImageProviderConfig
from app.services import batch_service, workflow_service

router = APIRouter(prefix="/gallery", tags=["gallery"])
KEY = "gallery_workflow"
Mode = Literal["all", "outfit", "pose"]
MODE_ROLES = {"all": {"portrait", "costume", "pose"}, "outfit": {"portrait", "costume"}, "pose": {"portrait", "pose"}}


def config_key(mode: Mode):
    return KEY if mode == "all" else f"{KEY}_{mode}"
Role = Literal["portrait", "costume", "pose", "extras", "composite"]


class Binding(BaseModel):
    workflow_version_id: int
    prompt_key: str
    mapping: dict[Role, str]


def targets(db):
    return db.query(WorkflowVersion, Workflow).join(Workflow, WorkflowVersion.workflow_id == Workflow.id).join(
        GenerationType, GenerationType.id == Workflow.generation_type_id).filter(
        Workflow.media_type == "image", GenerationType.enabled.is_(True), GenerationType.deleted_at.is_(None))


def definition(db, binding):
    pair = targets(db).filter(WorkflowVersion.id == binding.workflow_version_id).first()
    if not pair:
        raise HTTPException(422, "工作流版本不可用")
    version, workflow = pair
    fields = {p["key"]: p for p in version.param_schema or []}
    if fields.get(binding.prompt_key, {}).get("type") not in ("text", "textarea"):
        raise HTTPException(422, "请选择提示词参数")
    if not binding.mapping or any(fields.get(k, {}).get("type") != "image" for k in binding.mapping.values()):
        raise HTTPException(422, "请选择有效的图片输入")
    if "composite" in binding.mapping and set(binding.mapping) & {"portrait","costume","pose"}:
        raise HTTPException(422, "拼图与三个独立参考槽不能同时映射")
    return version, workflow, fields


@router.get("/workflows")
def workflows(user: AdminUser, db: DBSession):
    return [{"id": v.id, "name": w.name, "version": v.version, "parameters": v.param_schema}
            for v,w in targets(db).order_by(Workflow.name, WorkflowVersion.id.desc())]


@router.get("/config")
def config(user: CurrentUser, db: DBSession, mode: Mode = "all"):
    setting = db.get(Setting, config_key(mode))
    if not setting:
        return None
    version, workflow, _ = definition(db, Binding(**setting.value))
    return {**setting.value, "name": workflow.name, "parameters": version.param_schema}


@router.put("/config")
def publish(body: Binding, user: AdminUser, db: DBSession, mode: Mode = "all"):
    definition(db, body)
    slots = set(body.mapping) - {"extras", "composite"}
    if mode != "all" and "composite" not in body.mapping and slots != MODE_ROLES[mode]:
        raise HTTPException(422, "请完整绑定当前双图组合的两个槽位")
    value = {**body.model_dump(), "revision": uuid4().hex}
    db.merge(Setting(key=config_key(mode), value=value))
    db.commit()
    return value


class Request(BaseModel):
    mode: Mode | None = None
    request_id: UUID
    revision: str = ""
    provider_id: int | None = Field(default=None, gt=0)
    prompt: str = Field(min_length=1, max_length=30000)
    refs: dict[Role, list[int]]
    selection: dict[str, str] = Field(default_factory=dict)
    options: dict = Field(default_factory=dict)


@router.post("/generations")
def generate(body: Request, user: CurrentUser, db: DBSession):
    key = f"{user.id}:{body.request_id}"
    def existing():
        row = db.query(Task).join(Batch).filter(Batch.request_key == key, Task.user_id == user.id).first()
        return {"task_id": row.id, "batch_id": row.batch_id} if row else None
    prior = existing()
    if prior:
        return prior
    if body.provider_id is None:
        type_id, version_id, clean, snapshot = comfy_inputs(body,user,db)
    else:
        type_id, version_id, clean, snapshot = provider_inputs(body,user,db)
    batch = Batch(user_id=user.id, name="AI角色图库 · "+body.prompt[:48], source="gallery",
                  request_key=key, generation_type_id=type_id, workflow_version_id=version_id,
                  global_params={"gallery_recipe":body.model_dump(mode="json"), "binding":snapshot})
    task = Task(user_id=user.id,row_no=0,generation_type_id=type_id,workflow_version_id=version_id,
                params=clean,status="DRAFT")
    batch.tasks.append(task)
    db.add(batch)
    try:
        db.flush()
        result = batch_service.submit_batch(db,batch,commit=False)
        if not result["enqueued"]:
            raise HTTPException(422,task.error or "入队失败")
        db.commit()
    except IntegrityError:
        db.rollback()
        prior = existing()
        if prior: return prior
        raise
    return {"task_id":task.id,"batch_id":batch.id}


def provider_inputs(body,user,db):
    from app.services.generation_type_service import get_select_options
    provider = db.get(ImageProviderConfig,body.provider_id)
    mixed = db.query(GenerationType).filter_by(code="mixed",enabled=True,deleted_at=None).first()
    if not provider or not provider.enabled or not mixed:
        raise HTTPException(422,"图片提供方或混合生图未启用")
    expected = MODE_ROLES[body.mode or "all"]
    if {r for r,ids in body.refs.items() if ids and r != "extras"} != expected:
        raise HTTPException(422,"参考图片与所选组合不一致")
    refs = []
    for role in ("portrait","costume","pose","extras"):
        ids = body.refs.get(role,[])
        if role in expected and len(ids) != 1:
            raise HTTPException(422,"每个主要参考槽需要一张图")
        for rid in ids:
            resource = db.get(Resource,rid)
            if not resource or resource.owner_id != user.id or resource.deleted_at or resource.media_type != "image":
                raise HTTPException(422,"参考图片不可用")
        refs.extend(ids)
    size = body.options.get("size")
    if set(body.options) != {"size"} or size not in [str(o["value"]) for o in get_select_options(db,"image_size")]:
        raise HTTPException(422,"请选择有效的图片尺寸")
    params = {"__execution_provider":"gemini_image","__provider_config_id":provider.id,
              "prompt":body.prompt,"reference_resource_ids":refs,"size":size}
    return mixed.id,None,params,{"provider":provider.name,"model":provider.model}


def comfy_inputs(body,user,db):
    cfg = config(user, db, body.mode or "all")
    if not cfg or cfg["revision"] != body.revision:
        raise HTTPException(409, "图库工作流配置已变更，请刷新")
    binding = Binding(**cfg)
    if body.mode:
        expected = {"composite"} if "composite" in binding.mapping else MODE_ROLES[body.mode]
        if {role for role, ids in body.refs.items() if ids and role != "extras"} != expected:
            raise HTTPException(422, "参考图片与所选组合不一致")
    version, workflow, fields = definition(db, binding)
    params = {k: p["default"] for k,p in fields.items() if p.get("default") is not None}
    for k,v in body.options.items():
        if k not in fields or fields[k]["type"] in ("image","video","audio") or k == binding.prompt_key:
            raise HTTPException(422, "无效的工作流参数")
        params[k] = v
    params[binding.prompt_key] = body.prompt
    grouped = {}
    for role in ("portrait","costume","pose","composite","extras"):
        ids = body.refs.get(role, [])
        if not ids: continue
        slot = binding.mapping.get(role)
        if not slot or (role != "extras" and len(ids) != 1):
            raise HTTPException(422, f"参考槽未配置或数量不符：{role}")
        for rid in ids:
            r = db.get(Resource,rid)
            if not r or r.owner_id != user.id or r.deleted_at or r.media_type != "image":
                raise HTTPException(422, "参考图片不可用")
        grouped.setdefault(slot, []).extend(ids)
    for slot, ids in grouped.items():
        if len(ids)>1 and not fields[slot].get("multiple"):
            raise HTTPException(422, f"{slot} 只接受一张图片")
        params[slot] = ids if fields[slot].get("multiple") else ids[0]
    clean, errors = workflow_service.validate_task_params(db,version,params,user.id)
    if errors:
        raise HTTPException(422, "；".join(errors))
    return workflow.generation_type_id,version.id,clean,binding.model_dump()


@router.get("/generations")
def history(user: CurrentUser, db: DBSession):
    rows = db.query(Task, Batch).join(Batch, Task.batch_id == Batch.id).filter(
        Batch.source == "gallery", Task.user_id == user.id
    ).order_by(Task.id.desc()).limit(30)
    return [{"id": task.id, "status": task.status, "version": task.workflow_version_id,
             "recipe": batch.global_params.get("gallery_recipe", {})} for task, batch in rows]
