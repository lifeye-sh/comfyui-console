"""WebSocket 网关 /ws/events。

鉴权：查询参数 token=JWT。订阅 EventBus 的 task 主题并广播给所有在线客户端。
扩展点：按 task_id/batch_id 订阅过滤（CC-08 之后细化）。
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.core.events import bus
from app.core.security import decode_token

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, msg: dict[str, Any]) -> None:
        for ws in list(self.active):
            try:
                await ws.send_json(msg)
            except Exception:  # noqa: BLE001
                self.disconnect(ws)


manager = ConnectionManager()
_subscribed = False


async def _on_task_event(payload: dict[str, Any]) -> None:
    await manager.broadcast(
        {
            "type": f"task.{payload['type']}",
            "task_id": payload["task_id"],
            "progress": payload["progress"],
            "payload": payload["payload"],
        }
    )


def init_ws(app: FastAPI) -> None:
    global _subscribed
    if not _subscribed:
        bus.subscribe("task", _on_task_event)
        _subscribed = True

    @app.websocket("/ws/events")
    async def ws_endpoint(ws: WebSocket) -> None:
        token = ws.query_params.get("token", "")
        try:
            decode_token(token)
        except Exception:  # noqa: BLE001
            await ws.close(code=4401)
            return
        await manager.connect(ws)
        try:
            while True:
                await ws.receive_text()  # 心跳/忽略客户端消息
        except WebSocketDisconnect:
            manager.disconnect(ws)
        except Exception:  # noqa: BLE001
            manager.disconnect(ws)