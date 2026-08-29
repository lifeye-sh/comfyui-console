"""Standalone R9 test runner (VM: sqlite memory + no pytest)."""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, '.')

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    ShortDramaProject, User,
    V3ActionProposal, V3CharacterAnchorVersion, V3ContextSnapshot, V3StyleBibleVersion,
)
from app.short_drama.v3_director import action_proposal_service, context_selector, director_ai_service
from app.ws.gateway import ConnectionManager


def make_env(db: Session):
    user = User(username="u1", password_hash="x", role="user")
    db.add(user); db.flush()
    other = User(username="u2", password_hash="x", role="user")
    db.add(other); db.flush()
    project = ShortDramaProject(name="项目A", synopsis="测试", owner_id=user.id, source_type="idea")
    db.add(project); db.flush()
    style = V3StyleBibleVersion(project_id=project.id, name="风格", version=1,
        visual_thesis="测试", aspect_ratio="9:16", status="approved")
    db.add(style); db.flush()
    anchor = V3CharacterAnchorVersion(project_id=project.id, stable_key="CH-001", version=1,
        style_bible_id=style.id, status="approved", priority="protagonist", name="主角",
        identity_anchor={"face": "不变"}, controllable_vars={"costume": "白衬衫"}, drift_prohibition=[])
    db.add(anchor)
    db.commit()
    return {"user": user, "other": other, "project": project, "style": style, "anchor": anchor}


class FakeWS:
    def __init__(self, uid: int):
        self.uid = uid
        self.msgs: list[dict] = []

    async def send_json(self, msg):
        self.msgs.append(msg)


def test_ws_isolation():
    manager = ConnectionManager()
    ws1, ws2 = FakeWS(1), FakeWS(2)
    manager.active[ws1] = {"user_id": 1, "projects": set()}
    manager.active[ws2] = {"user_id": 2, "projects": set()}
    manager.subscribe_project(ws1, 100)

    async def run():
        await manager.broadcast({"type": "task.completed"}, owner_id=1)
        await manager.send_to_project(100, 1, {"type": "director.chat_reply"})
        await manager.broadcast({"type": "system.ping"}, owner_id=None)

    asyncio.run(run())
    assert len(ws1.msgs) == 3, ws1.msgs
    assert len(ws2.msgs) == 1 and ws2.msgs[0]["type"] == "system.ping"
    print('✅ T1 两用户事件隔离：user1 收到 3 条，user2 只收到系统广播')

    # 未订阅/非 owner 收不到 director 事件
    sent_check = ConnectionManager()
    ws3 = FakeWS(2)
    sent_check.active[ws3] = {"user_id": 2, "projects": set()}
    sent_check.subscribe_project(ws3, 100)

    async def run2():
        await sent_check.send_to_project(100, 1, {"type": "director.x"})

    asyncio.run(run2())
    assert len(ws3.msgs) == 0
    print('✅ T2 非 owner 即使订阅也收不到 director 事件')


def test_context_selector(db, env):
    pid = env["project"].id
    s1 = context_selector.create_snapshot(db, pid, "guidance")
    s2 = context_selector.create_snapshot(db, pid, "guidance")
    assert s1.id == s2.id
    print('✅ T3 同 revision 快照合并复用')

    env["anchor"].controllable_vars = {"costume": "红裙"}
    db.commit()
    new_hash = context_selector.compute_revision_hash(db, pid)
    assert new_hash != s1.revision_hash
    s3 = context_selector.create_snapshot(db, pid, "guidance")
    db.refresh(s1)
    assert s1.superseded is True and s3.id != s1.id
    print('✅ T4 revision 变化后旧快照标记 superseded')

    try:
        context_selector.create_snapshot(db, pid, "hack")
        assert False
    except ValueError as e:
        assert "未知上下文用途" in str(e)
    print('✅ T5 非法用途拒绝')

    snap = context_selector.create_snapshot(db, pid, "chat", token_budget=10)
    assert snap.truncated is True
    print('✅ T6 token 预算截断生效')


def make_proposal(db, env, changes=None):
    snapshot = context_selector.create_snapshot(db, env["project"].id, "proposal")
    return action_proposal_service.create_proposal(
        db, env["user"].id, env["project"].id, snapshot,
        {
            "action_type": "update_anchor_controllable_vars",
            "target_type": "character_anchor",
            "target_ref": "CH-001",
            "title": "更换服装", "rationale": "剧情需要",
            "changes": changes or [{"field": "costume", "before": "白衬衫", "after": "红裙"}],
            "impact_refs": [],
        },
    )


