"""Gemini Image provider configuration and gateway client."""
from __future__ import annotations

import base64
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.models import ImageProviderConfig
from app.short_drama.ai_service import decrypt_api_key, encrypt_api_key


class ImageProviderInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    provider: str = Field(pattern="^gemini_(web2api|proxy)$")
    base_url: str = Field(min_length=1, max_length=512)
    model: str = Field(min_length=1, max_length=128)
    api_key: str | None = Field(default=None, max_length=2048)
    enabled: bool = True
    is_default: bool = False
    timeout_seconds: int = Field(default=300, ge=10, le=900)
    max_concurrency: int = Field(default=1, ge=1, le=32)


class ImageProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    provider: str
    base_url: str
    model: str
    api_key_hint: str
    enabled: bool
    is_default: bool
    timeout_seconds: int
    max_concurrency: int
    created_at: Any
    updated_at: Any


@dataclass(frozen=True)
class GeneratedImage:
    data: bytes
    mime: str
    note: str = ""


def _hint(value: str) -> str:
    if not value:
        return "未设置"
    return f"{value[:3]}***{value[-4:]}" if len(value) > 8 else "***"


def save(db: Session, actor_id: int, body: ImageProviderInput, provider_id: int | None = None) -> ImageProviderConfig:
    item = db.get(ImageProviderConfig, provider_id) if provider_id else ImageProviderConfig(created_by=actor_id, api_key_encrypted="")
    if provider_id and not item:
        raise ValueError("图片服务商配置不存在")
    if not provider_id:
        db.add(item)
    for field in ("name", "provider", "base_url", "model", "enabled", "is_default", "timeout_seconds", "max_concurrency"):
        setattr(item, field, getattr(body, field))
    if body.api_key is not None:
        item.api_key_encrypted = encrypt_api_key(body.api_key)
        item.api_key_hint = _hint(body.api_key)
    elif not provider_id:
        # Local gateways may be keyless. Encrypting an empty string keeps storage semantics uniform.
        item.api_key_encrypted = encrypt_api_key("")
        item.api_key_hint = "未设置"
    if item.is_default:
        db.query(ImageProviderConfig).filter(ImageProviderConfig.id != item.id).update(
            {ImageProviderConfig.is_default: False}, synchronize_session=False
        )
    db.commit()
    db.refresh(item)
    return item


