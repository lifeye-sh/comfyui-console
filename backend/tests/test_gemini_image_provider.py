from __future__ import annotations

import asyncio
import base64

from app.db import SessionLocal
from app.models import Batch, GenerationType, ImageProviderConfig, Resource, Task, TaskResource, User
from app.queue.dispatcher import Dispatcher
from app.schemas.schemas import BatchCreateIn, BatchRowIn
from app.services import batch_service, image_provider_service
from app.services.image_provider_service import GeneratedImage, ImageProviderInput


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_gemini_task_bypasses_workflow_and_saves_output(monkeypatch) -> None:
    with SessionLocal() as db:
        user = db.query(User).first()
        generation_type = db.query(GenerationType).filter(GenerationType.code == "mixed", GenerationType.enabled.is_(True)).first()
        assert user and generation_type
        config = image_provider_service.save(db, user.id, ImageProviderInput(
            name="Gemini test provider", provider="gemini_web2api", base_url="http://localhost:8083/v1",
            model="gemini-image", api_key="test-key", enabled=True, is_default=True, timeout_seconds=30,
            max_concurrency=2,
        ))
        batch = batch_service.create_batch(db, BatchCreateIn(
            name="gemini-test", generation_type_id=generation_type.id,
            rows=[BatchRowIn(row_no=index, generation_type_id=generation_type.id, workflow_version_id=None, params={
                "prompt": f"纸鹤 {index}", "reference_resource_ids": [], "size": "1024x1024",
                "__execution_provider": "gemini_image", "__provider_config_id": config.id,
            }) for index in range(2)],
        ), user.id)
        result = batch_service.submit_batch(db, batch)
        assert result == {"ok": True, "enqueued": 2, "invalid": 0}
        tasks = db.query(Task).filter(Task.batch_id == batch.id).order_by(Task.id).all()
        assert all(task.status == "PENDING" and task.workflow_version_id is None for task in tasks)

        active = 0
        maximum = 0
        requested_sizes: list[str] = []
        async def fake_generate(*args, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal active, maximum
            requested_sizes.append(str(args[3]))
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.05)
            active -= 1
            return GeneratedImage(PNG_1X1, "image/png", "ok")

        async def quiet_publish(*args, **kwargs):  # type: ignore[no-untyped-def]
            return None

        monkeypatch.setattr(image_provider_service, "generate", fake_generate)
        dispatcher = Dispatcher()
        dispatcher._publish = quiet_publish  # type: ignore[method-assign]
        async def execute_lane() -> None:
            await dispatcher._submit_gemini_pending(db)
            await asyncio.gather(*(job for _, job in dispatcher._gemini_jobs.values()))
            dispatcher._cleanup_gemini_jobs()
        asyncio.run(execute_lane())
        db.expire_all()
        tasks = db.query(Task).filter(Task.batch_id == batch.id).order_by(Task.id).all()
        assert maximum == 2
        assert requested_sizes == ["1024x1024", "1024x1024"]
        assert all(task.status == "SUCCESS" for task in tasks)
        outputs = db.query(Resource).join(TaskResource, TaskResource.resource_id == Resource.id).filter(
            TaskResource.task_id.in_([task.id for task in tasks]), TaskResource.role == "output"
        ).all()
        assert len(outputs) == 2
        assert all(output.meta["provider"] == "gemini_image" for output in outputs)

        db.query(TaskResource).filter(TaskResource.task_id.in_([task.id for task in tasks])).delete(synchronize_session=False)
        for output in outputs:
            db.delete(output)
        for task in tasks:
            db.delete(task)
        db.flush()
        db.delete(batch)
        db.delete(config)
        db.commit()


def test_each_image_model_config_is_an_independent_execution_lane() -> None:
    with SessionLocal() as db:
        user = db.query(User).first()
        generation_type = db.query(GenerationType).filter(
            GenerationType.code == "mixed", GenerationType.enabled.is_(True)
        ).first()
        assert user and generation_type

        # Deliberately share the same gateway. Lane isolation must be based on
        # model configuration ID, not provider kind, endpoint, or model family.
        configs = [
            image_provider_service.save(db, user.id, ImageProviderInput(
                name=f"Independent lane {suffix}", provider="gemini_web2api",
                base_url="http://localhost:8083/v1", model=f"gemini-image-{suffix.lower()}",
                api_key="test-key", enabled=True, is_default=False,
                timeout_seconds=30, max_concurrency=1,
            ))
            for suffix in ("A", "B")
        ]
        batch = Batch(
            user_id=user.id, name="independent-model-lanes",
            generation_type_id=generation_type.id, global_params={},
            source="manual", is_template=False,
        )
        db.add(batch)
        db.flush()
        tasks = [
            Task(
                batch_id=batch.id, row_no=index, user_id=user.id,
                generation_type_id=generation_type.id, workflow_version_id=None,
                params={
                    "prompt": f"lane {index}", "__execution_provider": "gemini_image",
                    "__provider_config_id": config.id,
                },
                status="PENDING",
            )
            for index, config in enumerate(configs, start=1)
        ]
        db.add_all(tasks)
        db.commit()
        task_ids = {task.id for task in tasks}

        dispatcher = Dispatcher()
        dispatcher._gemini_recovery_done = True
        started: list[int] = []

        async def fake_run(task_id: int) -> None:
            started.append(task_id)
            await asyncio.sleep(0.05)

        dispatcher._run_gemini_task = fake_run  # type: ignore[method-assign]

        async def execute_lanes() -> None:
            await dispatcher._submit_gemini_pending(db)
            await asyncio.sleep(0)
            assert set(dispatcher._gemini_jobs) == task_ids
            assert set(started) == task_ids
            assert {model_config_id for model_config_id, _ in dispatcher._gemini_jobs.values()} == {
                config.id for config in configs
            }
            await asyncio.gather(*(job for _, job in dispatcher._gemini_jobs.values()))

        asyncio.run(execute_lanes())

        for task in tasks:
            db.delete(task)
        db.flush()
        db.delete(batch)
        for config in configs:
            db.delete(config)
        db.commit()
