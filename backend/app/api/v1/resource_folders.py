"""素材库文件夹接口。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser, DBSession
from app.services import resource_folder_service

router = APIRouter(prefix="/resource-folders", tags=["resource-folders"])


class FolderCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    parent_id: int | None = None


class FolderPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    parent_id: int | None = None
    move: bool = False


def folder_out(folder) -> dict:
    return {"id": folder.id, "owner_id": folder.owner_id, "parent_id": folder.parent_id,
            "name": folder.name, "folder_type": folder.folder_type, "system_key": folder.system_key,
            "sort_order": folder.sort_order, "created_at": folder.created_at, "updated_at": folder.updated_at}


@router.get("/tree")
def tree(user: CurrentUser, db: DBSession) -> list[dict]:
    resource_folder_service.ensure_unorganized_folder(db, user.id)
    db.commit()
    return resource_folder_service.tree(db, user.id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create(body: FolderCreateIn, user: CurrentUser, db: DBSession) -> dict:
    try: return folder_out(resource_folder_service.create(db, user.id, body.name, body.parent_id))
    except ValueError as exc: raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.patch("/{folder_id}")
def patch(folder_id: int, body: FolderPatchIn, user: CurrentUser, db: DBSession) -> dict:
    try: return folder_out(resource_folder_service.update(db, user.id, folder_id, body.name, body.parent_id, body.move))
    except ValueError as exc: raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.delete("/{folder_id}")
def delete(folder_id: int, user: CurrentUser, db: DBSession) -> dict:
    try: return {"moved_resources": resource_folder_service.delete(db, user.id, folder_id)}
    except ValueError as exc: raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
