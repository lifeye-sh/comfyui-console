"""Select an isolated database before any test module imports the app."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import uuid4

import pytest


TEST_TEMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
TEST_TEMP_ROOT.mkdir(exist_ok=True)
TEST_RUN_ID = uuid4().hex
TEST_DATABASE_PATH = TEST_TEMP_ROOT / f"comfyui-console-tests-{TEST_RUN_ID}.db"
TEST_STORAGE_PATH = TEST_TEMP_ROOT / f"resources-{TEST_RUN_ID}"
os.environ["COMFY_CONSOLE_DATABASE_URL"] = (
    f"sqlite:///{TEST_DATABASE_PATH.as_posix()}"
)
os.environ["COMFY_CONSOLE_STORAGE_PATH"] = str(TEST_STORAGE_PATH)


@pytest.fixture
def tmp_path():  # type: ignore[no-untyped-def]
    """Workspace-local replacement for pytest's sandbox-inaccessible temp path."""
    path = TEST_TEMP_ROOT / f"case-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


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
        TEST_DATABASE_PATH.unlink(missing_ok=True)
        shutil.rmtree(TEST_STORAGE_PATH, ignore_errors=True)
        try:
            TEST_TEMP_ROOT.rmdir()
        except OSError:
            pass
