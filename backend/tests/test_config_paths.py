from __future__ import annotations

from app.config import BACKEND_DIR, Settings, settings


def test_relative_data_paths_are_anchored_to_backend(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    configured = Settings(
        database_url="sqlite:///./data/path-test.db",
        storage_path="./data/path-test-resources",
    )

    assert configured.database_url == (
        f"sqlite:///{(BACKEND_DIR / 'data' / 'path-test.db').resolve().as_posix()}"
    )
    assert configured.storage_path == str(
        (BACKEND_DIR / "data" / "path-test-resources").resolve()
    )


def test_pytest_never_uses_development_database() -> None:
    development_database = (BACKEND_DIR / "data" / "app.db").resolve().as_posix()

    assert development_database not in settings.database_url
    assert "comfyui-console-tests-" in settings.database_url
