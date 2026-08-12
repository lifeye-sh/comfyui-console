"""节点服务：CRUD、健康探测、能力采集。"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.comfy.client import ComfyUIClient
from app.models import Node
from app.schemas.schemas import NodeCreateIn, NodePatchIn


def list_nodes(db: Session) -> list[Node]:
    return db.query(Node).order_by(Node.id).all()


def create_node(db: Session, body: NodeCreateIn) -> Node:
    node = Node(name=body.name, base_url=body.base_url, ws_url=body.ws_url, tags=body.tags, max_concurrent=body.max_concurrent)
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def patch_node(db: Session, node: Node, body: NodePatchIn) -> Node:
    for f in ("name", "base_url", "ws_url", "tags", "max_concurrent", "status"):
        v = getattr(body, f, None)
        if v is not None:
            setattr(node, f, v)
    db.commit()
    db.refresh(node)
    return node


def delete_node(db: Session, node: Node) -> None:
    db.delete(node)
    db.commit()


async def probe_node(node: Node) -> dict:
    """探测节点：系统状态 + 在线标记。失败抛异常。"""
    client = ComfyUIClient(node.id, node.base_url, node.ws_url)
    try:
        info = await client.probe()
        return info
    finally:
        await client.aclose()


def mark_seen(db: Session, node: Node, status: str = "online") -> None:
    node.status = status
    node.last_seen_at = datetime.now(timezone.utc)
    db.commit()