"""WebSocket 网关 /ws/events。

鉴权：查询参数 token=JWT。连接绑定 user_id。
- task 事件：payload 带 owner_id 时只推给该用户（项目隔离），否则兼容旧广播
- director 事件：客户端发送 {"type":"subscribe","project_id":N} 订阅，
  服务器校验项目归属后按 user+project 定向推送；{"type":"unsubscribe","project_id":N} 退订
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.core.events import bus
from app.core.security import decode_token
from app.db import SessionLocal
from app.models import ShortDramaProject, User

logger = logging.getLogger(__name__)


class ConnectionManager:
    """按连接管理订阅：每个连接绑定 user_id 与一组 project 订阅。"""

    def __init__(self) -> None:
        # ws -> {"user_id": int, "projects": set[int]}
        self.active: dict[WebSocket, dict[str, Any]] = {}

    async def connect(self, ws: WebSocket, user_id: int) -> None:
        await ws.accept()
        self.active[ws] = {"user_id": user_id, "projects": set()}

    def disconnect(self, ws: WebSocket) -> None:
        self.active.pop(ws, None)

    def subscribe_project(self, ws: WebSocket, project_id: int) -> bool:
        conn = self.active.get(ws)
        if not conn:
            return False
        conn["projects"].add(project_id)
        return True

    def unsubscribe_project(self, ws: WebSocket, project_id: int) -> None:
        conn = self.active.get(ws)
        if conn:
            conn["projects"].discard(project_id)

    def user_id_of(self, ws: WebSocket) -> int | None:
        conn = self.active.get(ws)
        return conn["user_id"] if conn else None

    async def broadcast(self, msg: dict[str, Any], owner_id: int | None = None) -> None:
        """owner_id 存在时只推送给该用户的连接；否则广播（系统级兼容）。"""
        for ws, conn in list(self.active.items()):
            if owner_id is not None and conn["user_id"] != owner_id:
                continue
            try:
                await ws.send_json(msg)
            except Exception:  # noqa: BLE001
                self.disconnect(ws)

    async def send_to_project(self, project_id: int, owner_id: int, msg: dict[str, Any]) -> None:
        """导演事件定向推送：仅发给 owner 的、且订阅了该 project 的连接。"""
        for ws, conn in list(self.active.items()):
            if conn["user_id"] != owner_id or project_id not in conn["projects"]:
                continue
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
        },
        owner_id=payload.get("owner_id"),
    )


async def _on_director_event(payload: dict[str, Any]) -> None:
    await manager.send_to_project(
        payload["project_id"],
        payload["owner_id"],
        {
            "type": f"director.{payload['type']}",
            "project_id": payload["project_id"],
            "payload": payload["payload"],
        },
    )


def _project_owned_by(project_id: int, user_id: int) -> bool:
    db = SessionLocal()
    try:
        row = (
            db.query(ShortDramaProject.id)
            .filter(
                ShortDramaProject.id == project_id,
                ShortDramaProject.owner_id == user_id,
            )
            .first()
        )
        return row is not None
    finally:
        db.close()


def init_ws(app: FastAPI) -> None:
    global _subscribed
    if not _subscribed:
        bus.subscribe("task", _on_task_event)
        bus.subscribe("director", _on_director_event)
        _subscribed = True

    @app.websocket("/ws/events")
    async def ws_endpoint(ws: WebSocket) -> None:
        token = ws.query_params.get("token", "")
        try:
            claims = decode_token(token)
            username = str(claims.get("sub", ""))
        except Exception:  # noqa: BLE001
            await ws.close(code=4401)
            return
        if not username:
            await ws.close(code=4401)
            return
        # sub 是用户名，查库拿 user_id
        db_session = SessionLocal()
        try:
            user = db_session.query(User).filter(User.username == username).first()
        finally:
            db_session.close()
        if not user:
            await ws.close(code=4401)
            return
        await manager.connect(ws, user.id)
        try:
            while True:
                raw = await ws.receive_text()
                # 客户端控制消息：订阅/退订项目频道
                try:
                    import json

                    msg = json.loads(raw)
                except Exception:  # noqa: BLE001
                    continue
                msg_type = msg.get("type")
                project_id = msg.get("project_id")
                if not isinstance(project_id, int):
                    continue
                if msg_type == "subscribe":
                    # 归属校验：只能订阅自己的项目
                    if _project_owned_by(project_id, user_id):
                        manager.subscribe_project(ws, project_id)
                        await ws.send_json({"type": "director.subscribed", "project_id": project_id})
                    else:
                        await ws.send_json({"type": "director.subscribe_denied", "project_id": project_id})
                elif msg_type == "unsubscribe":
                    manager.unsubscribe_project(ws, project_id)
        except WebSocketDisconnect:
            manager.disconnect(ws)
        except Exception:  # noqa: BLE001
            manager.disconnect(ws)
