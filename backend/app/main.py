"""FastAPI 应用入口：路由挂载、生命周期、种子数据、调度器与 WS 网关。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.exceptions import register_exception_handlers
from app.db import SessionLocal, init_db
from app.queue.dispatcher import dispatcher
from app.short_drama.worker import story_worker
from app.short_drama.ai_service import seed_prompts
from app.services import auth_service, generation_type_service, prompt_service, resource_service, resource_folder_service
from app.services import image_provider_service
from app.ws.gateway import init_ws

logging.basicConfig(level=20)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # 1. 建库（开发态）
    init_db()
    # 2. 种子数据
    db = SessionLocal()
    try:
        auth_service.ensure_admin_seed(db, settings.admin_username, settings.admin_password)
        generation_type_service.seed_builtin_types(db)
        generation_type_service.seed_select_options(db)
        prompt_service.seed_default_categories(db)
        resource_service.repair_resource_media_types(db)
        resource_folder_service.archive_existing(db)
        seed_prompts(db)
        from app.models import User
        admin = db.query(User).filter(User.username == settings.admin_username).first()
        image_provider_service.seed_from_environment(db, admin.id if admin else None)
    finally:
        db.close()
    # 3. 启动调度器
    await dispatcher.start()
    logger.info("Dispatcher started")
    if settings.short_drama_enabled:
        await story_worker.start()
        logger.info("Story Worker started")
    yield
    # 4. 关闭
    await dispatcher.stop()
    logger.info("Dispatcher stopped")
    if settings.short_drama_enabled:
        await story_worker.stop()
        logger.info("Story Worker stopped")


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="ComfyUI 工作流管理与批量任务排队平台",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
init_ws(app)

# 路由挂载
from app.api.v1 import (  # noqa: E402
    auth as _auth,
    users as _users,
    nodes as _nodes,
    workflows as _workflows,
    generation_types as _gt,
    batches as _batches,
    tasks as _tasks,
    resources as _resources,
    resource_folders as _resource_folders,
    settings as _settings,
    prompts as _prompts,
    shares as _shares,
    audit_logs as _audit,
    dashboard as _dashboard,
    runtime as _runtime,
)
from app.api.v2 import (  # noqa: E402
    generation_type_configs as _v2_generation_type_configs,
    short_drama as _v2_short_drama,
    short_drama_director as _v2_short_drama_director,
    image_providers as _v2_image_providers,
    structured_imports as _v2_structured_imports,
)

api_prefix = "/api/v1"
app.include_router(_auth.router, prefix=api_prefix)
app.include_router(_users.router, prefix=api_prefix)
app.include_router(_nodes.router, prefix=api_prefix)
app.include_router(_workflows.router, prefix=api_prefix)
app.include_router(_gt.router, prefix=api_prefix)
app.include_router(_batches.router, prefix=api_prefix)
app.include_router(_tasks.router, prefix=api_prefix)
app.include_router(_resources.router, prefix=api_prefix)
app.include_router(_resource_folders.router, prefix=api_prefix)
app.include_router(_settings.router, prefix=api_prefix)
app.include_router(_prompts.router, prefix=api_prefix)
app.include_router(_prompts.cat_router, prefix=api_prefix)
app.include_router(_shares.router, prefix=api_prefix)
app.include_router(_shares.public_router)
app.include_router(_audit.router, prefix=api_prefix)
app.include_router(_dashboard.router, prefix=api_prefix)
app.include_router(_runtime.router, prefix=api_prefix)
app.include_router(_v2_generation_type_configs.router, prefix="/api/v2")
app.include_router(_v2_short_drama.router, prefix="/api/v2")
app.include_router(_v2_short_drama_director.router, prefix="/api/v2")
app.include_router(_v2_image_providers.router, prefix="/api/v2")
app.include_router(_v2_structured_imports.router, prefix="/api/v2")


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "version": settings.version}


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {"app": settings.app_name, "version": settings.version, "docs": "/docs"}

from app.api.v2 import director_workspace as _director_workspace
app.include_router(_director_workspace.router, prefix="/api/v2")
