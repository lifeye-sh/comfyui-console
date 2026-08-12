"""认证服务：登录、刷新、用户管理。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import User
from app.schemas.schemas import LoginIn, UserCreateIn


def login(db: Session, body: LoginIn) -> tuple[str, str] | None:
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        return None
    if user.status != "active":
        return None
    return create_access_token(user.username, {"role": user.role}), create_refresh_token(user.username)


def refresh(db: Session, refresh_token: str) -> tuple[str, str] | None:
    try:
        payload = decode_token(refresh_token)
    except Exception:
        return None
    if payload.get("type") != "refresh":
        return None
    user = db.query(User).filter(User.username == payload.get("sub")).first()
    if not user or user.status != "active":
        return None
    return create_access_token(user.username, {"role": user.role}), create_refresh_token(user.username)


def create_user(db: Session, body: UserCreateIn) -> User:
    if db.query(User).filter(User.username == body.username).first():
        raise ValueError("用户名已存在")
    user = User(username=body.username, password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def ensure_admin_seed(db: Session, username: str, password: str) -> None:
    """启动时确保管理员种子用户存在。"""
    if db.query(User).filter(User.username == username).first():
        return
    user = User(username=username, password_hash=hash_password(password), role="admin")
    db.add(user)
    db.commit()