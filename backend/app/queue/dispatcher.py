"""任务调度器：领取 PENDING 任务 → 提交节点 → 轮询完成 → 回拉输出。

M1 采用轮询 /history 的方式保证可靠性（WS 仅用于实时进度推送，不驱动状态机）。
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.comfy.client import ComfyUIClient
from app.comfy.prompt_builder import build_prompt
from app.core.events import publish_task_event
from app.db import SessionLocal
from app.models import GenerationType, Node, Resource, Task, TaskResource, WorkflowVersion
from app.storage.local_fs import get_storage

logger = logging.getLogger(__name__)


def resolve_multimedia_target(prompt: dict, spec: dict) -> tuple[dict, str]:
    """Resolve the real loader input, tolerating legacy input_image/input_video mappings."""
    node_id = str(spec.get("node") or "")
    node = prompt.get(node_id)
    if not node_id or not isinstance(node, dict):
        raise RuntimeError(f"多媒体参数 {spec.get('key')} 未配置有效节点")

    path = str(spec.get("path") or "")
    parts = [part for part in path.split(".") if part]
    target = node
    valid_path = bool(parts)
    for part in parts[:-1]:
        child = target.get(part)
        if not isinstance(child, dict):
            valid_path = False
            break
        target = child
    if valid_path and parts[-1] in target:
        return target, parts[-1]

    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        raise RuntimeError(f"多媒体参数 {spec.get('key')} 的节点没有 inputs")
    media_type = spec.get("type")
    aliases = {
        "image": ("image", "input_image", "image_path", "filename"),
        "video": ("video", "input_video", "video_path", "filename"),
        "audio": ("audio", "input_audio", "audio_path", "filename"),
    }.get(media_type, ())
    for field in aliases:
        if field in inputs:
            return inputs, field
    for field in inputs:
        if media_type and media_type in field.lower():
            return inputs, field
    raise RuntimeError(f"无法定位多媒体参数 {spec.get('key')} 对应的节点输入")


class Dispatcher:
    def __init__(self, session_factory=SessionLocal) -> None:
        self._session_factory = session_factory
        self._clients: dict[int, ComfyUIClient] = {}
        self._task: asyncio.Task | None = None
        self._stopping = False

    # ---------- 生命周期 ----------
    async def start(self) -> None:
        self._stopping = False
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        for c in self._clients.values():
            await c.aclose()
        self._clients.clear()

    def _get_client(self, node: Node) -> ComfyUIClient:
        c = self._clients.get(node.id)
        if c is None:
            c = ComfyUIClient(node.id, node.base_url, node.ws_url)
            self._clients[node.id] = c
        return c

    # ---------- 主循环 ----------
    async def _run(self) -> None:
        while not self._stopping:
            try:
                await self._tick()
            except Exception as e:  # noqa: BLE001
                logger.exception("调度循环异常: %s", e)
            await asyncio.sleep(1.0)

    async def _tick(self) -> None:
        db = self._session_factory()
        try:
            await self._finalize_completed(db)
            await self._submit_pending(db)
        finally:
            db.close()

    # ---------- 提交 ----------
    async def _submit_pending(self, db: Session) -> None:
        """取 PENDING 任务，按打分选最优节点提交。"""
        while True:
            t = (
                db.query(Task)
                .filter(Task.status == "PENDING")
                .order_by(Task.priority.desc(), Task.id)
                .first()
            )
            if not t:
                break
            node = self._pick_node(db, t)
            if not node:
                break  # 无可用节点，等下一轮
            await self._dispatch(db, t, node)

    def _pick_node(self, db: Session, t: Task) -> Node | None:
        """按标签匹配 + 加权打分选最优节点。返回 None 表示无可用节点。"""
        nodes = db.query(Node).filter(Node.status == "online").all()
        if not nodes:
            return None

        # 任务所需标签（来自工作流版本的 output_mapping 或 generation_type 的 tags）
        # M3 简化：暂不做严格标签匹配，只做负载打分
        candidates = []
        for node in nodes:
            in_flight = (
                db.query(Task)
                .filter(Task.node_id == node.id, Task.status.in_(["QUEUED", "RUNNING"]))
                .count()
            )
            if in_flight >= node.max_concurrent:
                continue
            # 打分：空闲并发越多越好，在途任务越少越好
            free_slots = node.max_concurrent - in_flight
            score = free_slots * 10 - in_flight
            candidates.append((score, node))

        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    async def _dispatch(self, db: Session, t: Task, node: Node) -> None:
        client = self._get_client(node)
        t.status = "DISPATCHING"
        t.node_id = node.id
        db.commit()
        await publish_task_event(t.id, "status", 0, {"status": "DISPATCHING"})

        try:
            wv = db.get(WorkflowVersion, t.workflow_version_id)
            if not wv:
                raise RuntimeError("工作流版本不存在")
            prompt = build_prompt(wv.api_json, wv.param_schema, t.params)
            prompt = await self._upload_inputs(db, client, prompt, wv.param_schema, t)
            client_id = f"console-node{node.id}-task{t.id}"
            resp = await client.post_prompt(prompt, client_id)
            t.prompt_id = resp["prompt_id"]
            t.status = "QUEUED"
            t.started_at = datetime.now(timezone.utc)
            db.commit()
            await publish_task_event(t.id, "status", 0, {"status": "QUEUED", "prompt_id": resp["prompt_id"]})
        except Exception as e:  # noqa: BLE001
            db.rollback()
            t.status = "FAILED"
            t.error = str(e)
            t.retries += 1
            db.commit()
            await publish_task_event(t.id, "failed", 0, {"error": str(e)})
            logger.warning("任务 %s 提交失败: %s", t.id, e)

    async def _upload_inputs(
        self, db: Session, client: ComfyUIClient, prompt: dict, param_schema: list[dict], t: Task
    ) -> dict:
        for spec in param_schema:
            if spec.get("type") not in ("image", "video", "audio"):
                continue
            rid = t.params.get(spec["key"])
            if not rid:
                continue
            r = db.get(Resource, int(rid))
            if not r:
                raise RuntimeError(f"输入素材不存在: #{rid}")
            if r.media_type != spec.get("type"):
                raise RuntimeError(f"输入素材 #{rid} 类型与参数 {spec['key']} 不匹配")
            data = get_storage().read(r.storage_key)
            up = await client.upload_image(data, r.filename)
            fname = up.get("name", r.filename)
            subfolder = str(up.get("subfolder") or "").strip("/\\")
            if subfolder:
                fname = f"{subfolder}/{fname}"
            target, field = resolve_multimedia_target(prompt, spec)
            target[field] = fname
            db.add(TaskResource(task_id=t.id, resource_id=r.id, role="input", slot_key=spec["key"]))
        db.commit()
        return prompt

    # ---------- 完成回收 ----------
    async def _finalize_completed(self, db: Session) -> None:
        in_flight = db.query(Task).filter(Task.status.in_(["QUEUED", "RUNNING"])).all()
        for t in in_flight:
            if not t.prompt_id or not t.node_id:
                continue
            node = db.get(Node, t.node_id)
            if not node:
                continue
            client = self._get_client(node)
            try:
                hist = await client.get_history(t.prompt_id)
            except Exception as e:  # noqa: BLE001
                logger.debug("history 查询失败 task=%s: %s", t.id, e)
                continue
            entry = hist.get(t.prompt_id)
            if not entry:
                continue
            status_info = entry.get("status", {}) or {}
            if status_info.get("completed"):
                try:
                    await self._collect_outputs(db, t, client, entry.get("outputs", {}))
                    t.status = "SUCCESS"
                    t.finished_at = datetime.now(timezone.utc)
                    db.commit()
                    await publish_task_event(t.id, "completed", 100, {})
                except Exception as e:  # noqa: BLE001
                    db.rollback()
                    t.status = "FAILED"
                    t.error = f"输出回收失败: {e}"
                    t.finished_at = datetime.now(timezone.utc)
                    db.commit()
                    await publish_task_event(t.id, "failed", 0, {"error": str(e)})
            elif status_info.get("status_str") == "error":
                t.status = "FAILED"
                t.error = str(status_info.get("messages"))[:500]
                t.finished_at = datetime.now(timezone.utc)
                db.commit()
                await publish_task_event(t.id, "failed", 0, {"error": t.error})

    async def _collect_outputs(self, db: Session, t: Task, client: ComfyUIClient, outputs: dict) -> None:
        seen: set[tuple[str, str, str]] = set()
        for node_id, out in outputs.items():
            for output_key, media_type in (
                ("images", "image"),
                ("gifs", "video"),
                ("videos", "video"),
                ("audio", "audio"),
                ("audios", "audio"),
            ):
                for item in out.get(output_key, []) or []:
                    identity = (
                        str(item.get("filename", "")),
                        str(item.get("subfolder", "")),
                        str(item.get("type", "output")),
                    )
                    if identity in seen:
                        continue
                    seen.add(identity)
                    await self._save_output(db, t, client, item, media_type=media_type, ext_key=output_key)

    async def _save_output(self, db: Session, t: Task, client: ComfyUIClient, item: dict, media_type: str, ext_key: str) -> None:
        from app.models import Resource
        from app.services.resource_service import build_image_thumbnail, infer_media_type, thumbnail_storage_key
        from app.services.resource_folder_service import ensure_task_result_folder

        fname = item.get("filename", "output")
        subfolder = item.get("subfolder", "")
        type_ = item.get("type", "output")
        data = await client.get_view_bytes(fname, subfolder=subfolder, type_=type_)
        import hashlib, os
        sha = hashlib.sha256(data).hexdigest()
        ext = os.path.splitext(fname)[1] or ""
        key = f"resources/{datetime.now(timezone.utc):%Y-%m}/{sha[:8]}/{fname}"
        storage = get_storage()
        storage.save_bytes(data, key)
        mime = mimetypes.guess_type(fname)[0] or {
            "image": "image/png",
            "video": "video/mp4",
            "audio": "audio/wav",
        }.get(media_type, "application/octet-stream")
        media_type = infer_media_type(fname, mime, media_type)
        thumb_key = None
        width = height = None
        if media_type == "image":
            try:
                thumb_data, width, height = build_image_thumbnail(data)
                thumb_key = thumbnail_storage_key(key)
                storage.save_bytes(thumb_data, thumb_key)
            except Exception as exc:  # noqa: BLE001
                logger.warning("输出图片缩略图生成失败 task=%s file=%s: %s", t.id, fname, exc)
        generation_type = db.get(GenerationType, t.generation_type_id) if t.generation_type_id else None
        r = Resource(
            owner_id=t.user_id,
            folder_id=ensure_task_result_folder(
                db, t.user_id, t.id, generation_type.name if generation_type else "未知类型"
            ).id if t.user_id else None,
            media_type=media_type,
            direction="output",
            filename=fname,
            mime=mime,
            size=len(data),
            sha256=sha,
            storage_key=key,
            thumb_key=thumb_key,
            width=width,
            height=height,
            visibility="private",
        )
        db.add(r)
        db.flush()
        db.add(TaskResource(task_id=t.id, resource_id=r.id, role="output"))


dispatcher = Dispatcher()
