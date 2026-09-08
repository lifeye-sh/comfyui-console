"""Exercise Alembic independently of create_all and application compatibility DDL."""
from pathlib import Path
import os
import sqlite3
import subprocess
import sys


def test_clean_sqlite_upgrade_and_versioned_startup(tmp_path):
    root = Path(__file__).resolve().parents[1]
    database = tmp_path / "migration.db"
    env = {**os.environ, "COMFY_CONSOLE_DATABASE_URL": f"sqlite:///{database.as_posix()}"}

    def run(*args):
        result = subprocess.run([sys.executable, *args], cwd=root, env=env,
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert result.returncode == 0, result.stdout + result.stderr

    def schema():
        with sqlite3.connect(database) as db:
            return db.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()

    run("-m", "alembic", "upgrade", "0010")
    before = schema()
    assert not any(name == "v3_stable_identities" for name, _ in before)
    assert not any(name == "script_manifest_versions" for name, _ in before)
    run("-c", "import app.models; from app.db import init_db; init_db()")
    assert schema() == before  # Startup must not jump ahead of Alembic.
    run("-m", "alembic", "upgrade", "0032")
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO users (id, username, password_hash, role, status) VALUES (1, 'migration', 'unused', 'user', 'active')")
        db.execute("INSERT INTO short_drama_projects (id, owner_id, name) VALUES (1, 1, 'migration')")
        db.execute("INSERT INTO v3_stable_identities (id, project_id, entity_type, stable_key, status, created_at, updated_at) VALUES (1, 1, 'scene', 'SC-001', 'active', '2026-08-01', '2026-08-01')")
    run("-m", "alembic", "upgrade", "head")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT stable_key, created_at FROM v3_stable_identities WHERE id=1").fetchone() == ("SC-001", "2026-08-01")
    before = schema()
    run("-m", "alembic", "upgrade", "head")
    run("-c", "import app.models; from app.db import init_db; init_db()")
    assert schema() == before
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0035_structured_drama_imports",)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        for table in ("script_manifest_versions", "project_asset_versions", "shot_character_bindings"):
            columns = {row[1]: row for row in db.execute(f"PRAGMA table_info({table})")}
            assert columns["created_at"][4] == "CURRENT_TIMESTAMP"
            assert columns["updated_at"][4] == "CURRENT_TIMESTAMP"
        assert any(row[3] == "location_id" for row in db.execute("PRAGMA foreign_key_list(drama_scenes)"))
        assert any(row[3] == "first_frame_resource_id" for row in db.execute("PRAGMA foreign_key_list(drama_shots)"))
