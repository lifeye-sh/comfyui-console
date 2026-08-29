from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.deps import AdminUser, CurrentUser, DBSession
from app.models import ImageProviderConfig
from app.services import image_provider_service as service

router = APIRouter(prefix="/image-providers", tags=["image-providers"])


@router.get("", response_model=list[service.ImageProviderOut])
def list_providers(user: CurrentUser, db: DBSession) -> list[service.ImageProviderOut]:
    query = db.query(ImageProviderConfig)
    if user.role != "admin":
        query = query.filter(ImageProviderConfig.enabled.is_(True))
    return [service.ImageProviderOut.model_validate(item) for item in query.order_by(ImageProviderConfig.is_default.desc(), ImageProviderConfig.id).all()]


@router.post("", response_model=service.ImageProviderOut, status_code=status.HTTP_201_CREATED)
def create_provider(body: service.ImageProviderInput, admin: AdminUser, db: DBSession) -> service.ImageProviderOut:
    try:
        return service.ImageProviderOut.model_validate(service.save(db, admin.id, body))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.put("/{provider_id}", response_model=service.ImageProviderOut)
def update_provider(provider_id: int, body: service.ImageProviderInput, admin: AdminUser, db: DBSession) -> service.ImageProviderOut:
    try:
        return service.ImageProviderOut.model_validate(service.save(db, admin.id, body, provider_id))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.delete("/{provider_id}")
def delete_provider(provider_id: int, admin: AdminUser, db: DBSession) -> dict[str, bool]:
    try:
        service.delete(db, provider_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {"deleted": True}


@router.post("/{provider_id}/test")
def test_provider(provider_id: int, admin: AdminUser, db: DBSession) -> dict:
    try:
        return service.test(db, provider_id)
    except Exception as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"连接测试失败：{exc}") from exc
