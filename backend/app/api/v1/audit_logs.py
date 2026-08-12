"""审计日志路由 /api/v1/audit-logs（仅管理员）。"""
from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import AdminUser, DBSession
from app.services import audit_service
from app.schemas.schemas import AuditLogOut

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=list[AuditLogOut])
def list_(
    admin: AdminUser,
    db: DBSession,
    user_id: int | None = None,
    action: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditLogOut]:
    items, _ = audit_service.list_logs(db, user_id, action, limit, offset)
    return [AuditLogOut.model_validate(item) for item in items]