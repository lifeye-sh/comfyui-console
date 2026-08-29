"""进程内事件总线（asyncio pub/sub）。

扩展点：后续可替换为 Redis pub/sub 以支持多进程/多实例。

事件携带可选 owner_id / project_id / channel，网关据此做用户/项目隔离：
- owner_id 存在 → 只推送给该用户（及其所在连接订阅的 channel）
- owner_id 缺失 → 兼容旧行为广播（仅限非敏感的系统级事件）
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Awaitable, Callable


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[[dict[str, Any]], Awaitable[None]]]] = defaultdict(list)

    def subscribe(self, topic: str, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        self._subs[topic].append(handler)

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        for handler in list(self._subs.get(topic, [])):
            try:
                await handler(payload)
            except Exception:  # noqa: BLE001 — 隔离订阅者错误
                pass


bus = EventBus()


async def publish_task_event(
    task_id: int,
    event_type: str,
    progress: int = 0,
    payload: dict | None = None,
    owner_id: int | None = None,
    project_id: int | None = None,
) -> None:
    await bus.publish("task", {
        "task_id": task_id, "type": event_type, "progress": progress,
        "payload": payload or {}, "owner_id": owner_id, "project_id": project_id,
    })


async def publish_director_event(
    project_id: int,
    owner_id: int,
    event_type: str,
    payload: dict | None = None,
) -> None:
    """导演工作台事件：严格按 user + project 定向推送。"""
    await bus.publish("director", {
        "project_id": project_id, "owner_id": owner_id,
        "type": event_type, "payload": payload or {},
    })
