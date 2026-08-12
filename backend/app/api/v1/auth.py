"""认证路由 /api/v1/auth。"""
from __future__ import annotations

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import DBSession, get_current_user
from app.models import User
from app.services import auth_service
from app.schemas.schemas import LoginIn, RefreshIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: DBSession) -> TokenOut:
    result = auth_service.login(db, body)
    if not result:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    access, refresh = result
    return TokenOut(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, db: DBSession) -> TokenOut:
    result = auth_service.refresh(db, body.refresh_token)
    if not result:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "刷新令牌无效")
    access, refresh = result
    return TokenOut(access_token=access, refresh_token=refresh)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)