def seed_from_environment(db: Session, actor_id: int | None = None) -> ImageProviderConfig | None:
    """Bootstrap the skill-compatible local gateway once; UI edits remain authoritative afterwards."""
    if db.query(ImageProviderConfig.id).first():
        return None
    backend = os.getenv("GEMINI_IMAGE_BACKEND", "web2api").strip().lower()
    is_proxy = backend == "proxy"
    provider = "gemini_proxy" if is_proxy else "gemini_web2api"
    base_url = os.getenv("GEMINI_IMAGE_BASE_URL") or ("http://localhost:4982/openai/v1" if is_proxy else "http://localhost:8083/v1")
    model = os.getenv("GEMINI_IMAGE_MODEL") or ("gemini-2.5-flash-image" if is_proxy else "gemini-image")
    key = os.getenv("GEMINI_IMAGE_API_KEY", "")
    item = ImageProviderConfig(
        name="Gemini Image（本机网关）", provider=provider, base_url=base_url, model=model,
        api_key_encrypted=encrypt_api_key(key), api_key_hint=_hint(key), enabled=True,
        is_default=True, timeout_seconds=300, max_concurrency=1, created_by=actor_id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def delete(db: Session, provider_id: int) -> None:
    item = db.get(ImageProviderConfig, provider_id)
    if not item:
        raise ValueError("图片服务商配置不存在")
    db.delete(item)
    db.commit()


def get_enabled(db: Session, provider_id: int | None = None) -> ImageProviderConfig:
    if provider_id:
        item = db.get(ImageProviderConfig, provider_id)
    else:
        item = db.query(ImageProviderConfig).filter(
            ImageProviderConfig.enabled.is_(True), ImageProviderConfig.is_default.is_(True)
        ).first()
    if not item or not item.enabled:
        raise ValueError("没有可用的 Gemini Image 提供方")
    return item


def _headers(config: ImageProviderConfig) -> dict[str, str]:
    key = decrypt_api_key(config.api_key_encrypted)
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _extract_data_url(content: Any) -> tuple[str, str] | None:
    texts: list[str] = []
    if isinstance(content, str):
        texts.append(content)
    elif isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and item.get("text"):
                texts.append(str(item["text"]))
            image_url = item.get("image_url")
            if item.get("type") == "image_url" and isinstance(image_url, dict):
                texts.append(str(image_url.get("url", "")))
    pattern = re.compile(r"data:([a-zA-Z0-9+/.-]+);base64,([A-Za-z0-9+/=]+)")
    for text in texts:
        match = pattern.search(text)
        if match:
            return match.group(1), match.group(2)
    return None


def _data_url(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


async def generate(
    config: ImageProviderConfig,
    prompt: str,
    references: list[tuple[bytes, str]] | None = None,
    size: str = "1024x1024",
) -> GeneratedImage:
    refs = references or []
    base = config.base_url.rstrip("/")
    size_labels = {
        "1024x1024": "1:1 square",
        "1536x1024": "3:2 landscape",
        "1024x1536": "2:3 portrait",
    }
    effective_size = size or "1024x1024"
    sized_prompt = (
        f"{prompt}\n\nIMAGE OUTPUT REQUIREMENT: {effective_size} pixels, "
        f"{size_labels.get(effective_size, effective_size)} aspect ratio."
    )
    async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
        if config.provider == "gemini_web2api":
            content: str | list[dict[str, Any]] = sized_prompt
            if refs:
                content = [{"type": "text", "text": sized_prompt}]
                content.extend({"type": "image_url", "image_url": {"url": _data_url(data, mime)}} for data, mime in refs)
            response = await client.post(
                f"{base}/chat/completions", headers=_headers(config),
                json={"model": config.model, "messages": [{"role": "user", "content": content}]},
            )
            response.raise_for_status()
            returned = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            found = _extract_data_url(returned)
            if not found:
                raise RuntimeError("Gemini 返回中没有图片数据")
            mime, encoded = found
            note = re.sub(r"!?\[image\]\(data:[^)]+\)", "", returned).strip() if isinstance(returned, str) else ""
        else:
            payload: dict[str, Any] = {
                "model": config.model, "prompt": sized_prompt, "n": 1,
                "size": effective_size, "response_format": "b64_json",
            }
            if refs:
                payload["image"] = [_data_url(data, mime) for data, mime in refs]
            response = await client.post(f"{base}/images/generations", headers=_headers(config), json=payload)
            response.raise_for_status()
            encoded = response.json().get("data", [{}])[0].get("b64_json", "")
            if not encoded:
                raise RuntimeError("Gemini 返回中没有图片数据")
            mime, note = "image/png", ""
    try:
        data = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise RuntimeError("Gemini 图片数据无法解码") from exc
    if not data:
        raise RuntimeError("Gemini 返回了空图片")
    return GeneratedImage(data=data, mime=mime, note=note[:500])


def test(db: Session, provider_id: int) -> dict[str, Any]:
    config = get_enabled(db, provider_id)
    started = time.monotonic()
    with httpx.Client(timeout=min(config.timeout_seconds, 30)) as client:
        response = client.get(f"{config.base_url.rstrip('/')}/models", headers=_headers(config))
        response.raise_for_status()
        models = [item.get("id") for item in response.json().get("data", []) if isinstance(item, dict)]
    return {"ok": True, "model": config.model, "model_available": config.model in models, "latency_ms": round((time.monotonic() - started) * 1000)}
