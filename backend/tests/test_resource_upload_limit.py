from __future__ import annotations

from io import BytesIO

import pytest
from fastapi import UploadFile
from sqlalchemy import BigInteger

from app.models import Resource
from app.services import resource_service


class _ExistingQuery:
    def __init__(self, existing: object) -> None:
        self.existing = existing

    def filter(self, *_args: object) -> "_ExistingQuery":
        return self

    def first(self) -> object:
        return self.existing


class _ExistingResourceDB:
    def __init__(self, existing: object) -> None:
        self.existing = existing

    def query(self, _model: object) -> _ExistingQuery:
        return _ExistingQuery(self.existing)


def test_resource_upload_limit_and_size_column_support_2gb() -> None:
    assert resource_service.MAX_SIZE == 2 * 1024 * 1024 * 1024
    assert isinstance(Resource.__table__.c.size.type, BigInteger)


@pytest.mark.asyncio
async def test_upload_rejects_content_over_limit_without_reading_it_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(resource_service, "MAX_SIZE", 4)
    monkeypatch.setattr(resource_service, "UPLOAD_CHUNK_SIZE", 3)
    upload = UploadFile(filename="large.bin", file=BytesIO(b"12345"))

    with pytest.raises(ValueError, match="文件不能超过 2GB"):
        await resource_service.upload_resource(_ExistingResourceDB(object()), upload, owner_id=1)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_upload_accepts_content_exactly_at_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(resource_service, "MAX_SIZE", 4)
    monkeypatch.setattr(resource_service, "UPLOAD_CHUNK_SIZE", 3)
    existing = object()
    upload = UploadFile(filename="boundary.bin", file=BytesIO(b"1234"))

    result = await resource_service.upload_resource(_ExistingResourceDB(existing), upload, owner_id=1)  # type: ignore[arg-type]

    assert result is existing
    assert upload.file.tell() == 0
