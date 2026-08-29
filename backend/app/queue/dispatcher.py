"""任务调度器：领取 PENDING 任务 → 提交节点 → 轮询完成 → 回拉输出。

M1 采用轮询 /history 的方式保证可靠性（WS 仅用于实时进度推送，不驱动状态机）。
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import hashlib
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.comfy.client import ComfyUIClient
from app.comfy.prompt_builder import build_prompt
from app.core.events import publish_task_event
from app.db import SessionLocal
from app.models import GenerationType, ImageProviderConfig, Node, Resource, ShotTaskLink, Task, TaskResource, Workflow, WorkflowVersion
from app.storage.local_fs import get_storage
from app.services import node_service

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
    def __init__(
        self,
        session_factory=SessionLocal,
        *,
        max_submissions_per_tick: int = 2,
        max_finalizations_per_tick: int = 10,
        node_probe_interval_seconds: float = 15.0,
        orphan_timeout_seconds: float = 300.0,
    ) -> None:
        self._session_factory = session_factory
        # Keep ticks bounded even though they run outside FastAPI's event loop;
        # this also prevents one task class from monopolizing the worker.
        self._max_submissions_per_tick = max(1, max_submissions_per_tick)
        self._max_finalizations_per_tick = max(1, max_finalizations_per_tick)
        self._node_probe_interval_seconds = max(1.0, node_probe_interval_seconds)
        self._orphan_timeout_seconds = max(30.0, orphan_timeout_seconds)
        self._clients: dict[int, ComfyUIClient] = {}
        self._gemini_jobs: dict[int, tuple[int, asyncio.Task[None]]] = {}
        self._gemini_recovery_done = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._web_loop: asyncio.AbstractEventLoop | None = None
        self._started_at: datetime | None = None
        self._last_heartbeat_at: datetime | None = None
        self._last_tick_at: datetime | None = None
        self._last_probe_at: datetime | None = None
        self._last_error: str | None = None
        self._ticks = self._submitted = self._completed = self._failed = 0

    # ---------- 生命周期 ----------
    async def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._web_loop = asyncio.get_running_loop()
        self._started_at = datetime.now(timezone.utc)
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._thread_main,
            name="comfyui-dispatcher",
            daemon=True,
        )
        self._thread.start()

    async def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            await asyncio.to_thread(self._thread.join, 10)
        self._thread = None
        self._web_loop = None

    def _thread_main(self) -> None:
        """Run queue I/O on its own event loop so it cannot block the API."""
        asyncio.run(self._run())

    def status(self) -> dict:
        db = self._session_factory()
        try:
            counts = {state: db.query(Task).filter(Task.status == state).count() for state in (
                "PENDING", "DISPATCHING", "QUEUED", "RUNNING", "FAILED"
            )}
        finally:
            db.close()
        thread = self._thread
        active_model_channels: dict[int, int] = {}
        for model_config_id, job in self._gemini_jobs.values():
            if not job.done():
                active_model_channels[model_config_id] = active_model_channels.get(model_config_id, 0) + 1
        return {
            "running": bool(thread and thread.is_alive()), "thread_name": thread.name if thread else None,
            "started_at": self._started_at, "last_heartbeat_at": self._last_heartbeat_at,
            "last_tick_at": self._last_tick_at, "last_probe_at": self._last_probe_at,
            "last_error": self._last_error,
            "counters": {"ticks": self._ticks, "submitted": self._submitted, "completed": self._completed, "failed": self._failed},
            "gemini": {
                "active": sum(active_model_channels.values()),
                "model_channels": [
                    {"model_config_id": model_config_id, "active": active}
                    for model_config_id, active in sorted(active_model_channels.items())
                ],
            },
            "tasks": counts,
        }

    def _get_client(self, node: Node) -> ComfyUIClient:
        c = self._clients.get(node.id)
        if c is None:
            c = ComfyUIClient(node.id, node.base_url, node.ws_url)
            self._clients[node.id] = c
        return c

    # ---------- 主循环 ----------
    async def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                self._last_heartbeat_at = datetime.now(timezone.utc)
                try:
                    await self._tick()
                    self._last_error = None
                except Exception as e:  # noqa: BLE001
                    self._last_error = str(e)
                    logger.exception("调度循环异常: %s", e)
                await asyncio.sleep(1.0)
        finally:
            jobs = [job for _, job in self._gemini_jobs.values() if not job.done()]
            for job in jobs:
                job.cancel()
            if jobs:
                await asyncio.gather(*jobs, return_exceptions=True)
            self._gemini_jobs.clear()
            for client in self._clients.values():
                await client.aclose()
            self._clients.clear()

    async def _publish(self, task_id: int, event_type: str, progress: int, payload: dict, owner_id: int | None = None) -> None:
        """Publish websocket events on FastAPI's loop from the worker thread."""
        web_loop = self._web_loop
        if web_loop and web_loop.is_running() and asyncio.get_running_loop() is not web_loop:
            future = asyncio.run_coroutine_threadsafe(
                publish_task_event(task_id, event_type, progress, payload, owner_id=owner_id),
                web_loop,
            )
            await asyncio.wrap_future(future)
            return
        await publish_task_event(task_id, event_type, progress, payload, owner_id=owner_id)

    async def _tick(self) -> None:
        db = self._session_factory()
        try:
            now = datetime.now(timezone.utc)
            await self._submit_gemini_pending(db)
            if not self._last_probe_at or (now - self._last_probe_at).total_seconds() >= self._node_probe_interval_seconds:
                await self._probe_nodes(db)
                self._last_probe_at = now
            await self._finalize_completed(db)
            await self._retry_short_drama_compensation(db)
            await self._submit_pending(db)
            self._ticks += 1
            self._last_tick_at = datetime.now(timezone.utc)
        finally:
            db.close()

    async def _probe_nodes(self, db: Session) -> None:
        for node in db.query(Node).order_by(Node.id).all():
            try:
                await self._get_client(node).probe()
                node_service.mark_seen(db, node, "online")
            except Exception as exc:  # noqa: BLE001
                node_service.mark_probe_failed(db, node, str(exc))
            await asyncio.sleep(0)

    # ---------- 提交 ----------
    def _cleanup_gemini_jobs(self) -> None:
        for task_id, (_, job) in list(self._gemini_jobs.items()):
            if not job.done():
                continue
            try:
                job.exception()
            except (asyncio.CancelledError, Exception):
                pass
            self._gemini_jobs.pop(task_id, None)

    async def _submit_gemini_pending(self, db: Session) -> None:
        """Launch Gemini tasks in per-model-config lanes, independent of ComfyUI nodes."""
        self._cleanup_gemini_jobs()
        if not self._gemini_recovery_done:
            # A process restart cancels in-memory HTTP calls. Put those tasks back
            # into the Gemini lane instead of leaving them as orphaned RUNNING rows.
            changed = False
            for task in db.query(Task).filter(Task.status.in_(["DISPATCHING", "QUEUED", "RUNNING"])).all():
                if (task.params or {}).get("__execution_provider") != "gemini_image" or task.id in self._gemini_jobs:
                    continue
                task.status = "PENDING"
                task.node_id = None
                task.prompt_id = None
                task.error = "服务重启，Gemini 任务已自动恢复排队"
                changed = True
            if changed:
                db.commit()
            self._gemini_recovery_done = True

        providers = {
            item.id: item for item in db.query(ImageProviderConfig).filter(ImageProviderConfig.enabled.is_(True)).all()
        }
        # ImageProviderConfig.id is the lane identity. Configurations that share
        # a provider kind or base URL still have completely independent limits.
        active_by_model_config: dict[int, int] = {}
        for provider_id, job in self._gemini_jobs.values():
            if not job.done():
                active_by_model_config[provider_id] = active_by_model_config.get(provider_id, 0) + 1

        pending = db.query(Task).filter(Task.status == "PENDING").order_by(Task.priority.desc(), Task.id).all()
        for task in pending:
            if task.id in self._gemini_jobs or (task.params or {}).get("__execution_provider") != "gemini_image":
                continue
            provider_id = int((task.params or {}).get("__provider_config_id") or 0)
            provider = providers.get(provider_id)
            if not provider:
                task.status = "FAILED"
                task.error = "Gemini Image 提供方不存在或已停用"
                task.finished_at = datetime.now(timezone.utc)
                db.commit()
                continue
            active = active_by_model_config.get(provider_id, 0)
            if active >= max(1, provider.max_concurrency):
                continue
            job = asyncio.create_task(self._run_gemini_task(task.id), name=f"gemini-image-{task.id}")
            self._gemini_jobs[task.id] = (provider_id, job)
            active_by_model_config[provider_id] = active + 1
            self._submitted += 1

    async def _run_gemini_task(self, task_id: int) -> None:
        db = self._session_factory()
        try:
            task = db.get(Task, task_id)
            if not task or task.status != "PENDING":
                return
            await self._dispatch_gemini_image(db, task)
        finally:
            db.close()

    async def _submit_pending(self, db: Session) -> None:
        """Submit only ComfyUI tasks; Gemini has its own independent lane."""
        for _ in range(self._max_submissions_per_tick):
            t = next((task for task in db.query(Task).filter(Task.status == "PENDING").order_by(Task.priority.desc(), Task.id).all()
                      if (task.params or {}).get("__execution_provider") != "gemini_image"), None)
            if not t:
                return
            node = self._pick_node(db, t)
            if not node:
                return  # 无可用节点，等下一轮
            await self._dispatch(db, t, node)
            self._submitted += 1
            # Some local ComfyUI calls finish immediately. Explicitly give the
            # web server a chance to service pending HTTP requests between jobs.
            await asyncio.sleep(0)

    async def _dispatch_gemini_image(self, db: Session, t: Task) -> None:
        """Execute Gemini image generation/edit while preserving the normal task/resource lifecycle."""
        from app.services import image_provider_service
        from app.services.resource_folder_service import ensure_task_result_folder
        from app.services.resource_service import build_image_thumbnail, thumbnail_storage_key

        t.status = "RUNNING"
        t.started_at = datetime.now(timezone.utc)
        db.commit()
        await self._publish(t.id, "status", 5, {"status": "RUNNING", "provider": "gemini_image"}, owner_id=t.user_id)
        try:
            provider_id = int((t.params or {}).get("__provider_config_id") or 0)
            config = image_provider_service.get_enabled(db, provider_id)
            from app.services import generation_type_service
            maintained_sizes = {
                str(item.get("value")) for item in generation_type_service.get_select_options(db, "image_size")
                if isinstance(item, dict) and item.get("value")
            }
            requested_size = str(
                (t.params or {}).get("size")
                or generation_type_service.get_select_default(db, "image_size")
                or "1024x1024"
            )
            if requested_size not in maintained_sizes:
                raise RuntimeError(f"图片尺寸不在系统维护项中：{requested_size}")
            reference_ids = [int(value) for value in ((t.params or {}).get("reference_resource_ids") or []) if value]
            references: list[tuple[bytes, str]] = []
            for resource_id in reference_ids:
                resource = db.get(Resource, resource_id)
                if not resource or resource.media_type != "image":
                    raise RuntimeError(f"参考图片不存在或类型不正确：#{resource_id}")
                if t.user_id and resource.owner_id not in (None, t.user_id):
                    raise RuntimeError(f"无权使用参考图片：#{resource_id}")
                references.append((await asyncio.to_thread(get_storage().read, resource.storage_key), resource.mime or "image/png"))
                if not db.query(TaskResource.id).filter(TaskResource.task_id == t.id, TaskResource.resource_id == resource.id, TaskResource.role == "input").first():
                    db.add(TaskResource(task_id=t.id, resource_id=resource.id, role="input", slot_key="reference_resource_ids"))
            await self._publish(t.id, "progress", 20, {"mode": "edit" if references else "generate"}, owner_id=t.user_id)
            generated = await image_provider_service.generate(
                config,
                str((t.params or {}).get("prompt") or "").strip(),
                references,
                requested_size,
            )
            sha = hashlib.sha256(generated.data).hexdigest()
            ext = mimetypes.guess_extension(generated.mime) or ".png"
            filename = f"gemini_{'edit' if references else 'generate'}_{t.id}{ext}"
            key = f"resources/{datetime.now(timezone.utc):%Y-%m}/{sha[:16]}/{filename}"
            storage = get_storage()
            storage.save_bytes(generated.data, key)
            thumb_data, width, height = build_image_thumbnail(generated.data)
            thumb_key = thumbnail_storage_key(key)
            storage.save_bytes(thumb_data, thumb_key)
            generation_type = db.get(GenerationType, t.generation_type_id) if t.generation_type_id else None
            resource = Resource(
                owner_id=t.user_id,
                folder_id=ensure_task_result_folder(db, t.user_id, t.id, generation_type.name if generation_type else "Gemini 图片").id if t.user_id else None,
                media_type="image", direction="output", filename=filename, mime=generated.mime,
                size=len(generated.data), sha256=sha, storage_key=key, thumb_key=thumb_key,
                width=width, height=height, visibility="private",
                meta={"provider": "gemini_image", "provider_config_id": config.id, "model": config.model, "image_size": requested_size, "mode": "edit" if references else "generate", "note": generated.note},
            )
            db.add(resource)
            db.flush()
            db.add(TaskResource(task_id=t.id, resource_id=resource.id, role="output"))
            asset_context = (t.params or {}).get("__asset_context")
            if isinstance(asset_context, dict) and t.user_id:
                try:
                    from app.short_drama import phase1_service
                    snapshot = {"provider": "gemini_image", "provider_config_id": config.id, "model": config.model, "image_size": requested_size, "purpose": asset_context.get("purpose", "default"), "reference_resource_ids": reference_ids}
                    creator = phase1_service.auto_link_turnaround if asset_context.get("purpose") in {"asset_turnaround", "character_turnaround"} else phase1_service.create_asset_version
                    creator(db, t.user_id, int(asset_context["project_id"]), str(asset_context["entity_type"]), int(asset_context["entity_id"]),
                        resource_id=resource.id, source_task_id=t.id, prompt=str((t.params or {}).get("prompt") or ""), generation_snapshot=snapshot)
                except Exception as asset_exc:  # result is still valid even if project-candidate linking needs repair
                    logger.warning("Gemini 输出关联项目资产失败 task=%s: %s", t.id, asset_exc)
            t.status = "SUCCESS"
            t.error = None
            t.finished_at = datetime.now(timezone.utc)
            db.commit()
            await self._publish(t.id, "completed", 100, {"status": "SUCCESS", "resource_id": resource.id}, owner_id=t.user_id)
            self._completed += 1
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            task = db.get(Task, t.id)
            if task:
                task.status = "FAILED"
                task.error = str(exc)
                task.retries += 1
                task.finished_at = datetime.now(timezone.utc)
                db.commit()
            await self._publish(t.id, "failed", 0, {"error": str(exc)}, owner_id=t.user_id)
            self._failed += 1
            logger.warning("Gemini Image 任务 %s 失败: %s", t.id, exc)

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
        await self._publish(t.id, "status", 0, {"status": "DISPATCHING"}, owner_id=t.user_id)

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
            await self._publish(t.id, "status", 0, {"status": "QUEUED", "prompt_id": resp["prompt_id"]}, owner_id=t.user_id)
        except Exception as e:  # noqa: BLE001
            db.rollback()
            t.status = "FAILED"
            t.error = str(e)
            t.retries += 1
            db.commit()
            await self._publish(t.id, "failed", 0, {"error": str(e)}, owner_id=t.user_id)
            self._failed += 1
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

            # 遮罩优先：如果该 image 参数附带了 __mask 字段，上传遮罩文件。
            #
            # 统一策略（原图输出永不修改）：
            #   1. 原图照常上传注入 LoadImage 的 image widget（正常流程，不跳过）
            #   2. 遮罩文件（纯黑白图：白=遮罩，黑=非遮罩）上传到 ComfyUI
            #   3. 插入 LoadImageMask 节点（channel="red"）加载遮罩文件，输出 MASK 张量
            #   4. 扫描 prompt 中所有引用 LoadImage MASK 输出的连接 ["<node_id>", 1]，
            #      改为指向 LoadImageMask 的输出 ["_mask_loader", 0]
            #   5. 扫描 class_type 含 mask/inpaint/drawmask 且 mask 输入缺失的节点，
            #      连接到 LoadImageMask 输出
            #   6. LoadImage 的 IMAGE 输出连接 ["<node_id>", 0] 完全不动
            mask_rid: int | None = None
            if spec.get("type") == "image":
                mask_raw = t.params.get(f"{spec['key']}__mask")
                if mask_raw:
                    try:
                        mask_rid = int(mask_raw)
                    except (TypeError, ValueError):
                        mask_rid = None
            if mask_rid:
                mask_r = db.get(Resource, mask_rid)
                if not mask_r:
                    raise RuntimeError(f"遮罩素材不存在: #{mask_rid}")
                if mask_r.media_type != "image":
                    raise RuntimeError(f"遮罩素材 #{mask_rid} 不是图片类型")
                mask_data = await asyncio.to_thread(get_storage().read, mask_r.storage_key)
                mask_up = await client.upload_image(mask_data, mask_r.filename)
                mask_fname = mask_up.get("name", mask_r.filename)
                mask_subfolder = str(mask_up.get("subfolder") or "").strip("/\\")
                if mask_subfolder:
                    mask_fname = f"{mask_subfolder}/{mask_fname}"

                # 原图照常上传并注入（正常流程，LoadImage 的 image widget）
                data = await asyncio.to_thread(get_storage().read, r.storage_key)
                up = await client.upload_image(data, r.filename)
                orig_fname = up.get("name", r.filename)
                orig_subfolder = str(up.get("subfolder") or "").strip("/\\")
                if orig_subfolder:
                    orig_fname = f"{orig_subfolder}/{orig_fname}"
                target, field = resolve_multimedia_target(prompt, spec)
                target[field] = orig_fname

                # 插入 LoadImageMask 节点加载遮罩文件
                # LoadImageMask RETURN_TYPES = ("MASK",)，output 0 = MASK
                # channel="red": mask = R/255.0 → 白色=1.0（遮罩），黑色=0.0（无遮罩）
                mask_loader_id = f"_mask_loader_{spec.get('key', 'image')}"
                prompt[mask_loader_id] = {
                    "class_type": "LoadImageMask",
                    "inputs": {"image": mask_fname, "channel": "red"},
                }

                # 获取 LoadImage 节点 ID（param_schema 中的 node 字段）
                loadimage_node_id = str(spec.get("node") or "")

                # 扫描 prompt 中所有节点的 inputs：
                #   - 把引用 LoadImage MASK 输出 ["<id>", 1] 的连接改为 ["_mask_loader", 0]
                #   - 对 class_type 含 mask/inpaint/drawmask 且 mask 输入缺失的节点，
                #     连接到 LoadImageMask 输出
                for nid, nd in prompt.items():
                    if not isinstance(nd, dict) or nid == mask_loader_id:
                        continue
                    nd_inputs = nd.get("inputs")
                    if not isinstance(nd_inputs, dict):
                        continue
                    nd_class = str(nd.get("class_type", "")).lower()
                    for key, val in list(nd_inputs.items()):
                        # 检查是否为 LoadImage 的 MASK 输出连接 ["<id>", 1]
                        if (
                            isinstance(val, list) and len(val) == 2
                            and str(val[0]) == loadimage_node_id
                            and val[1] == 1
                        ):
                            # 改为指向 LoadImageMask 的 MASK 输出
                            nd_inputs[key] = [mask_loader_id, 0]
                    # 对缺失 mask 输入的节点（如 DrawMaskOnImage），补充连接
                    class_needs_mask = any(
                        kw in nd_class for kw in ("mask", "inpaint", "drawmask")
                    )
                    if class_needs_mask:
                        mask_val = nd_inputs.get("mask")
                        if mask_val in (None, "", 0, []):
                            nd_inputs["mask"] = [mask_loader_id, 0]

                db.add(TaskResource(task_id=t.id, resource_id=mask_r.id, role="mask", slot_key=spec["key"]))
                continue

            # 常规路径：上传原图片 / 视频 / 音频
            data = await asyncio.to_thread(get_storage().read, r.storage_key)
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
        in_flight = (
            db.query(Task)
            .filter(Task.status.in_(["QUEUED", "RUNNING"]))
            .order_by(Task.id)
            .limit(self._max_finalizations_per_tick)
            .all()
        )
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
                await self._recover_orphan(db, t, client)
                continue
            status_info = entry.get("status", {}) or {}
            if status_info.get("completed"):
                has_shot_link = db.query(ShotTaskLink.id).filter(ShotTaskLink.task_id == t.id).first() is not None
                try:
                    if has_shot_link:
                        from app.short_drama import production_service
                        production_service.mark_output_payload(db, t.id, entry.get("outputs", {}))
                    await self._collect_outputs(db, t, client, entry.get("outputs", {}))
                    t.status = "SUCCESS"
                    t.error = None
                    t.finished_at = datetime.now(timezone.utc)
                    db.commit()
                    sync_pending = False
                    if has_shot_link:
                        try:
                            production_service.reconcile_task_outputs(db, t.id)
                        except Exception as sync_exc:  # noqa: BLE001
                            db.rollback()
                            production_service.mark_sync_failed(db, t.id, str(sync_exc))
                            sync_pending = True
                            logger.exception("shot output sync failed task=%s", t.id)
                    await self._publish(t.id, "completed", 100, {"take_sync_pending": sync_pending}, owner_id=t.user_id)
                    self._completed += 1
                except Exception as e:  # noqa: BLE001
                    db.rollback()
                    t = db.get(Task, t.id)
                    if has_shot_link:
                        t.status = "SUCCESS"
                        t.error = None
                        t.finished_at = datetime.now(timezone.utc)
                        db.commit()
                        production_service.mark_output_payload(db, t.id, entry.get("outputs", {}))
                        production_service.mark_sync_failed(db, t.id, str(e), "output_collect_failed")
                        await self._publish(t.id, "completed", 100, {"take_sync_pending": True, "sync_error": str(e)}, owner_id=t.user_id)
                        self._completed += 1
                    else:
                        t.status = "FAILED"
                        t.error = f"输出回收失败: {e}"
                        t.finished_at = datetime.now(timezone.utc)
                        db.commit()
                        await self._publish(t.id, "failed", 0, {"error": str(e)}, owner_id=t.user_id)
                        self._failed += 1
            elif status_info.get("status_str") == "error":
                t.status = "FAILED"
                t.error = str(status_info.get("messages"))[:500]
                t.finished_at = datetime.now(timezone.utc)
                db.commit()
                await self._publish(t.id, "failed", 0, {"error": t.error}, owner_id=t.user_id)
                self._failed += 1
            # History may be served from a local cache without yielding. Keep
            # the API responsive even while many completed jobs are collected.
            await asyncio.sleep(0)

    async def _retry_short_drama_compensation(self, db: Session) -> None:
        """Retry output collection/Take sync without changing successful task state."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        links = (
            db.query(ShotTaskLink)
            .filter(
                ShotTaskLink.status.in_(["output_collect_failed", "sync_failed"]),
                (ShotTaskLink.next_retry_at.is_(None) | (ShotTaskLink.next_retry_at <= now)),
            )
            .order_by(ShotTaskLink.next_retry_at, ShotTaskLink.id)
            .limit(5)
            .all()
        )
        handled: set[int] = set()
        for link in links:
            if link.task_id in handled:
                continue
            handled.add(link.task_id)
            task = db.get(Task, link.task_id)
            if not task or task.status != "SUCCESS":
                continue
            failed_status = link.status
            try:
                if failed_status == "output_collect_failed":
                    node = db.get(Node, task.node_id) if task.node_id else None
                    if not node:
                        raise RuntimeError("任务执行节点不存在，无法补拉产物")
                    await self._collect_outputs(db, task, self._get_client(node), link.output_payload or {})
                    db.commit()
                from app.short_drama import production_service
                production_service.reconcile_task_outputs(db, task.id)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                from app.short_drama import production_service
                production_service.mark_sync_failed(db, task.id, str(exc), failed_status)
                logger.warning("short drama compensation failed task=%s: %s", task.id, exc)
            await asyncio.sleep(0)

    async def _recover_orphan(self, db: Session, task: Task, client: ComfyUIClient) -> None:
        if not task.started_at:
            return
        started = task.started_at.replace(tzinfo=timezone.utc) if task.started_at.tzinfo is None else task.started_at
        now = datetime.now(timezone.utc)
        if now - started < timedelta(seconds=self._orphan_timeout_seconds):
            return
        try:
            queue = await client.get_queue()
        except Exception:
            return
        prompt_ids: set[str] = set()
        for key in ("queue_running", "queue_pending"):
            for item in queue.get(key, []) or []:
                if isinstance(item, (list, tuple)) and len(item) > 1:
                    prompt_ids.add(str(item[1]))
                elif isinstance(item, dict) and item.get("prompt_id"):
                    prompt_ids.add(str(item["prompt_id"]))
        if task.prompt_id in prompt_ids:
            return
        task.status = "FAILED"
        task.error = "ComfyUI 已丢失该任务记录，请使用重新生成功能"
        task.finished_at = now
        db.commit()
        self._failed += 1
        await self._publish(task.id, "failed", 0, {"error": task.error, "recovered": True}, owner_id=task.user_id)

    async def _collect_outputs(self, db: Session, t: Task, client: ComfyUIClient, outputs: dict) -> None:
        seen: set[tuple[str, str, str]] = set()
        for node_id, out in outputs.items():
            for output_key, media_type in (
                ("images", "image"),
                ("gifs", "video"),
                ("videos", "video"),
                ("audio", "audio"),
                ("audios", "audio"),
                ("text", "text"),
                ("texts", "text"),
            ):
                for item in out.get(output_key, []) or []:
                    # 某些自定义节点会直接输出字符串（如内联文本），
                    # 它们没有 filename/subfolder/type，无法通过 /view 下载，跳过。
                    if not isinstance(item, dict):
                        continue
                    identity = (
                        str(item.get("filename", "")),
                        str(item.get("subfolder", "")),
                        str(item.get("type", "output")),
                    )
                    if identity in seen:
                        continue
                    seen.add(identity)
                    await self._save_output(db, t, client, item, media_type=media_type, ext_key=output_key)
        # 根据工作流版本的文本输出配置，提取指定节点的内联文本（如翻译/图片反推结果）
        try:
            wv = db.get(WorkflowVersion, t.workflow_version_id) if t.workflow_version_id else None
            if wv and wv.text_output_config:
                cfg = wv.text_output_config
                node_id = str(cfg.get("node_id") or "")
                field = cfg.get("field") or "*"
                node_out = outputs.get(node_id)
                if node_out and isinstance(node_out, dict):
                    text = self._extract_text(node_out, field)
                    if text:
                        await self._save_text_output(db, t, text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("文本输出提取失败 task=%s: %s", t.id, exc)
        self._auto_link_turnaround_output(db, t)

    @staticmethod
    def _auto_link_turnaround_output(db: Session, task: Task) -> None:
        context = (task.params or {}).get("__asset_context")
        if not isinstance(context, dict) or context.get("purpose") not in {"asset_turnaround", "character_turnaround"} or not task.user_id:
            return
        output = (db.query(Resource).join(TaskResource, TaskResource.resource_id == Resource.id)
            .filter(TaskResource.task_id == task.id, TaskResource.role == "output", Resource.media_type == "image")
            .order_by(Resource.id.desc()).first())
        if not output:
            return
        try:
            from app.short_drama import phase1_service
            phase1_service.auto_link_turnaround(db, task.user_id, int(context["project_id"]), str(context["entity_type"]),
                int(context["entity_id"]), output.id, task.id, str((task.params or {}).get("prompt") or ""),
                {"provider": "comfyui", "purpose": context.get("purpose"), "workflow_version_id": task.workflow_version_id})
        except Exception as exc:  # noqa: BLE001
            logger.warning("ComfyUI 三视图自动关联失败 task=%s: %s", task.id, exc)

    @staticmethod
    def _extract_text(node_out: dict, field: str) -> str:
        """从节点输出中提取文本内容。field 为 '*' 时自动探测所有字符串字段。"""
        def _to_str(value: object) -> str | None:
            if isinstance(value, str):
                return value if value.strip() else None
            if isinstance(value, (list, tuple)):
                parts = []
                for v in value:
                    if isinstance(v, str) and v.strip():
                        parts.append(v)
                    elif isinstance(v, dict) and v.get("filename"):
                        return None  # 文件类型，忽略
                return "\n".join(parts) if parts else None
            return None

        if field and field != "*":
            if field in node_out:
                return _to_str(node_out[field]) or ""
        # 自动探测：优先 text/texts/result/output/string/translation，否则找第一个字符串值
        for key in ("text", "texts", "result", "output", "string", "translation", "response", "content"):
            if key in node_out:
                s = _to_str(node_out[key])
                if s:
                    return s
        for value in node_out.values():
            s = _to_str(value)
            if s:
                return s
        return ""

    async def _save_text_output(self, db: Session, t: Task, text: str) -> None:
        """把内联文本保存为 text 类型 Resource。"""
        from app.models import Resource
        from app.services.resource_folder_service import ensure_task_result_folder

        data = text.encode("utf-8")
        import hashlib, os
        sha = hashlib.sha256(data).hexdigest()
        fname = f"text_output_{datetime.now(timezone.utc):%Y%m%d%H%M%S}.txt"
        key = f"resources/{datetime.now(timezone.utc):%Y-%m}/{sha[:16]}/{fname}"
        get_storage().save_bytes(data, key)
        generation_type = db.get(GenerationType, t.generation_type_id) if t.generation_type_id else None
        r = Resource(
            owner_id=t.user_id,
            folder_id=ensure_task_result_folder(
                db, t.user_id, t.id, generation_type.name if generation_type else "未知类型"
            ).id if t.user_id else None,
            media_type="text",
            direction="output",
            filename=fname,
            mime="text/plain",
            size=len(data),
            sha256=sha,
            storage_key=key,
            visibility="private",
        )
        db.add(r)
        db.flush()
        db.add(TaskResource(task_id=t.id, resource_id=r.id, role="output"))

    async def _save_output(self, db: Session, t: Task, client: ComfyUIClient, item: dict, media_type: str, ext_key: str) -> None:
        from app.models import Resource
        from app.services.resource_service import build_image_thumbnail, infer_media_type, probe_media_metadata, thumbnail_storage_key
        from app.services.resource_folder_service import ensure_task_result_folder

        fname = item.get("filename", "output")
        subfolder = item.get("subfolder", "")
        type_ = item.get("type", "output")
        data = await client.get_view_bytes(fname, subfolder=subfolder, type_=type_)
        import hashlib, os
        sha = hashlib.sha256(data).hexdigest()
        existing = (
            db.query(Resource)
            .join(TaskResource, TaskResource.resource_id == Resource.id)
            .filter(
                TaskResource.task_id == t.id,
                TaskResource.role == "output",
                Resource.sha256 == sha,
                Resource.filename == fname,
                Resource.deleted_at.is_(None),
            )
            .first()
        )
        if existing:
            return
        ext = os.path.splitext(fname)[1] or ""
        key = f"resources/{datetime.now(timezone.utc):%Y-%m}/{sha[:16]}/{fname}"
        storage = get_storage()
        storage.save_bytes(data, key)
        mime = mimetypes.guess_type(fname)[0] or {
            "image": "image/png",
            "video": "video/mp4",
            "audio": "audio/wav",
            "text": "text/plain",
        }.get(media_type, "application/octet-stream")
        media_type = infer_media_type(fname, mime, media_type)
        thumb_key = None
        width = height = duration = None
        if media_type == "image":
            try:
                thumb_data, width, height = build_image_thumbnail(data)
                thumb_key = thumbnail_storage_key(key)
                storage.save_bytes(thumb_data, thumb_key)
            except Exception as exc:  # noqa: BLE001
                logger.warning("输出图片缩略图生成失败 task=%s file=%s: %s", t.id, fname, exc)
        elif media_type in ("video", "audio"):
            try:
                width, height, duration = probe_media_metadata(storage.abs_path(key))
            except Exception as exc:  # noqa: BLE001
                logger.warning("输出媒体元数据读取失败 task=%s file=%s: %s", t.id, fname, exc)
        elif media_type == "text":
            # 文本输出（如图片反推、翻译结果），写入 .txt 文件，无需缩略图
            if not ext:
                key = key + ".txt"
                mime = "text/plain"
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
            duration=duration,
            visibility="private",
        )
        db.add(r)
        db.flush()
        db.add(TaskResource(task_id=t.id, resource_id=r.id, role="output"))


dispatcher = Dispatcher()
