"""Select an isolated database before any test module imports the app."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path


TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="comfyui-console-tests-"))
os.environ["COMFY_CONSOLE_DATABASE_URL"] = (
    f"sqlite:///{(TEST_DATA_DIR / 'test.db').as_posix()}"
)
os.environ["COMFY_CONSOLE_STORAGE_PATH"] = str(TEST_DATA_DIR / "resources")


def pytest_sessionstart(session) -> None:  # type: ignore[no-untyped-def]
    """Create the same baseline data as application startup, without workers."""
    from app.config import settings
    from app.db import SessionLocal, init_db
    from app.services import auth_service, generation_type_service, prompt_service

    init_db()
    with SessionLocal() as db:
        auth_service.ensure_admin_seed(db, settings.admin_username, settings.admin_password)
        generation_type_service.seed_builtin_types(db)
        generation_type_service.seed_select_options(db)
        prompt_service.seed_default_categories(db)


def pytest_sessionfinish(session, exitstatus) -> None:  # type: ignore[no-untyped-def]
    # Release pooled SQLite handles before cleanup on Windows. Cleanup failure
    # must not hide the actual test result.
    try:
        from app.db import engine

        engine.dispose()
    finally:
        shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
