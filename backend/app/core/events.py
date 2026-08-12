"""进程内事件总线（asyncio pub/sub）。

扩展点：后续可替换为 Redis pub/sub 以支持多进程/多实例。
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


async def publish_task_event(task_id: int, event_type: str, progress: int = 0, payload: dict | None = None) -> None:
    await bus.publish("task", {"task_id": task_id, "type": event_type, "progress": progress, "payload": payload or {}})