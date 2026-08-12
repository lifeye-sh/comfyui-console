"""用户管理路由 /api/v1/users（仅管理员）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import AdminUser, DBSession
from app.models import User
from app.services import auth_service
from app.schemas.schemas import UserCreateIn, UserOut, UserPatchIn

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(admin: AdminUser, db: DBSession) -> list[UserOut]:
    users = db.query(User).order_by(User.id).all()
    return [UserOut.model_validate(u) for u in users]


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreateIn, admin: AdminUser, db: DBSession) -> UserOut:
    try:
        user = auth_service.create_user(db, body)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return UserOut.model_validate(user)


@router.patch("/{user_id}", response_model=UserOut)
def patch_user(user_id: int, body: UserPatchIn, admin: AdminUser, db: DBSession) -> UserOut:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    if body.password:
        from app.core.security import hash_password
        user.password_hash = hash_password(body.password)
    if body.role:
        user.role = body.role
    if body.status:
        user.status = body.status
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)