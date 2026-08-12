"""分享链接路由 /api/v1/shares 与公开访问 /s/{token}。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, DBSession
from app.models import Share
from app.services import share_service
from app.storage.local_fs import get_storage
from app.schemas.schemas import ShareCreateIn, ShareOut

router = APIRouter(prefix="/shares", tags=["shares"])
public_router = APIRouter(tags=["shares"])


@router.post("", response_model=ShareOut, status_code=201)
def create(body: ShareCreateIn, user: CurrentUser, db: DBSession) -> ShareOut:
    try:
        share = share_service.create_share(
            db, body.resource_id, body.password, body.expires_hours, body.allow_download, user.id
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return ShareOut.model_validate(share)


@router.get("", response_model=list[ShareOut])
def list_(user: CurrentUser, db: DBSession, resource_id: int | None = None) -> list[ShareOut]:
    return [ShareOut.model_validate(s) for s in share_service.list_shares(db, resource_id)]


@router.delete("/{share_id}", status_code=204)
def revoke(share_id: int, user: CurrentUser, db: DBSession) -> None:
    share = db.get(Share, share_id)
    if not share:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "分享不存在")
    share_service.revoke_share(db, share)


@public_router.get("/s/{token}")
def access_share(token: str, db: DBSession, password: str | None = None) -> dict:
    share = share_service.get_share_by_token(db, token)
    if not share:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "分享已过期或不存在")
    if not share_service.verify_share(share, password):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "密码错误")
    resource = db.get(Share.resource_id.__class__, share.resource_id) if False else None
    from app.models import Resource
    resource = db.get(Resource, share.resource_id)
    if not resource:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "资源不存在")
    return {
        "filename": resource.filename,
        "mime": resource.mime,
        "size": resource.size,
        "media_type": resource.media_type,
        "allow_download": share.allow_download,
    }


@public_router.get("/s/{token}/file")
def download_share(token: str, db: DBSession, password: str | None = None):
    share = share_service.get_share_by_token(db, token)
    if not share:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "分享已过期或不存在")
    if not share.allow_download:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "此分享不允许下载")
    if not share_service.verify_share(share, password):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "密码错误")
    from app.models import Resource
    resource = db.get(Resource, share.resource_id)
    if not resource:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "资源不存在")
    import io
    data = get_storage().read(resource.storage_key)
    return StreamingResponse(io.BytesIO(data), media_type=resource.mime)


__all__ = ["router", "public_router"]