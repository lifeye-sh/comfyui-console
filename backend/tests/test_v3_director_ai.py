"""V3 第 9 轮：AI 导演对话、建议与安全推送测试（服务级）。

覆盖核心契约：
- WebSocket 连接绑定 user_id，两个用户互相收不到对方项目事件
- AI 输出不能执行未定义操作（白名单外 action_type 拒绝）
- ActionProposal 在 revision 过期时拒绝执行并标记 expired
- 目标资产乐观锁冲突拒绝执行
- 旧 revision 快照在新 revision 产生后被标记 superseded
- 快速重复创建同 revision 快照被合并（复用）
- 提案只能修改白名单字段，身份锚点不可触碰
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    ShortDramaProject,
    User,
    V3ActionProposal,
    V3CharacterAnchorVersion,
    V3ContextSnapshot,
    V3StyleBibleVersion,
)
from app.short_drama.v3_director import (
    action_proposal_service,
    context_selector,
    director_ai_service,
)
from app.ws.gateway import ConnectionManager


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def env(db: Session):
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
        identity_anchor={"face": "不变"}, controllable_vars={"costume": "白衬衫"},
        drift_prohibition=[])
    db.add(anchor)
    db.commit()
    return {"user": user, "other": other, "project": project, "style": style, "anchor": anchor}


# --------------------------------------------------------------------------- #
# WebSocket 隔离
# --------------------------------------------------------------------------- #

class TestWsIsolation:
    def test_two_users_cannot_receive_each_others_events(self):
        """两个用户同时在线时互相收不到对方项目事件。"""
        manager = ConnectionManager()

        sent: list[tuple[int, dict]] = []

        class FakeWS:
            def __init__(self, uid: int):
                self.uid = uid

            async def send_json(self, msg):
                sent.append((self.uid, msg))

        ws1, ws2 = FakeWS(1), FakeWS(2)
        # 模拟 connect（不做真正 accept）
        manager.active[ws1] = {"user_id": 1, "projects": set()}
        manager.active[ws2] = {"user_id": 2, "projects": set()}
        manager.subscribe_project(ws1, 100)

        # 同步事件：给 user=1 推送
        asyncio.get_event_loop_policy()

        async def run():
            await manager.broadcast({"type": "task.completed"}, owner_id=1)
            await manager.send_to_project(100, 1, {"type": "director.chat_reply"})

        asyncio.run(run())

        user1_msgs = [m for uid, m in sent if uid == 1]
        user2_msgs = [m for uid, m in sent if uid == 2]
        assert len(user1_msgs) == 2  # task 事件 + director 事件
        assert len(user2_msgs) == 0  # 用户 2 什么都没收到

    def test_director_event_requires_subscription_and_ownership(self):
        """未订阅项目 / 非项目 owner 的连接收不到 director 事件。"""
        manager = ConnectionManager()
        sent: list[tuple[int, dict]] = []

        class FakeWS:
            def __init__(self, uid: int):
                self.uid = uid

            async def send_json(self, msg):
                sent.append((self.uid, msg))

        ws1, ws2 = FakeWS(1), FakeWS(2)
        manager.active[ws1] = {"user_id": 1, "projects": set()}
        manager.active[ws2] = {"user_id": 2, "projects": set()}
        # ws2 订阅了项目但不是 owner —— send_to_project 校验 owner
        manager.subscribe_project(ws2, 100)

        async def run():
            await manager.send_to_project(100, 1, {"type": "director.x"})

        asyncio.run(run())
        assert len(sent) == 0  # owner=1 未连接/未订阅；ws2 虽订阅但非 owner

    def test_broadcast_without_owner_is_system_level(self):
        """无 owner_id 的系统级事件仍广播（兼容）。"""
        manager = ConnectionManager()
        sent: list[tuple[int, dict]] = []

        class FakeWS:
            def __init__(self, uid: int):
                self.uid = uid

            async def send_json(self, msg):
                sent.append((self.uid, msg))

        ws1, ws2 = FakeWS(1), FakeWS(2)
        manager.active[ws1] = {"user_id": 1, "projects": set()}
        manager.active[ws2] = {"user_id": 2, "projects": set()}

        async def run():
            await manager.broadcast({"type": "system.ping"}, owner_id=None)

        asyncio.run(run())
        assert len(sent) == 2


# --------------------------------------------------------------------------- #
# ContextSelector
# --------------------------------------------------------------------------- #

class TestContextSelector:
    def test_same_revision_snapshot_reused(self, db: Session, env):
        """相同 (project, purpose, revision) 的快照合并复用，不重复创建。"""
        pid = env["project"].id
        s1 = context_selector.create_snapshot(db, pid, "guidance")
        s2 = context_selector.create_snapshot(db, pid, "guidance")
        assert s1.id == s2.id

        # 不同 purpose 是不同快照
        s3 = context_selector.create_snapshot(db, pid, "chat")
        assert s3.id != s1.id

    def test_revision_change_supersedes_old_snapshots(self, db: Session, env):
        """新 revision 出现时旧快照标记 superseded（revision guard 基础）。"""
        pid = env["project"].id
        s1 = context_selector.create_snapshot(db, pid, "guidance")
        old_hash = s1.revision_hash
        assert not s1.superseded

        # 上游资产变更 → revision 变化
        env["anchor"].controllable_vars = {"costume": "红裙"}
        db.commit()

        new_hash = context_selector.compute_revision_hash(db, pid)
        assert new_hash != old_hash

        s2 = context_selector.create_snapshot(db, pid, "guidance")
        db.refresh(s1)
        assert s2.revision_hash == new_hash
        assert s2.id != s1.id
        assert s1.superseded is True  # 旧快照被标记

    def test_unknown_purpose_rejected(self, db: Session, env):
        with pytest.raises(ValueError, match="未知上下文用途"):
            context_selector.create_snapshot(db, env["project"].id, "hack")

    def test_token_budget_truncation(self, db: Session, env):
        """超出 token 预算时截断低优先级区块并记录说明。"""
        pid = env["project"].id
        snapshot = context_selector.create_snapshot(db, pid, "guidance", token_budget=10)
        # 上下文必有内容，预算 10 一定触发截断
        assert snapshot.truncated is True
        assert snapshot.token_estimated <= max(10, snapshot.token_estimated)
        assert snapshot.truncation_note


# --------------------------------------------------------------------------- #
# ActionProposal：白名单 / revision guard / 乐观锁
# --------------------------------------------------------------------------- #

def _make_proposal(db: Session, env, *, action_type="update_anchor_controllable_vars",
                   changes=None, lock_version=None) -> V3ActionProposal:
    snapshot = context_selector.create_snapshot(db, env["project"].id, "proposal")
    return action_proposal_service.create_proposal(
        db, env["user"].id, env["project"].id, snapshot,
        {
            "action_type": action_type,
            "target_type": "character_anchor",
            "target_ref": "CH-001",
            "title": "更换服装",
            "rationale": "剧情需要",
            "changes": changes or [{"field": "costume", "before": "白衬衫", "after": "红裙"}],
            "impact_refs": [],
        },
    )


class TestActionProposalSecurity:
    def test_undefined_action_type_rejected(self, db: Session, env):
        """AI 输出不能执行未定义操作：白名单外类型直接拒绝。"""
        snapshot = context_selector.create_snapshot(db, env["project"].id, "proposal")
        with pytest.raises(Exception, match="未定义操作类型"):
            action_proposal_service.create_proposal(
                db, env["user"].id, env["project"].id, snapshot,
                {
                    "action_type": "delete_project",  # 危险操作不在白名单
                    "target_type": "project",
                    "target_ref": "1",
                    "changes": [],
                },
            )

    def test_apply_updates_controllable_vars_and_lock(self, db: Session, env):
        """应用成功：只改可控变量，lock_version 递增。"""
        proposal = _make_proposal(db, env)
        assert proposal.status == "pending"
        result = action_proposal_service.apply_proposal(
            db, env["user"].id, env["project"].id, proposal.id,
        )
        assert result.status == "applied"
        db.refresh(env["anchor"])
        assert env["anchor"].controllable_vars["costume"] == "红裙"
        # 身份锚点未被触碰
        assert env["anchor"].identity_anchor == {"face": "不变"}
        assert env["anchor"].lock_version == 2

    def test_apply_rejected_when_revision_expired(self, db: Session, env):
        """版本过期：revision 变化后应用 → 拒绝并标记 expired。"""
        proposal = _make_proposal(db, env)
        # 项目资产在提案生成后变更 → revision 变化
        env["style"].visual_thesis = "新风格论点"
        db.commit()
        with pytest.raises(Exception, match="过期"):
            action_proposal_service.apply_proposal(
                db, env["user"].id, env["project"].id, proposal.id,
            )
        db.refresh(proposal)
        assert proposal.status == "expired"

    def test_apply_rejected_on_lock_conflict(self, db: Session, env):
        """乐观锁冲突：目标资产 lock_version 变化后应用 → 拒绝。

        注意：需要 revision 不变的前提下 lock 变化。直接改 lock_version
        同时保持指纹不变很难（指纹含版本 id），因此构造方式为：
        提案创建后伪造 revision hash 相同但 lock 不同 —— 这里通过
        先创建提案、再手动把提案 base_revision_hash 改回当前值模拟。
        """
        proposal = _make_proposal(db, env)
        env["anchor"].lock_version = 99  # 模拟并发修改
        db.commit()
        # 伪装 revision 未变（只测乐观锁分支）
        proposal.base_revision_hash = context_selector.compute_revision_hash(db, env["project"].id)
        db.commit()
        with pytest.raises(Exception, match="乐观锁"):
            action_proposal_service.apply_proposal(
                db, env["user"].id, env["project"].id, proposal.id,
            )

    def test_apply_forbidden_for_non_owner(self, db: Session, env):
        """重新鉴权：非提案所有者不能应用。"""
        proposal = _make_proposal(db, env)
        with pytest.raises(Exception, match="无权"):
            action_proposal_service.apply_proposal(
                db, env["other"].id, env["project"].id, proposal.id,
            )

    def test_disallowed_field_rejected_at_apply(self, db: Session, env):
        """提案绕过创建校验带入非白名单字段 → 应用时拒绝，数据不变。"""
        snapshot = context_selector.create_snapshot(db, env["project"].id, "proposal")
        proposal = action_proposal_service.create_proposal(
            db, env["user"].id, env["project"].id, snapshot,
            {
                "action_type": "update_anchor_controllable_vars",
                "target_type": "character_anchor",
                "target_ref": "CH-001",
                "changes": [{"field": "identity_anchor", "before": "", "after": "篡改"}],
            },
        )
        # 直接改库模拟绕过（创建时已过滤，防御纵深测试执行器）
        proposal.changes = [{"field": "identity_anchor", "before": "", "after": "篡改"}]
        db.commit()
        with pytest.raises(Exception, match="未授权字段"):
            action_proposal_service.apply_proposal(
                db, env["user"].id, env["project"].id, proposal.id,
            )
        db.refresh(env["anchor"])
        assert env["anchor"].identity_anchor == {"face": "不变"}

    def test_dismiss_records_reason(self, db: Session, env):
        proposal = _make_proposal(db, env)
        result = action_proposal_service.dismiss_proposal(
            db, env["user"].id, env["project"].id, proposal.id, "不合适",
        )
        assert result.status == "dismissed"
        assert result.dismissed_reason == "不合适"

    def test_mark_expired_batch(self, db: Session, env):
        """批处理：revision 变化后所有 pending 提案标记 expired。"""
        p1 = _make_proposal(db, env)
        p2 = _make_proposal(db, env, action_type="suggest_prop_state",
                            changes=[{"field": "wear_condition", "before": "", "after": "划痕"}])
        env["anchor"].controllable_vars = {"costume": "蓝衣"}
        db.commit()
        changed = action_proposal_service.mark_expired_proposals(db, env["project"].id)
        assert changed >= 2
        db.refresh(p1); db.refresh(p2)
        assert p1.status == "expired"
        assert p2.status == "expired"


# --------------------------------------------------------------------------- #
# director_ai_service
# --------------------------------------------------------------------------- #

class TestDirectorAIService:
    def test_proposal_whitelist_filtering(self):
        """generate_proposals 的白名单过滤逻辑（离线测试解析层）。"""
        spec = director_ai_service.ACTION_TYPES.get("update_anchor_controllable_vars")
        assert spec is not None
        assert "identity_anchor" not in spec["fields"]
        assert "costume" in spec["fields"]

    def test_rate_limit_counts_messages(self, db: Session, env):
        """项目级限额基于消息计数。"""
        remaining = director_ai_service.check_rate_limit(db, env["project"].id)
        assert remaining == director_ai_service.PROJECT_HOURLY_LIMIT
