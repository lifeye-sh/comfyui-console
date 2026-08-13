"""节点管理路由 /api/v1/nodes（管理员写，登录可读）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import AdminUser, DBSession
from app.models import Node
from app.services import node_service
from app.schemas.schemas import NodeCreateIn, NodeOut, NodePatchIn

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.get("", response_model=list[NodeOut])
def list_nodes(admin: AdminUser, db: DBSession) -> list[NodeOut]:
    return [NodeOut.model_validate(n) for n in node_service.list_nodes(db)]


@router.post("", response_model=NodeOut, status_code=201)
def create_node(body: NodeCreateIn, admin: AdminUser, db: DBSession) -> NodeOut:
    return NodeOut.model_validate(node_service.create_node(db, body))


@router.patch("/{node_id}", response_model=NodeOut)
def patch_node(node_id: int, body: NodePatchIn, admin: AdminUser, db: DBSession) -> NodeOut:
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "节点不存在")
    return NodeOut.model_validate(node_service.patch_node(db, node, body))


@router.delete("/{node_id}", status_code=204)
def delete_node(node_id: int, admin: AdminUser, db: DBSession) -> None:
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "节点不存在")
    node_service.delete_node(db, node)


@router.post("/{node_id}/probe")
async def probe_node(node_id: int, admin: AdminUser, db: DBSession) -> dict:
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "节点不存在")
    try:
        info = await node_service.probe_node(node)
        node_service.mark_seen(db, node, "online")
        return {"ok": True, "info": info}
    except Exception as e:  # noqa: BLE001
        node_service.mark_probe_failed(db, node, str(e), offline_after=1)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"节点探测失败：{e}")
