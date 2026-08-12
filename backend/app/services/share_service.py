"""分享链接服务。"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models import Resource, Share


def create_share(
    db: Session,
    resource_id: int,
    password: Optional[str],
    expires_hours: Optional[int],
    allow_download: bool,
    created_by: Optional[int],
) -> Share:
    resource = db.get(Resource, resource_id)
    if not resource or resource.deleted_at:
        raise ValueError("资源不存在")
    token = secrets.token_urlsafe(24)
    expires_at = None
    if expires_hours:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
    share = Share(
        resource_id=resource_id,
        token=token,
        password_hash=hash_password(password) if password else None,
        expires_at=expires_at,
        allow_download=allow_download,
        created_by=created_by,
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    return share


def get_share_by_token(db: Session, token: str) -> Optional[Share]:
    share = db.query(Share).filter(Share.token == token, Share.revoked_at.is_(None)).first()
    if not share:
        return None
    if share.expires_at and share.expires_at < datetime.now(timezone.utc):
        return None
    return share


def verify_share(share: Share, password: Optional[str]) -> bool:
    if not share.password_hash:
        return True
    if not password:
        return False
    return verify_password(password, share.password_hash)


def revoke_share(db: Session, share: Share) -> None:
    share.revoked_at = datetime.now(timezone.utc)
    db.commit()


def list_shares(db: Session, resource_id: Optional[int] = None) -> list[Share]:
    q = db.query(Share).filter(Share.revoked_at.is_(None))
    if resource_id:
        q = q.filter(Share.resource_id == resource_id)
    return q.order_by(Share.id.desc()).all()