"""应用配置（环境变量驱动）。

环境变量前缀 `COMFY_CONSOLE_`，例如：
  COMFY_CONSOLE_DATABASE_URL=postgresql://user:pass@host/db
  COMFY_CONSOLE_SECRET_KEY=...
  COMFY_CONSOLE_DEBUG=false
"""
from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="COMFY_CONSOLE_",
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "comfyui-console"
    version: str = "0.1.0"
    debug: bool = True

    # V2.1 AI 短剧模块；可在部署时显式关闭以快速回滚入口。
    short_drama_enabled: bool = True
    story_worker_poll_seconds: float = 1.0
    story_worker_timeout_seconds: int = 300
    story_worker_max_retries: int = 2

    # V3 AI 导演前期制作模块（实验）；默认关闭，灰度开放。
    v3_director_enabled: bool = False

    # 数据库
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'data' / 'app.db').as_posix()}"

    # 资源存储
    storage_path: str = str(BACKEND_DIR / "data" / "resources")

    @field_validator("database_url", mode="before")
    @classmethod
    def resolve_sqlite_database_url(cls, value: object) -> object:
        """Anchor relative SQLite URLs to backend/, independent of process cwd."""
        if not isinstance(value, str) or not value.startswith("sqlite:///"):
            return value
        raw_path = value.removeprefix("sqlite:///")
        if raw_path == ":memory:" or raw_path.startswith("file:"):
            return value
        path = Path(raw_path)
        if path.is_absolute():
            return value
        return f"sqlite:///{(BACKEND_DIR / path).resolve().as_posix()}"

    @field_validator("storage_path", mode="before")
    @classmethod
    def resolve_storage_path(cls, value: object) -> object:
        """Anchor relative resource storage to backend/, independent of cwd."""
        if not isinstance(value, str):
            return value
        path = Path(value)
        return str(path if path.is_absolute() else (BACKEND_DIR / path).resolve())

    # 认证
    secret_key: str = "change-me-in-production-please-use-a-long-random-secret-key"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_minutes: int = 60 * 24 * 7

    # CORS
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # 管理员种子（首次启动自动创建）
    admin_username: str = "admin"
    admin_password: str = "admin123"


settings = Settings()
