"""Second-stage director workspace; independent from the legacy V3 wizard."""
from fastapi import APIRouter, Depends, HTTPException
from app.config import settings
from app.core.deps import CurrentUser, DBSession
from app.schemas.director_workspace import WorkspaceSave, WorkflowBinding, DirectorGenerate, ImportFrame, ShotRefsUpdate
from app.short_drama import director_workspace_service as service, project_service

def enabled() -> None:
    if not settings.short_drama_enabled: raise HTTPException(404,"短剧模块未启用")

router=APIRouter(prefix="/short-drama/projects/{project_id}/director-workspace", tags=["director-workspace"],dependencies=[Depends(enabled)])

def call(db, function, *args):
    try: return function(db,*args)
    except project_service.ProjectNotFoundError as exc:
        db.rollback();raise HTTPException(404,str(exc)) from exc
    except service.Conflict as exc:
        db.rollback();raise HTTPException(409,str(exc)) from exc
    except ValueError as exc:
        db.rollback();raise HTTPException(422,str(exc)) from exc

@router.get("/episodes/{episode_id}")
def overview(project_id:int,episode_id:int,user:CurrentUser,db:DBSession):
    return call(db,service.overview,user.id,project_id,episode_id)

@router.get("/workflows")
def workflows(project_id:int,user:CurrentUser,db:DBSession):
    return call(db,service.workflow_list,user.id,project_id)

@router.put("/workflows/{version_id}/binding")
def bind(project_id:int,version_id:int,body:WorkflowBinding,user:CurrentUser,db:DBSession):
    call(db,service.bind_workflow,user.id,project_id,version_id,body.mapping)
    return {"saved":True}

@router.get("/shots/{shot_id}")
def shot(project_id:int,shot_id:int,user:CurrentUser,db:DBSession):
    return call(db,service.shot_view,user.id,project_id,shot_id)

@router.put("/shots/{shot_id}")
def save(project_id:int,shot_id:int,body:WorkspaceSave,user:CurrentUser,db:DBSession):
    call(db,service.save_draft,user.id,project_id,shot_id,body.revision,body.draft)
    return call(db,service.shot_view,user.id,project_id,shot_id)

@router.put("/shots/{shot_id}/refs")
def update_refs(project_id:int,shot_id:int,body:ShotRefsUpdate,user:CurrentUser,db:DBSession):
    call(db,service.update_refs,user.id,project_id,shot_id,body.character_ids,body.bindings,body.location_id,body.prop_ids)
    return call(db,service.shot_view,user.id,project_id,shot_id)

@router.post("/shots/{shot_id}/compile")
def compile(project_id:int,shot_id:int,body:DirectorGenerate,user:CurrentUser,db:DBSession):
    return call(db,service.compile_generation,user.id,project_id,shot_id,body)

@router.post("/shots/{shot_id}/generate",status_code=201)
def generate(project_id:int,shot_id:int,body:DirectorGenerate,user:CurrentUser,db:DBSession):
    return call(db,service.create_generation,user.id,project_id,shot_id,body)

@router.post("/shots/{shot_id}/frames/import",status_code=201)
def import_frame(project_id:int,shot_id:int,body:ImportFrame,user:CurrentUser,db:DBSession):
    call(db,service.import_frame,user.id,project_id,shot_id,body.scope,body.resource_id)
    return call(db,service.shot_view,user.id,project_id,shot_id)

@router.post("/shots/{shot_id}/video-prompt")
def video_prompt(project_id:int,shot_id:int,user:CurrentUser,db:DBSession):
    return {"prompt":call(db,service.compose_video_prompt_view,user.id,project_id,shot_id)}

@router.post("/takes/{take_id}/adopt")
def adopt(project_id:int,take_id:int,user:CurrentUser,db:DBSession):
    call(db,service.adopt,user.id,project_id,take_id)
    return {"adopted":True}
