"""V3 第 7 轮：依赖图、Manifest 和连续性审计测试。

覆盖：
- ManifestItem 引用真实版本外键和稳定键
- 上游变更仅影响有依赖边的下游资产
- Blocker 与 optimization 分离；waive 记录操作人和原因
- 已审批 Manifest 不可原地修改
- V3ManifestReference 关联正确
- V3AuditIssueTarget 关联正确
- LLM 语义审计基础功能（无 provider 时优雅降级）
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    ShortDramaProject,
    User,
    V3ArtifactDependency,
    V3AuditIssue,
    V3AuditIssueTarget,
    V3AuditRun,
    V3CharacterAnchorVersion,
    V3GenerationManifest,
    V3LocationViewVersion,
    V3ManifestItem,
    V3ManifestReference,
    V3PropAnchorVersion,
    V3SpatialPlanVersion,
    V3StaleRecord,
    V3StyleBibleVersion,
    V3PaletteVersion,
)
from app.short_drama.v3_director import continuity_service, manifest_service


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
def project_and_user(db: Session):
    user = User(username="testuser", password_hash="x", role="admin")
    db.add(user)
    db.flush()
    project = ShortDramaProject(name="测试短剧", synopsis="测试", owner_id=user.id, source_type="idea")
    db.add(project)
    db.flush()
    return project, user


@pytest.fixture()
def approved_style(db: Session, project_and_user):
    project, _ = project_and_user
    palette = V3PaletteVersion(
        project_id=project.id, name="色卡", scope="general",
        primary_color="#3a4a7a", secondary_color="#5a6a9a",
        accent_color="#ff9a48", neutral_color="#202838",
    )
    db.add(palette)
    db.flush()
    style = V3StyleBibleVersion(
        project_id=project.id, name="风格圣经", version=1,
        visual_thesis="测试风格", aspect_ratio="9:16",
        era="现代", realism="写实",
        palette_version_id=palette.id,
        status="approved",
    )
    db.add(style)
    db.flush()
    return style


@pytest.fixture()
def approved_anchors(db: Session, project_and_user, approved_style):
    project, _ = project_and_user
    char = V3CharacterAnchorVersion(
        project_id=project.id, stable_key="CH-001", version=1,
        style_bible_id=approved_style.id, status="approved",
        priority="protagonist", name="主角",
        identity_anchor={"face_ratios": "标准"}, controllable_vars={},
        drift_prohibition=["不得偏离身份锚点"],
    )
    db.add(char)
    prop = V3PropAnchorVersion(
        project_id=project.id, stable_key="PR-001", version=1,
        style_bible_id=approved_style.id, status="approved",
        name="关键道具", size="中", material="金属",
        wear_condition="完好", owner_character_key="CH-001",
        priority_rank=1,
    )
    db.add(prop)
    spatial = V3SpatialPlanVersion(
        project_id=project.id, location_stable_key="LOC-001",
        version=1, plan_kind="exterior",
        topology={}, floor_plan={},
        status="approved", name="外景",
    )
    db.add(spatial)
    db.flush()
    location = V3LocationViewVersion(
        project_id=project.id, spatial_plan_id=spatial.id,
        stable_key="LV-001", version=1, view_angle="正面",
        status="approved", name="主视图",
    )
    db.add(location)
    db.flush()
    return {"char": char, "prop": prop, "spatial": spatial, "location": location}


# --------------------------------------------------------------------------- #
# 依赖图测试
# --------------------------------------------------------------------------- #

class TestDependencyGraph:
    def test_build_dependency_graph_creates_edges(self, db: Session, approved_anchors):
        project_id = approved_anchors["char"].project_id
        count = manifest_service.build_dependency_graph(db, project_id)

        # character_anchor → style_bible (1 edge)
        # prop_anchor → style_bible (1 edge)
        # prop_anchor → character_anchor (1 edge, wardrobe)
        # location_view → spatial_plan (1 edge)
        assert count == 4
        deps = manifest_service.list_dependencies(db, project_id)
        assert len(deps) == 4

    def test_propagate_stale_only_affects_downstream(self, db: Session, approved_anchors):
        project_id = approved_anchors["char"].project_id
        manifest_service.build_dependency_graph(db, project_id)

        # 上游 style_bible 变更 → 应该标记 character_anchor 和 prop_anchor 过期
        count = manifest_service.propagate_stale(
            db, project_id, "style_bible", f"STYLE-v{approved_anchors['char'].style_bible_id}", "style_changed"
        )
        assert count == 2  # character_anchor + prop_anchor

        stale = manifest_service.list_stale_records(db, project_id, status="open")
        assert len(stale) == 2
        asset_types = {s.asset_type for s in stale}
        assert "character_anchor" in asset_types
        assert "prop_anchor" in asset_types
        # location_view 不依赖 style_bible，不应该被标记
        assert "location_view" not in asset_types

    def test_propagate_stale_skips_duplicates(self, db: Session, approved_anchors):
        project_id = approved_anchors["char"].project_id
        manifest_service.build_dependency_graph(db, project_id)
        upstream_ref = f"STYLE-v{approved_anchors['char'].style_bible_id}"

        manifest_service.propagate_stale(db, project_id, "style_bible", upstream_ref, "style_changed")
        count2 = manifest_service.propagate_stale(db, project_id, "style_bible", upstream_ref, "style_changed")
        assert count2 == 0  # 不会重复创建

    def test_propagate_stale_for_spatial(self, db: Session, approved_anchors):
        project_id = approved_anchors["char"].project_id
        manifest_service.build_dependency_graph(db, project_id)

        count = manifest_service.propagate_stale(
            db, project_id, "spatial_plan", f"SPL-{approved_anchors['spatial'].id}", "spatial_changed"
        )
        assert count == 1  # 只有 location_view 依赖 spatial_plan
        stale = manifest_service.list_stale_records(db, project_id, status="open")
        assert stale[0].asset_type == "location_view"

    def test_resolve_stale(self, db: Session, approved_anchors):
        project_id = approved_anchors["char"].project_id
        manifest_service.build_dependency_graph(db, project_id)
        manifest_service.propagate_stale(
            db, project_id, "style_bible", f"STYLE-v{approved_anchors['char'].style_bible_id}", "style_changed"
        )
        stale = manifest_service.list_stale_records(db, project_id, status="open")
        assert len(stale) == 2

        rec = manifest_service.resolve_stale(db, stale[0].id, 1, "已重新生成")
        assert rec.status == "resolved"
        assert rec.resolution == "已重新生成"

        remaining = manifest_service.list_stale_records(db, project_id, status="open")
        assert len(remaining) == 1


# --------------------------------------------------------------------------- #
# Manifest 测试
# --------------------------------------------------------------------------- #

class TestManifest:
    def test_build_manifest_from_approved(self, db: Session, approved_anchors):
        project_id = approved_anchors["char"].project_id
        m = manifest_service.build_manifest_from_approved(db, project_id, "测试清单")

        assert m.status == "draft"
        assert m.version == 1
        assert m.style_bible_id is not None
        assert len(m.items) > 0

        # 角色锚点应该有 3 个 item (front/side/back)
        char_items = [i for i in m.items if i.asset_type == "character_anchor"]
        assert len(char_items) == 3
        views = {i.required_view for i in char_items}
        assert views == {"front", "side", "back"}

        # 道具锚点应该有 1 个 item (hero)
        prop_items = [i for i in m.items if i.asset_type == "prop_anchor"]
        assert len(prop_items) == 1
        assert prop_items[0].required_view == "hero"

        # 地点视图应该有 1 个 item
        loc_items = [i for i in m.items if i.asset_type == "location_view"]
        assert len(loc_items) == 1

    def test_manifest_items_have_references(self, db: Session, approved_anchors):
        project_id = approved_anchors["char"].project_id
        m = manifest_service.build_manifest_from_approved(db, project_id, "测试清单")

        # 每个 item 应该有 V3ManifestReference 关联
        for item in m.items:
            assert len(item.references) > 0
            for ref in item.references:
                assert ref.reference_type in ("character_anchor", "prop_anchor", "location_view", "spatial_plan")
                assert ref.reference_key  # 非空 stable key
                assert ref.reference_version_id is not None  # 真实版本外键

    def test_manifest_reference_unique_constraint(self, db: Session, approved_anchors):
        """每个 ManifestItem 的同一引用类型+键组合应该是唯一的。"""
        project_id = approved_anchors["char"].project_id
        m = manifest_service.build_manifest_from_approved(db, project_id, "测试清单")

        for item in m.items:
            ref_keys = [(r.reference_type, r.reference_key) for r in item.references]
            assert len(ref_keys) == len(set(ref_keys)), "引用重复"

    def test_approve_manifest(self, db: Session, approved_anchors):
        project, user = approved_anchors["char"].project_id, 1
        m = manifest_service.build_manifest_from_approved(db, project, "")
        approved = manifest_service.approve_manifest(db, project, m.id, user)

        assert approved.status == "approved"
        assert approved.approved_by == user
        assert approved.approved_at is not None

    def test_approved_manifest_cannot_be_modified(self, db: Session, approved_anchors):
        """已批准 Manifest 不可原地修改：再次调用 approve 应失败。"""
        project_id = approved_anchors["char"].project_id
        m = manifest_service.build_manifest_from_approved(db, project_id, "")
        manifest_service.approve_manifest(db, project_id, m.id, 1)

        with pytest.raises(ValueError, match="不可批准"):
            manifest_service.approve_manifest(db, project_id, m.id, 1)

    def test_manifest_version_increment(self, db: Session, approved_anchors):
        project_id = approved_anchors["char"].project_id
        m1 = manifest_service.build_manifest_from_approved(db, project_id, "")
        m2 = manifest_service.build_manifest_from_approved(db, project_id, "")
        assert m2.version == m1.version + 1

    def test_manifest_out_serialization(self, db: Session, approved_anchors):
        project_id = approved_anchors["char"].project_id
        m = manifest_service.build_manifest_from_approved(db, project_id, "测试")
        out = manifest_service.manifest_out(m, m.items)

        assert out["id"] == m.id
        assert out["version"] == m.version
        assert out["status"] == "draft"
        assert len(out["items"]) == len(m.items)
        for item_out in out["items"]:
            assert "references" in item_out
            assert isinstance(item_out["references"], list)
            assert len(item_out["references"]) > 0


# --------------------------------------------------------------------------- #
# 连续性审计测试
# --------------------------------------------------------------------------- #

class TestContinuityAudit:
    def test_create_audit_run(self, db: Session, project_and_user):
        project, _ = project_and_user
        run = continuity_service.create_audit_run(db, project.id)
        assert run.status == "running"
        assert run.started_at is not None

    def test_run_rule_audit_no_issues(self, db: Session, project_and_user):
        """没有数据时规则审计应该返回 0 个问题。"""
        project, _ = project_and_user
        run = continuity_service.create_audit_run(db, project.id)
        count = continuity_service.run_rule_audit(db, project.id, run)
        assert count == 0

    def test_finish_audit_summary(self, db: Session, project_and_user):
        project, _ = project_and_user
        run = continuity_service.create_audit_run(db, project.id)
        continuity_service.run_rule_audit(db, project.id, run)
        run = continuity_service.finish_audit(db, run)

        assert run.status == "completed"
        assert run.finished_at is not None
        assert "blockers" in run.summary
        assert "total_issues" in run.summary
        assert run.summary["total_issues"] == 0

    def test_waive_issue_requires_reason(self, db: Session, project_and_user):
        project, _ = project_and_user
        run = continuity_service.create_audit_run(db, project.id)

        # 手动创建一个问题来测试 waive
        from app.models.v3_director import V3AuditIssue
        issue = V3AuditIssue(
            run_id=run.id, dimension="identity", severity="risk",
            description="测试问题", affected_assets=[],
        )
        db.add(issue)
        db.flush()

        # 空原因应该被拒绝
        with pytest.raises(ValueError, match="豁免必须提供原因"):
            continuity_service.waive_issue(db, issue.id, 1, "")

        # 有效豁免
        waived = continuity_service.waive_issue(db, issue.id, 1, "误报")
        assert waived.status == "waived"
        assert waived.waived_by == 1
        assert waived.waive_reason == "误报"

    def test_waive_already_processed_fails(self, db: Session, project_and_user):
        from app.models.v3_director import V3AuditIssue
        project, _ = project_and_user
        run = continuity_service.create_audit_run(db, project.id)
        issue = V3AuditIssue(
            run_id=run.id, dimension="identity", severity="risk",
            description="测试问题", affected_assets=[],
        )
        db.add(issue)
        db.flush()
        continuity_service.waive_issue(db, issue.id, 1, "处理")

        with pytest.raises(ValueError, match="问题已处理"):
            continuity_service.waive_issue(db, issue.id, 1, "再次")

    def test_audit_issue_targets_created(self, db: Session, project_and_user):
        """V3AuditIssueTarget 应该正确关联到审计问题。"""
        from app.models.v3_director import V3AuditIssue
        project, _ = project_and_user
        run = continuity_service.create_audit_run(db, project.id)
        issue = V3AuditIssue(
            run_id=run.id, dimension="identity", severity="risk",
            description="测试问题", affected_assets=[],
        )
        db.add(issue)
        db.flush()

        # 创建关联目标
        target = V3AuditIssueTarget(
            audit_issue_id=issue.id, target_type="character", target_ref="CH-001",
        )
        db.add(target)
        db.commit()
        db.refresh(issue)

        assert len(issue.targets) == 1
        assert issue.targets[0].target_type == "character"
        assert issue.targets[0].target_ref == "CH-001"

    def test_blocker_vs_optimization_separation(self, db: Session, project_and_user):
        """Blocker 和 optimization 应在 summary 中分别统计。"""
        from app.models.v3_director import V3AuditIssue
        project, _ = project_and_user
        run = continuity_service.create_audit_run(db, project.id)

        for i in range(3):
            db.add(V3AuditIssue(
                run_id=run.id, dimension="causal", severity="blocker",
                description=f"阻塞问题{i}", affected_assets=[],
            ))
        for i in range(2):
            db.add(V3AuditIssue(
                run_id=run.id, dimension="color", severity="optimization",
                description=f"优化建议{i}", affected_assets=[],
            ))
        db.commit()

        run = continuity_service.finish_audit(db, run)
        assert run.summary["blockers"] == 3
        assert run.summary["optimizations"] == 2
        assert run.summary["total_issues"] == 5
        assert "blocker" in run.summary["conclusion"]

    def test_issue_out_includes_targets(self, db: Session, project_and_user):
        from app.models.v3_director import V3AuditIssue
        project, _ = project_and_user
        run = continuity_service.create_audit_run(db, project.id)
        issue = V3AuditIssue(
            run_id=run.id, dimension="identity", severity="risk",
            description="测试问题", affected_assets=[],
        )
        db.add(issue)
        db.flush()
        db.add(V3AuditIssueTarget(
            audit_issue_id=issue.id, target_type="scene", target_ref="SC-001",
        ))
        db.commit()
        db.refresh(issue)

        out = continuity_service.issue_out(issue)
        assert "targets" in out
        assert len(out["targets"]) == 1
        assert out["targets"][0]["target_type"] == "scene"
        assert out["targets"][0]["target_ref"] == "SC-001"


# --------------------------------------------------------------------------- #
# LLM 语义审计测试
# --------------------------------------------------------------------------- #

class TestLLMAudit:
    def test_llm_audit_graceful_without_provider(self, db: Session, project_and_user):
        """没有 AI provider 配置时，LLM 审计应优雅降级返回 0。"""
        project, _ = project_and_user
        run = continuity_service.create_audit_run(db, project.id)
        count = continuity_service.run_llm_audit(db, project.id, run)
        assert count == 0  # 无 provider 不阻塞

    def test_llm_audit_does_not_override_rule_results(self, db: Session, project_and_user):
        """LLM 审计不能覆盖已有规则结果。"""
        from app.models.v3_director import V3AuditIssue
        project, _ = project_and_user
        run = continuity_service.create_audit_run(db, project.id)

        # 手动添加一个规则结果
        rule_issue = V3AuditIssue(
            run_id=run.id, dimension="identity", severity="blocker",
            description="规则检测的身份问题", affected_assets=[],
        )
        db.add(rule_issue)
        db.commit()

        # LLM 审计在无 provider 时返回 0，不会新增也不会覆盖
        count = continuity_service.run_llm_audit(db, project.id, run)
        assert count == 0

        issues = db.query(V3AuditIssue).filter(V3AuditIssue.run_id == run.id).all()
        assert len(issues) == 1  # 只有规则结果


# --------------------------------------------------------------------------- #
# 综合追溯测试
# --------------------------------------------------------------------------- #

class TestTraceability:
    def test_manifest_item_traceability(self, db: Session, approved_anchors):
        """可从任一 ManifestItem 追溯来源故事、风格、锚点、prompt 和审批链。"""
        project_id = approved_anchors["char"].project_id
        m = manifest_service.build_manifest_from_approved(db, project_id, "追溯测试")
        manifest_service.approve_manifest(db, project_id, m.id, 1)

        for item in m.items:
            # 追溯到 manifest
            assert item.manifest_id == m.id
            # 追溯到风格圣经版本
            assert item.style_version_id is not None
            # 追溯到引用的锚点
            assert len(item.references) > 0
            for ref in item.references:
                assert ref.reference_key  # 有 stable key
                assert ref.reference_version_id is not None  # 有真实版本 FK
            # 有 prompt
            assert item.prompt
            # 审批链：manifest 已批准
            assert m.status == "approved"
            assert m.approved_by is not None
            assert m.approved_at is not None