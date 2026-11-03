from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Resource
from app.services import resource_service


def _resource(owner_id: int, storage_key: str, size: int, *, deleted: bool = False) -> Resource:
    return Resource(
        owner_id=owner_id,
        media_type="image",
        direction="input",
        filename=storage_key.rsplit("/", 1)[-1],
        storage_key=storage_key,
        size=size,
        deleted_at=datetime.now(timezone.utc) if deleted else None,
    )


def test_storage_summary_includes_recycle_bin_and_deduplicates_storage_keys() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            _resource(1, "resources/active.png", 100),
            _resource(1, "resources/recycled.png", 40, deleted=True),
            _resource(1, "resources/shared.png", 60),
            _resource(1, "resources/shared.png", 60, deleted=True),
            _resource(2, "resources/other-user.png", 900),
        ])
        db.commit()

        summary = resource_service.storage_summary(db, 1)

    assert summary == {
        "total_bytes": 200,
        "active_bytes": 160,
        "recycle_bin_bytes": 40,
        "total_count": 4,
        "active_count": 2,
        "recycle_bin_count": 2,
    }
