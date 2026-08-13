from __future__ import annotations

import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Batch, Node, Task
from app.queue.dispatcher import Dispatcher


def test_pending_queue_is_processed_in_bounded_ticks() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    class ImmediateDispatcher(Dispatcher):
        def _pick_node(self, db: Session, task: Task) -> Node | None:
            return db.query(Node).first()

        async def _dispatch(self, db: Session, task: Task, node: Node) -> None:
            # Simulate a local ComfyUI response that completes without yielding.
            task.status = "QUEUED"
            task.node_id = node.id
            db.commit()

    with Session(engine) as db:
        batch = Batch(name="large queue")
        node = Node(name="local", base_url="http://127.0.0.1:8188", status="online")
        db.add_all([batch, node])
        db.flush()
        db.add_all([Task(batch_id=batch.id, status="PENDING", row_no=index) for index in range(20)])
        db.commit()

        dispatcher = ImmediateDispatcher(max_submissions_per_tick=2)
        asyncio.run(dispatcher._submit_pending(db))

        assert db.query(Task).filter(Task.status == "QUEUED").count() == 2
        assert db.query(Task).filter(Task.status == "PENDING").count() == 18


def test_pending_queue_yields_to_http_event_loop_between_jobs() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yielded = False

    class ImmediateDispatcher(Dispatcher):
        def _pick_node(self, db: Session, task: Task) -> Node | None:
            return db.query(Node).first()

        async def _dispatch(self, db: Session, task: Task, node: Node) -> None:
            task.status = "QUEUED"
            db.commit()

    with Session(engine) as db:
        batch = Batch(name="queue")
        node = Node(name="local", base_url="http://127.0.0.1:8188", status="online")
        db.add_all([batch, node])
        db.flush()
        db.add_all([Task(batch_id=batch.id, status="PENDING", row_no=index) for index in range(3)])
        db.commit()

        async def run() -> None:
            nonlocal yielded

            async def simulated_http_request() -> None:
                nonlocal yielded
                await asyncio.sleep(0)
                yielded = True

            request = asyncio.create_task(simulated_http_request())
            await ImmediateDispatcher(max_submissions_per_tick=2)._submit_pending(db)
            await request

        asyncio.run(run())

    assert yielded
