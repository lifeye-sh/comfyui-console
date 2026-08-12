"""ComfyUI 节点客户端：HTTP + WebSocket 封装。

M1 实现：
- HTTP：probe、upload_image、post_prompt、get_history、get_view、interrupt
- WS：iter_ws_events 异步生成器，归一化 ComfyUI 消息为平台事件
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Optional

import httpx

logger = logging.getLogger(__name__)


class ComfyUIClient:
    def __init__(self, node_id: int, base_url: str, ws_url: Optional[str] = None) -> None:
        self.node_id = node_id
        self.base_url = base_url.rstrip("/")
        self.ws_url = ws_url or (base_url.rstrip("/") + "/ws")
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=60.0)

    # ---------- HTTP ----------
    async def probe(self) -> dict[str, Any]:
        r = await self._http.get("/system_stats")
        r.raise_for_status()
        return r.json()

    async def object_info(self) -> dict[str, Any]:
        r = await self._http.get("/object_info")
        r.raise_for_status()
        return r.json()

    async def upload_image(self, data: bytes, filename: str, overwrite: bool = True) -> dict[str, Any]:
        files = {"image": (filename, data, "application/octet-stream")}
        data_form = {"overwrite": "true" if overwrite else "false"}
        r = await self._http.post("/upload/image", files=files, data=data_form)
        r.raise_for_status()
        return r.json()  # {name, subfolder, type}

    async def post_prompt(self, prompt: dict[str, Any], client_id: str) -> dict[str, Any]:
        r = await self._http.post("/prompt", json={"prompt": prompt, "client_id": client_id})
        if r.status_code != 200:
            raise RuntimeError(f"ComfyUI /prompt 失败: {r.status_code} {r.text}")
        return r.json()  # {prompt_id, number, node_errors}

    async def get_history(self, prompt_id: str) -> dict[str, Any]:
        r = await self._http.get(f"/history/{prompt_id}")
        r.raise_for_status()
        return r.json()  # {prompt_id: {...}}

    async def get_view_bytes(self, filename: str, subfolder: str = "", type_: str = "output") -> bytes:
        params = {"filename": filename, "subfolder": subfolder, "type": type_}
        r = await self._http.get("/view", params=params)
        r.raise_for_status()
        return r.content

    async def interrupt(self) -> None:
        await self._http.post("/interrupt")

    async def aclose(self) -> None:
        await self._http.aclose()

    # ---------- WebSocket ----------
    async def iter_ws_events(self) -> AsyncIterator[dict[str, Any]]:
        """连接节点 WS，逐条归一化消息并 yield。

        归一化事件：{type, prompt_id, progress, payload}
        type ∈ progress/executing/executed/execution_error/status
        断线自动重连（指数退避）。
        """
        import websockets  # 延迟导入，避免非 WS 路径依赖

        backoff = 1
        while True:
            try:
                async with websockets.connect(self.ws_url, max_size=None) as ws:
                    backoff = 1
                    async for raw in ws:
                        try:
                            msg = raw if isinstance(raw, dict) else __import__("json").loads(raw)
                        except Exception:  # noqa: BLE001
                            continue
                        yield self._normalize(msg)
            except Exception as e:  # noqa: BLE001
                logger.warning("节点 %s WS 断开：%s，%ss 后重连", self.node_id, e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    @staticmethod
    def _normalize(msg: dict[str, Any]) -> dict[str, Any]:
        mtype = msg.get("type")
        data = msg.get("data", {}) or {}
        if mtype == "progress":
            value = data.get("value", 0)
            mmax = data.get("max", 1) or 1
            return {
                "type": "progress",
                "prompt_id": data.get("prompt_id"),
                "progress": int(value / mmax * 100) if mmax else 0,
                "payload": data,
            }
        if mtype == "executing":
            return {"type": "executing", "prompt_id": data.get("prompt_id"), "progress": 0, "payload": data}
        if mtype == "executed":
            return {"type": "executed", "prompt_id": data.get("prompt_id"), "progress": 100, "payload": data}
        if mtype == "execution_error":
            return {"type": "execution_error", "prompt_id": data.get("prompt_id"), "progress": 0, "payload": data}
        if mtype == "status":
            return {"type": "status", "prompt_id": None, "progress": 0, "payload": data}
        return {"type": mtype or "unknown", "prompt_id": data.get("prompt_id"), "progress": 0, "payload": data}