"""首页系统 Dashboard 聚合统计。"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import GenerationType, Node, Resource, Task, Workflow


ACTIVE_TASK_STATUSES = ("PENDING", "DISPATCHING", "QUEUED", "RUNNING", "FINALIZING")


def get_summary(db: Session, user_id: int | None = None) -> dict:
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    trend_start = today - timedelta(days=6)

    nodes = db.query(Node).order_by(Node.id).all()
    task_query = db.query(Task)
    resource_query = db.query(Resource).filter(Resource.deleted_at.is_(None))
    if user_id is not None:
        task_query = task_query.filter(Task.user_id == user_id)
        resource_query = resource_query.filter(Resource.owner_id == user_id)
    today_tasks = task_query.filter(Task.created_at >= today).all()
    trend_tasks = task_query.filter(Task.created_at >= trend_start).all()
    task_status_counts = Counter(task.status for task in today_tasks)
    active_task_count = task_query.filter(Task.status.in_(ACTIVE_TASK_STATUSES)).count()
    completed = task_status_counts["SUCCESS"] + task_status_counts["FAILED"]

    resource_counts = Counter(
        media_type for (media_type,) in resource_query.with_entities(Resource.media_type).all()
    )
    generation_types = db.query(GenerationType).filter(GenerationType.enabled.is_(True)).all()
    workflows = db.query(Workflow).filter(Workflow.status == "active").all()

    trend_by_day: dict[str, Counter] = {
        (trend_start + timedelta(days=index)).date().isoformat(): Counter()
        for index in range(7)
    }
    for task in trend_tasks:
        day = task.created_at.date().isoformat()
        if day in trend_by_day:
            trend_by_day[day][task.status] += 1

    type_names = {item.id: item.name for item in generation_types}
    recent_tasks = task_query.order_by(Task.id.desc()).limit(8).all()

    return {
        "generated_at": now.isoformat(),
        "tasks": {
            "total": task_query.count(),
            "today": len(today_tasks),
            "active": active_task_count,
            "success": task_status_counts["SUCCESS"],
            "failed": task_status_counts["FAILED"],
            "success_rate": round(task_status_counts["SUCCESS"] * 100 / completed, 1) if completed else 0,
            "status_counts": dict(task_status_counts),
        },
        "nodes": {
            "total": len(nodes),
            "online": sum(node.status == "online" for node in nodes),
            "capacity": sum(node.max_concurrent for node in nodes),
            "items": [
                {
                    "id": node.id,
                    "name": node.name,
                    "status": node.status,
                    "max_concurrent": node.max_concurrent,
                    "last_seen_at": node.last_seen_at,
                }
                for node in nodes
            ],
        },
        "resources": {
            "total": resource_query.count(),
            "image": resource_counts["image"],
            "video": resource_counts["video"],
            "audio": resource_counts["audio"],
        },
        "workflows": {
            "total": len(workflows),
            "generation_types": len(generation_types),
            "configured_types": sum(item.default_workflow_id is not None for item in generation_types),
        },
        "trend": [
            {
                "date": day,
                "total": sum(counts.values()),
                "success": counts["SUCCESS"],
                "failed": counts["FAILED"],
            }
            for day, counts in trend_by_day.items()
        ],
        "recent_tasks": [
            {
                "id": task.id,
                "status": task.status,
                "generation_type_name": type_names.get(task.generation_type_id, "未分类"),
                "prompt": str((task.params or {}).get("prompt") or (task.params or {}).get("text") or ""),
                "created_at": task.created_at,
            }
            for task in recent_tasks
        ],
    }
