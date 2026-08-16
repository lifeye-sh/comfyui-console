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
        generation_type_columns = {column["name"] for column in inspect(engine).get_columns("generation_types")}
        if "published_config_version_id" not in generation_type_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE generation_types ADD COLUMN published_config_version_id INTEGER"))
        if "deleted_at" not in generation_type_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE generation_types ADD COLUMN deleted_at DATETIME"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_generation_types_deleted_at ON generation_types (deleted_at)"))
        task_columns = {column["name"] for column in inspect(engine).get_columns("tasks")}
        if "config_version_id" not in task_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE tasks ADD COLUMN config_version_id INTEGER"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_tasks_config_version_id ON tasks (config_version_id)"))
        node_columns = {column["name"] for column in inspect(engine).get_columns("nodes")}
        for column_name, definition in (
            ("last_probe_at", "DATETIME"),
            ("consecutive_failures", "INTEGER NOT NULL DEFAULT 0"),
            ("health_error", "TEXT"),
        ):
            if column_name not in node_columns:
                with engine.begin() as connection:
                    connection.execute(text(f"ALTER TABLE nodes ADD COLUMN {column_name} {definition}"))
        if "drama_scenes" in inspect(engine).get_table_names():
            scene_columns = {column["name"] for column in inspect(engine).get_columns("drama_scenes")}
            for column_name in ("elements", "source_references"):
                if column_name not in scene_columns:
                    with engine.begin() as connection:
                        connection.execute(text(f"ALTER TABLE drama_scenes ADD COLUMN {column_name} JSON NOT NULL DEFAULT '[]'"))
            if "character_ids" not in scene_columns:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE drama_scenes ADD COLUMN character_ids JSON NOT NULL DEFAULT '[]'"))
            if "location_id" not in scene_columns:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE drama_scenes ADD COLUMN location_id INTEGER"))
        for table_name in ("drama_characters", "character_variants", "drama_locations"):
            if table_name not in inspect(engine).get_table_names():
                continue
            columns = {column["name"] for column in inspect(engine).get_columns(table_name)}
            for column_name in ("source_references", "reference_resource_ids"):
                if column_name not in columns:
                    with engine.begin() as connection:
                        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} JSON NOT NULL DEFAULT '[]'"))
        if "drama_props" in inspect(engine).get_table_names():
            prop_columns = {column["name"] for column in inspect(engine).get_columns("drama_props")}
            for column_name, definition in (
                ("appearance", "TEXT NOT NULL DEFAULT ''"),
                ("appearance_scope", "VARCHAR(255) NOT NULL DEFAULT ''"),
                ("source_references", "JSON NOT NULL DEFAULT '[]'"),
                ("reference_resource_ids", "JSON NOT NULL DEFAULT '[]'"),
                ("status", "VARCHAR(24) NOT NULL DEFAULT 'draft'"),
            ):
                if column_name not in prop_columns:
                    with engine.begin() as connection:
                        connection.execute(text(f"ALTER TABLE drama_props ADD COLUMN {column_name} {definition}"))
        if "drama_shots" in inspect(engine).get_table_names():
            shot_columns = {column["name"] for column in inspect(engine).get_columns("drama_shots")}
            for column_name, definition in (
                ("character_ids", "JSON NOT NULL DEFAULT '[]'"),
                ("location_id", "INTEGER"),
                ("prop_ids", "JSON NOT NULL DEFAULT '[]'"),
                ("mood", "VARCHAR(255) NOT NULL DEFAULT ''"),
                ("composition", "VARCHAR(255) NOT NULL DEFAULT ''"),
                ("transition", "VARCHAR(128) NOT NULL DEFAULT ''"),
                ("first_frame_resource_id", "INTEGER"),
                ("last_frame_resource_id", "INTEGER"),
                ("pose_resource_id", "INTEGER"),
                ("reference_video_resource_id", "INTEGER"),
                ("reference_audio_resource_id", "INTEGER"),
                ("reference_resource_ids", "JSON NOT NULL DEFAULT '[]'"),
            ):
                if column_name not in shot_columns:
                    with engine.begin() as connection:
                        connection.execute(text(f"ALTER TABLE drama_shots ADD COLUMN {column_name} {definition}"))
            with engine.begin() as connection:
                connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_drama_shots_scene_no ON drama_shots (scene_id, shot_no)"))
        if "shot_task_links" in inspect(engine).get_table_names():
            link_columns = {column["name"] for column in inspect(engine).get_columns("shot_task_links")}
            for column_name, definition in (
                ("output_payload", "JSON NOT NULL DEFAULT '{}'"),
                ("sync_error", "TEXT"),
                ("sync_attempts", "INTEGER NOT NULL DEFAULT 0"),
                ("next_retry_at", "DATETIME"),
            ):
                if column_name not in link_columns:
                    with engine.begin() as connection:
                        connection.execute(text(f"ALTER TABLE shot_task_links ADD COLUMN {column_name} {definition}"))
            with engine.begin() as connection:
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_shot_task_links_next_retry_at ON shot_task_links (next_retry_at)"))
        if "drama_takes" in inspect(engine).get_table_names():
            with engine.begin() as connection:
                connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_drama_take_task_resource ON drama_takes (source_task_id, resource_id)"))
        if "creative_jobs" in inspect(engine).get_table_names():
            creative_columns = {column["name"] for column in inspect(engine).get_columns("creative_jobs")}
            for column_name, definition in (
                ("parent_job_id", "INTEGER"),
                ("provider_config_id", "INTEGER"),
                ("prompt_template_id", "INTEGER"),
                ("model", "VARCHAR(128)"),
                ("token_usage", "JSON NOT NULL DEFAULT '{}'"),
                ("estimated_cost", "FLOAT NOT NULL DEFAULT 0"),
            ):
                if column_name not in creative_columns:
                    with engine.begin() as connection:
                        connection.execute(text(f"ALTER TABLE creative_jobs ADD COLUMN {column_name} {definition}"))
            with engine.begin() as connection:
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_creative_jobs_parent_job_id ON creative_jobs (parent_job_id)"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_creative_jobs_provider_config_id ON creative_jobs (provider_config_id)"))
        if "drama_episodes" in inspect(engine).get_table_names():
            episode_columns = {column["name"] for column in inspect(engine).get_columns("drama_episodes")}
            for column_name, definition in (
                ("core_conflict", "TEXT NOT NULL DEFAULT ''"),
                ("emotional_arc", "TEXT NOT NULL DEFAULT ''"),
                ("opening_hook", "TEXT NOT NULL DEFAULT ''"),
                ("ending_hook", "TEXT NOT NULL DEFAULT ''"),
                ("is_locked", "BOOLEAN NOT NULL DEFAULT 0"),
            ):
                if column_name not in episode_columns:
                    with engine.begin() as connection:
                        connection.execute(text(f"ALTER TABLE drama_episodes ADD COLUMN {column_name} {definition}"))
