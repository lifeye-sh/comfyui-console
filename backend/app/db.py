"""数据库引擎、会话与 Base。

MVP：SQLite（开发）→ PostgreSQL（生产），通过 COMFY_CONSOLE_DATABASE_URL 切换。
CC-01 实现：Base + SessionLocal + get_db + init_db。
"""
from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

_connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=not settings.database_url.startswith("sqlite"),
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """开发态建库：生产用 Alembic 迁移。同时确保 SQLite 文件目录存在。"""
    if settings.database_url.startswith("sqlite"):
        db_file = settings.database_url.replace("sqlite:///", "", 1)
        db_dir = os.path.dirname(db_file)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    # 开发态兼容升级：create_all 不会为已有 SQLite 表增加字段。
    if settings.database_url.startswith("sqlite"):
        resource_columns = {column["name"] for column in inspect(engine).get_columns("resources")}
        if "folder_id" not in resource_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE resources ADD COLUMN folder_id INTEGER"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_resources_folder_id ON resources (folder_id)"))
