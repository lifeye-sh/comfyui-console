"""应用配置（环境变量驱动）。

环境变量前缀 `COMFY_CONSOLE_`，例如：
  COMFY_CONSOLE_DATABASE_URL=postgresql://user:pass@host/db
  COMFY_CONSOLE_SECRET_KEY=...
  COMFY_CONSOLE_DEBUG=false
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="COMFY_CONSOLE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "comfyui-console"
    version: str = "0.1.0"
    debug: bool = True

    # 数据库
    database_url: str = "sqlite:///./data/app.db"

    # 资源存储
    storage_path: str = "./data/resources"

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