"""队列提供者抽象。MVP 用 DB 直接实现（见 dispatcher.py）；扩展实现可对接 Redis Streams。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class QueueProvider(ABC):
    @abstractmethod
    async def enqueue(self, task_id: int, priority: int = 0) -> None: ...

    @abstractmethod
    async def dequeue(self) -> Optional[dict[str, Any]]: ...

    @abstractmethod
    async def ack(self, task_id: int) -> None: ...

    @abstractmethod
    async def nack(self, task_id: int) -> None: ...