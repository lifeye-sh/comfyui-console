"""系统 Dashboard 路由。"""
from fastapi import APIRouter

from app.core.deps import CurrentUser, DBSession
from app.services.dashboard_service import get_summary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(user: CurrentUser, db: DBSession) -> dict:
    return get_summary(db)
