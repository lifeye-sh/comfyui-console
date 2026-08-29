"""导演工作台 WebSocket 事件发布辅助。

在 API 协程里直接发布；异常吞掉不影响主流程（推送是尽力而为）。
"""
from __future__ import annotations

import logging

from app.core.events import publish_director_event

logger = logging.getLogger(__name__)


async def publish(project_id: int, owner_id: int, event_type: str, payload: dict | None = None) -> None:
    try:
        await publish_director_event(project_id, owner_id, event_type, payload)
    except Exception:  # noqa: BLE001
        logger.exception("director 事件发布失败 project=%s type=%s", project_id, event_type)


def safe_publish(project_id: int, owner_id: int, event_type: str, payload: dict | None = None) -> None:
    """同步上下文中的尽力发布：获取运行中 loop 则调度，否则忽略。"""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(publish(project_id, owner_id, event_type, payload))
