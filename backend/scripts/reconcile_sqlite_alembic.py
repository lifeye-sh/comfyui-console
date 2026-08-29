"""Reconcile a legacy SQLite DB created ahead of Alembic by Base.create_all.

This is intentionally strict: it only repairs the known 0017 -> 0028 drift and
refuses to stamp when any unrelated ORM table/column is missing.
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app.config import settings
from app.models import Base


KNOWN_COLUMNS = {
    "v3_manifest_item_task_links": {
        "output_resource_id": "INTEGER",
    },
    "drama_episodes": {
        "script_mode": "VARCHAR(24) NOT NULL DEFAULT 'novel'",
        "script_text": "TEXT NOT NULL DEFAULT ''",
        "script_settings": "JSON NOT NULL DEFAULT '{}'",
        "script_revision": "INTEGER NOT NULL DEFAULT 1",
    },
    "character_variants": {
        "status": "VARCHAR(24) NOT NULL DEFAULT 'draft'",
        "version": "INTEGER NOT NULL DEFAULT 1",
        "is_default": "BOOLEAN NOT NULL DEFAULT 0",
    },
}
TARGET_REVISION = "0028"


def sqlite_path() -> Path:
    prefix = "sqlite:///"
    if not settings.database_url.startswith(prefix):
        raise SystemExit("This reconciliation is only valid for SQLite databases.")
    return Path(settings.database_url.removeprefix(prefix)).resolve()


def drift(engine) -> tuple[str | None, set[str], dict[str, set[str]]]:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar() if "alembic_version" in tables else None
    missing_tables = set(Base.metadata.tables) - tables
    missing_columns: dict[str, set[str]] = {}
    for table_name in set(Base.metadata.tables) & tables:
        expected = {column.name for column in Base.metadata.tables[table_name].columns}
        actual = {column["name"] for column in inspector.get_columns(table_name)}
        if expected - actual:
            missing_columns[table_name] = expected - actual
    return revision, missing_tables, missing_columns


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="backup and repair the database")
    args = parser.parse_args()
    path = sqlite_path()
    engine = create_engine(settings.database_url)
    revision, missing_tables, missing_columns = drift(engine)
    print(f"database={path}")
    print(f"revision={revision}")
    print(f"missing_tables={sorted(missing_tables)}")
    print(f"missing_columns={missing_columns}")
    allowed = {table: set(columns) for table, columns in KNOWN_COLUMNS.items() if columns}
    if missing_tables:
        raise SystemExit("Refusing repair: one or more ORM tables are missing.")
    unexpected = {table: columns for table, columns in missing_columns.items() if columns - allowed.get(table, set())}
    if unexpected:
        raise SystemExit(f"Refusing repair: unexpected schema drift: {unexpected}")
    if not args.apply:
        print("dry-run only; pass --apply to repair")
        return
    backup = path.with_name(f"{path.name}.before-reconcile-{datetime.now():%Y%m%d-%H%M%S}.bak")
    engine.dispose()
    shutil.copy2(path, backup)
    engine = create_engine(settings.database_url)
    with engine.begin() as connection:
        for table_name, columns in missing_columns.items():
            for column_name in columns:
                definition = KNOWN_COLUMNS[table_name][column_name]
                connection.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {definition}'))
        connection.execute(text("UPDATE alembic_version SET version_num = :revision"), {"revision": TARGET_REVISION})
    revision, missing_tables, missing_columns = drift(engine)
    if revision != TARGET_REVISION or missing_tables or missing_columns:
        raise SystemExit(f"Repair verification failed: revision={revision}, tables={missing_tables}, columns={missing_columns}. Backup: {backup}")
    print(f"backup={backup}")
    print(f"reconciled_revision={revision}")
    print("schema verification passed")


if __name__ == "__main__":
    main()
