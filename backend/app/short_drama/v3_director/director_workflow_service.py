"""导演前期工作流：确定性步骤和门禁。不调用 LLM。

契约见 docs/v3-director-rfc.md §4。current_step 是流程唯一事实源。
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.v3_director import V3DirectorStepState, V3DirectorWorkflowRun

# 步骤定义（RFC §4.1）
STEP_LABELS: dict[int, str] = {
    0: "源材料导入",
    1: "故事级台账 + 情感曲线",
    2: "改编候选确认 → StoryVersion",
    3: "场景级剧本台账",
    4: "风格圣经 + 色卡",
    5: "主角/配角/道具锚点",
    6: "外景拓扑/内景平面图",
    7: "Manifest + 连续性审计",
    8: "生产编译",
}
CHECKPOINT_STEPS: dict[int, str] = {1: "A", 4: "B", 5: "C"}
MAX_STEP = 8


def get_or_create_run(db: Session, project_id: int) -> V3DirectorWorkflowRun:
    """获取项目工作流运行；不存在则创建并初始化步骤状态。"""
    run = db.query(V3DirectorWorkflowRun).filter(
        V3DirectorWorkflowRun.project_id == project_id
    ).first()
    if run:
        return run
    run = V3DirectorWorkflowRun(project_id=project_id, current_step=0, status="active")
    db.add(run)
    db.flush()
    for step in range(MAX_STEP + 1):
        db.add(V3DirectorStepState(workflow_run_id=run.id, step=step, gate_status="pending"))
    db.commit()
    db.refresh(run)
    return run


def get_state(db: Session, project_id: int) -> dict:
    """返回工作流运行 + 各步骤门禁状态（不含 LLM 判断）。"""
    run = get_or_create_run(db, project_id)
    steps = {s.step: s for s in run.steps}
    return {
        "project_id": project_id,
        "run_id": run.id,
        "current_step": run.current_step,
        "status": run.status,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "steps": [
            {
                "step": step,
                "label": STEP_LABELS.get(step, f"步骤 {step}"),
                "checkpoint": CHECKPOINT_STEPS.get(step),
                "gate_status": steps[step].gate_status if step in steps else "pending",
                "passed_at": steps[step].passed_at if step in steps else None,
            }
            for step in range(MAX_STEP + 1)
        ],
    }


def set_gate(
    db: Session,
    project_id: int,
    step: int,
    gate_status: str,
    reason: str | None = None,
) -> dict:
    """设置门禁状态（passed / blocked / waived / pending）。确定性规则操作。"""
    if gate_status not in {"pending", "blocked", "passed", "waived"}:
        raise ValueError("门禁状态必须是 pending/blocked/passed/waived")
    run = get_or_create_run(db, project_id)
    state = db.query(V3DirectorStepState).filter(
        V3DirectorStepState.workflow_run_id == run.id,
        V3DirectorStepState.step == step,
    ).first()
    if not state:
        raise ValueError(f"步骤 {step} 不存在")
    state.gate_status = gate_status
    state.waive_reason = reason if gate_status in ("waived", "blocked") else None
    state.passed_at = datetime.now(timezone.utc) if gate_status == "passed" else None
    db.commit()
    return get_state(db, project_id)


def advance_step(
    db: Session,
    project_id: int,
    allow_blocked: bool = False,
) -> dict:
    """推进 current_step；门禁状态仅作为建议展示，不阻断推进。"""
    run = get_or_create_run(db, project_id)
    if run.status != "active":
        raise ValueError("工作流已结束")
    if run.current_step >= MAX_STEP:
        raise ValueError("已是最后一步")
    target = run.current_step + 1
    run.current_step = target
    if target == MAX_STEP:
        run.completed_at = datetime.now(timezone.utc)
        run.status = "completed"
    db.commit()
    return get_state(db, project_id)


def can_proceed_to(db: Session, project_id: int, target_step: int) -> tuple[bool, str]:
    """兼容旧调用：门禁永远可继续，未完成状态由界面作为建议展示。"""
    get_or_create_run(db, project_id)
    return True, ""