def test_proposal_security(db, env):
    # 未定义操作拒绝
    snapshot = context_selector.create_snapshot(db, env["project"].id, "proposal")
    try:
        action_proposal_service.create_proposal(
            db, env["user"].id, env["project"].id, snapshot,
            {"action_type": "delete_project", "target_type": "project", "target_ref": "1", "changes": []})
        assert False
    except Exception as e:
        assert "未定义操作类型" in str(e)
    print('✅ T7 未定义操作类型被拒绝（白名单）')

    # 正常应用
    p = make_proposal(db, env)
    assert p.status == "pending"
    result = action_proposal_service.apply_proposal(db, env["user"].id, env["project"].id, p.id)
    assert result.status == "applied"
    db.refresh(env["anchor"])
    assert env["anchor"].controllable_vars["costume"] == "红裙"
    assert env["anchor"].identity_anchor == {"face": "不变"}
    assert env["anchor"].lock_version == 2
    print('✅ T8 应用成功：可控变量更新，身份锚点未动，lock 递增')

    # revision 过期拒绝
    p2 = make_proposal(db, env)
    env["style"].visual_thesis = "新风格"
    db.commit()
    try:
        action_proposal_service.apply_proposal(db, env["user"].id, env["project"].id, p2.id)
        assert False
    except Exception as e:
        assert "过期" in str(e)
    db.refresh(p2)
    assert p2.status == "expired"
    print('✅ T9 revision 过期拒绝执行并标记 expired')

    # 乐观锁冲突
    p3 = make_proposal(db, env)
    env["anchor"].lock_version = 99
    db.commit()
    p3.base_revision_hash = context_selector.compute_revision_hash(db, env["project"].id)
    db.commit()
    try:
        action_proposal_service.apply_proposal(db, env["user"].id, env["project"].id, p3.id)
        assert False
    except Exception as e:
        assert "乐观锁" in str(e)
    print('✅ T10 乐观锁冲突拒绝')

    # 非所有者拒绝
    p4 = make_proposal(db, env)
    try:
        action_proposal_service.apply_proposal(db, env["other"].id, env["project"].id, p4.id)
        assert False
    except Exception as e:
        assert "无权" in str(e)
    print('✅ T11 非所有者应用被拒绝（重新鉴权）')

    # 未授权字段（防御纵深）
    p5 = make_proposal(db, env, changes=[{"field": "identity_anchor", "before": "", "after": "篡改"}])
    # 创建层已过滤 changes；直接改库模拟绕过
    p5.changes = [{"field": "identity_anchor", "before": "", "after": "篡改"}]
    db.commit()
    try:
        action_proposal_service.apply_proposal(db, env["user"].id, env["project"].id, p5.id)
        assert False
    except Exception as e:
        assert "未授权字段" in str(e)
    db.refresh(env["anchor"])
    assert env["anchor"].identity_anchor == {"face": "不变"}
    print('✅ T12 执行器层字段白名单拒绝，身份锚点不可篡改')

    # dismiss
    p6 = make_proposal(db, env)
    r = action_proposal_service.dismiss_proposal(db, env["user"].id, env["project"].id, p6.id, "不合适")
    assert r.status == "dismissed" and r.dismissed_reason == "不合适"
    print('✅ T13 忽略提案记录原因')

    # 批量过期
    pa = make_proposal(db, env)
    pb = make_proposal(db, env)
    env["anchor"].controllable_vars = {"costume": "蓝衣"}
    db.commit()
    changed = action_proposal_service.mark_expired_proposals(db, env["project"].id)
    assert changed == 2
    db.refresh(pa); db.refresh(pb)
    assert pa.status == "expired" and pb.status == "expired"
    print('✅ T14 批处理过期标记')


def test_ai_service_misc(db, env):
    spec = director_ai_service.ACTION_TYPES.get("update_anchor_controllable_vars")
    assert spec and "identity_anchor" not in spec["fields"] and "costume" in spec["fields"]
    remaining = director_ai_service.check_rate_limit(db, env["project"].id)
    assert remaining == director_ai_service.PROJECT_HOURLY_LIMIT
    print('✅ T15 AI 白名单字段 + 项目限额初始值')


def main():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    test_ws_isolation()
    with Session(engine) as db:
        env = make_env(db)
        test_context_selector(db, env)
        test_proposal_security(db, env)
        test_ai_service_misc(db, env)
    print()
    print('All 15 R9 tests passed!')


if __name__ == '__main__':
    main()
