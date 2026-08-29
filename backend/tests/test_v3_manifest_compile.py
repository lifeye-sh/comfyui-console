"""V3 第 8 轮：Manifest 编译接入生产链路测试。

覆盖：
- 动态参数映射完整（prompt/negative/aspect_ratio 注入 param_schema）
- 媒体类型校验（image 生成类型匹配、素材归属）
- 编译预览不创建任务；校验失败整批拒绝
- 幂等创建（相同 idempotency_key 复用）
- 任务成功后 refresh-status 回写 ManifestItem 状态
- 无 Manifest 的 V2.1 生产链路不退化（_prompt fallback 保留）
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    Batch,
    GenerationType,
    ShortDramaProject,
    Task,
    User,
    V3CharacterAnchorVersion,
    V3GenerationManifest,
    V3LocationViewVersion,
    V3ManifestItem,
    V3ManifestItemTaskLink,
    V3PaletteVersion,
    V3PropAnchorVersion,
    V3SpatialPlanVersion,
    V3StaleRecord,
    V3StyleBibleVersion,
    Workflow,
    WorkflowVersion,
)
from app.short_drama.v3_director import manifest_compiler
from app.short_drama.v3_director.production_intent_service import (
    ManifestCompileError,
    build_intent,
    build_intents,
)


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def setup(db: Session):
    """完整环境：用户、项目、已审批清单（5 项）、图片生成类型与工作流。"""
    user = User(username="u", password_hash="x", role="admin")
    db.add(user); db.flush()
    project = ShortDramaProject(name="测试", synopsis="测试", owner_id=user.id, source_type="idea")
    db.add(project); db.flush()

    palette = V3PaletteVersion(project_id=project.id, version=1, name="色卡", scope="general",
        primary_color="#333333", secondary_color="#444444", accent_color="#555555", neutral_color="#222222")
    db.add(palette); db.flush()
    style = V3StyleBibleVersion(project_id=project.id, name="风格", version=1,
        visual_thesis="测试", aspect_ratio="9:16", era="现代", realism="写实",
        palette_version_id=palette.id, status="approved")
    db.add(style); db.flush()

    char = V3CharacterAnchorVersion(project_id=project.id, stable_key="CH-001", version=1,
        style_bible_id=style.id, status="approved", priority="protagonist", name="主角",
        identity_anchor={}, controllable_vars={}, drift_prohibition=["不得漂移"])
    db.add(char)
    prop = V3PropAnchorVersion(project_id=project.id, stable_key="PR-001", version=1,
        style_bible_id=style.id, status="approved", name="道具", size="中", material="金属",
        wear_condition="完好", owner_character_key="CH-001", priority_rank=1)
    db.add(prop)
    spatial = V3SpatialPlanVersion(project_id=project.id, location_stable_key="LOC-001",
        version=1, plan_kind="exterior", topology={}, floor_plan={}, status="approved", name="外景")
    db.add(spatial); db.flush()
    location = V3LocationViewVersion(project_id=project.id, spatial_plan_id=spatial.id,
        stable_key="LV-001", version=1, view_angle="正面", status="approved", name="主视图")
    db.add(location); db.flush()

    manifest = V3GenerationManifest(project_id=project.id, version=1, status="draft",
        style_bible_id=style.id, notes="")
    db.add(manifest); db.flush()
    for i in range(3):
        item = V3ManifestItem(manifest_id=manifest.id, project_id=project.id,
            asset_stable_key=f"CH-001", asset_type="character_anchor",
            required_view=["front", "side", "back"][i], scenes=[],
            reference_ids=[], prompt=f"角色主角 {['正面','侧面','背面'][i]} 视图",
            negative_constraints="面部变形", aspect_ratio="9:16")
        db.add(item)
    item4 = V3ManifestItem(manifest_id=manifest.id, project_id=project.id,
        asset_stable_key="PR-001", asset_type="prop_anchor", required_view="hero", scenes=[],
        reference_ids=[], prompt="道具特写", negative_constraints="变形", aspect_ratio="9:16")
    db.add(item4)
    item5 = V3ManifestItem(manifest_id=manifest.id, project_id=project.id,
        asset_stable_key="LV-001", asset_type="location_view", required_view="view", scenes=[],
        reference_ids=[], prompt="地点主视图", negative_constraints="透视错误", aspect_ratio="9:16")
    db.add(item5)
    db.flush()

    # 图片生成类型 + 工作流（prompt 必填，aspect_ratio 必填）
    gen_type = GenerationType(code=f"v3_img_{uuid4().hex[:8]}", name="V3 图片", media_type="image", enabled=True)
    db.add(gen_type); db.flush()
    workflow = Workflow(owner_id=user.id, generation_type_id=gen_type.id, name="V3 图片工作流",
        media_type="image", status="active")
    db.add(workflow); db.flush()
    version = WorkflowVersion(
        workflow_id=workflow.id, version=1,
        api_json={
            "1": {"class_type": "Text", "inputs": {"text": ""}},
            "2": {"class_type": "Ratio", "inputs": {"value": ""}},
        },
        param_schema=[
            {"key": "prompt", "label": "提示词", "type": "textarea", "node": "1", "path": "inputs.text", "required": True, "default": ""},
            {"key": "aspect_ratio", "label": "比例", "type": "text", "node": "2", "path": "inputs.value", "required": True, "default": "1:1"},
        ],
        output_mapping={},
    )
    db.add(version); db.flush()
    workflow.current_version_id = version.id
    gen_type.default_workflow_id = workflow.id
    db.commit()
    db.refresh(manifest)

    return {
        "user": user, "project": project, "manifest": manifest,
        "gen_type": gen_type, "workflow": workflow, "version": version,
    }


class TestBuildIntents:
    def test_build_intents_basic_mapping(self, db: Session, setup):
        """动态参数映射：prompt 注入、aspect_ratio 注入。"""
        env = setup
        manifest, intents = build_intents(
            db, env["user"].id, env["project"].id, env["manifest"].id,
            env["gen_type"].id, env["version"].id,
        )
        assert manifest.status == "approved"
        assert len(intents) == 5
        for intent in intents:
            assert intent.validation_errors == []
            assert intent.params["prompt"]  # prompt 已注入
            assert intent.params["aspect_ratio"] == "9:16"

    def test_draft_manifest_rejected(self, db: Session, setup):
        """未审批清单不能编译。"""
        env = setup
        env["manifest"].status = "draft"
        db.commit()
        with pytest.raises(ManifestCompileError, match="尚未审批"):
            build_intents(
                db, env["user"].id, env["project"].id, env["manifest"].id,
                env["gen_type"].id, env["version"].id,
            )

    def test_media_type_mismatch(self, db: Session, setup):
        """生成类型媒体类型与资产期望不匹配 → 报错误。"""
        env = setup
        video_type = GenerationType(code=f"v3_vid_{uuid4().hex[:8]}", name="V3 视频", media_type="video", enabled=True)
        db.add(video_type); db.flush()
        _, intents = build_intents(
            db, env["user"].id, env["project"].id, env["manifest"].id,
            video_type.id, None,
        )
        assert intents
        assert any(
            e["code"] == "media_type_mismatch"
            for intent in intents for e in intent.validation_errors
        )

    def test_required_missing_reports_error(self, db: Session, setup):
        """覆盖空 prompt → 必填校验报错。"""
        env = setup
        _, intents = build_intents(
            db, env["user"].id, env["project"].id, env["manifest"].id,
            env["gen_type"].id, env["version"].id,
            overrides={"prompt": ""},
        )
        assert any(
            e["code"] == "required"
            for intent in intents for e in intent.validation_errors
        )

    def test_unknown_override_warns(self, db: Session, setup):
        """未知覆盖参数产生 warning 而非 error。"""
        env = setup
        _, intents = build_intents(
            db, env["user"].id, env["project"].id, env["manifest"].id,
            env["gen_type"].id, env["version"].id,
            overrides={"nonexistent_key": 123},
        )
        assert any(
            w["code"] == "unknown_override"
            for intent in intents for w in intent.validation_warnings
        )
        # 不应因此产生 error
        assert all(intent.validation_errors == [] for intent in intents)

    def test_item_ids_filter(self, db: Session, setup):
        """指定 item_ids 只编译指定项。"""
        env = setup
        items = db.query(V3ManifestItem).filter(V3ManifestItem.manifest_id == env["manifest"].id).all()
        subset = items[:2]
        _, intents = build_intents(
            db, env["user"].id, env["project"].id, env["manifest"].id,
            env["gen_type"].id, env["version"].id,
            item_ids=[i.id for i in subset],
        )
        assert len(intents) == 2
        assert {i.manifest_item_id for i in intents} == {i.id for i in subset}


class TestManifestCompiler:
    def test_compile_preview_no_tasks(self, db: Session, setup):
        """编译预览不创建任何 Task/Batch。"""
        env = setup
        result = manifest_compiler.compile_preview(
            db, env["user"].id, env["project"].id, env["manifest"].id,
            env["gen_type"].id, env["version"].id,
        )
        assert result["total"] == 5
        assert result["ok_count"] == 5
        assert result["error_count"] == 0
        assert db.query(Task).count() == 0
        assert db.query(Batch).count() == 0

    def test_create_tasks_and_idempotency(self, db: Session, setup):
        """创建任务 + 幂等复用。"""
        env = setup
        key = "compile-run-1"
        result = manifest_compiler.create_tasks_from_manifest(
            db, env["user"].id, env["project"].id, env["manifest"].id,
            env["gen_type"].id, env["version"].id,
            idempotency_key=key, submit=True,
        )
        assert result["created"] == 5
        assert result["reused"] == 0
        assert result["batch_id"] is not None
        # 任务入队（PENDING）
        tasks = db.query(Task).all()
        assert len(tasks) == 5
        assert all(t.status == "PENDING" for t in tasks)
        # ManifestItem 状态更新为 queued
        items = db.query(V3ManifestItem).filter(V3ManifestItem.manifest_id == env["manifest"].id).all()
        assert all(i.status == "queued" for i in items)
        # 幂等重复调用
        result2 = manifest_compiler.create_tasks_from_manifest(
            db, env["user"].id, env["project"].id, env["manifest"].id,
            env["gen_type"].id, env["version"].id,
            idempotency_key=key, submit=True,
        )
        assert result2["created"] == 0
        assert result2["reused"] == 5
        assert db.query(Task).count() == 5

    def test_create_tasks_draft_manifest_rejected(self, db: Session, setup):
        """未审批清单 → 整批拒绝，不创建任务。"""
        env = setup
        env["manifest"].status = "draft"
        db.commit()
        with pytest.raises(ManifestCompileError):
            manifest_compiler.create_tasks_from_manifest(
                db, env["user"].id, env["project"].id, env["manifest"].id,
                env["gen_type"].id, env["version"].id,
                idempotency_key="x", submit=True,
            )
        assert db.query(Task).count() == 0

    def test_validation_failure_rejects_whole_batch(self, db: Session, setup):
        """任一 intent 校验失败 → 整批拒绝。"""
        env = setup
        # 覆盖 prompt 为空导致全部失败
        with pytest.raises(ManifestCompileError, match="校验失败"):
            manifest_compiler.create_tasks_from_manifest(
                db, env["user"].id, env["project"].id, env["manifest"].id,
                env["gen_type"].id, env["version"].id,
                idempotency_key="bad", submit=True,
                overrides={"prompt": ""},
            )
        assert db.query(Task).count() == 0

    def test_task_links_listing(self, db: Session, setup):
        """任务链接列表包含任务状态。"""
        env = setup
        manifest_compiler.create_tasks_from_manifest(
            db, env["user"].id, env["project"].id, env["manifest"].id,
            env["gen_type"].id, env["version"].id,
            idempotency_key="links", submit=True,
        )
        links = manifest_compiler.manifest_task_links(
            db, env["user"].id, env["project"].id, env["manifest"].id,
        )
        assert len(links) == 5
        assert all(link["task_status"] == "PENDING" for link in links)

    def test_refresh_status_success_and_failed(self, db: Session, setup):
        """任务成功/失败后 refresh-status 回写 ManifestItem 状态。"""
        env = setup
        manifest_compiler.create_tasks_from_manifest(
            db, env["user"].id, env["project"].id, env["manifest"].id,
            env["gen_type"].id, env["version"].id,
            idempotency_key="refresh", submit=True,
        )
        tasks = db.query(Task).order_by(Task.id).all()
        tasks[0].status = "SUCCESS"
        tasks[1].status = "FAILED"
        tasks[1].error = "生成失败"
        db.commit()

        result = manifest_compiler.refresh_manifest_status(
            db, env["user"].id, env["project"].id, env["manifest"].id,
        )
        assert result["summary"]["generated"] == 1
        assert result["summary"]["failed"] == 1
        assert result["summary"]["queued"] == 3

        items = {i.id: i for i in db.query(V3ManifestItem).filter(
            V3ManifestItem.manifest_id == env["manifest"].id).all()}
        links = db.query(V3ManifestItemTaskLink).order_by(V3ManifestItemTaskLink.id).all()
        # link[0] → task SUCCESS → item generated
        assert items[links[0].manifest_item_id].status == "generated"
        assert links[0].link_status == "synced"
        # link[1] → task FAILED → item failed
        assert items[links[1].manifest_item_id].status == "failed"
        assert links[1].link_status == "failed"

    def test_multi_output_task_reconcile_via_refresh(self, db: Session, setup):
        """多输出任务：资产级清单项（无 Shot）关联输出 Resource。"""
        from app.models import Resource, TaskResource

        env = setup
        manifest_compiler.create_tasks_from_manifest(
            db, env["user"].id, env["project"].id, env["manifest"].id,
            env["gen_type"].id, env["version"].id,
            idempotency_key="multi", submit=True,
        )
        task = db.query(Task).first()
        task.status = "SUCCESS"
        for index in (1, 2):
            resource = Resource(
                owner_id=env["user"].id, media_type="image", direction="output",
                filename=f"out-{index}.png", mime="image/png", size=index * 100,
                sha256=uuid4().hex * 2, storage_key=f"test/out-{index}.png",
                width=576, height=1024,
            )
            db.add(resource); db.flush()
            db.add(TaskResource(task_id=task.id, resource_id=resource.id, role="output"))
        db.commit()

        result = manifest_compiler.refresh_manifest_status(
            db, env["user"].id, env["project"].id, env["manifest"].id,
        )
        assert result["summary"]["generated"] == 1
        # v3 link 关联到第一个输出资源（资产级无 Shot 不造 Take）
        link = db.query(V3ManifestItemTaskLink).filter(V3ManifestItemTaskLink.task_id == task.id).first()
        outputs = db.query(Resource).join(TaskResource, TaskResource.resource_id == Resource.id).filter(
            TaskResource.task_id == task.id, TaskResource.role == "output"
        ).order_by(TaskResource.id).all()
        assert link.output_resource_id == outputs[0].id
        assert link.link_status == "synced"


class TestPromptFallbackIntact:
    def test_existing_prompt_fallback_function_still_exists(self):
        """无 Manifest 的 V2.1 生产链路保留 _prompt fallback。"""
        from app.short_drama import production_service
        assert callable(production_service._prompt)
        assert callable(production_service.compile_tasks)
        assert callable(production_service.create_tasks)

    def test_source_field_distinct(self, db: Session, setup):
        """V3 编译创建的 Batch source 标记为 short_drama_v3，与现有链路区分。"""
        env = setup
        result = manifest_compiler.create_tasks_from_manifest(
            db, env["user"].id, env["project"].id, env["manifest"].id,
            env["gen_type"].id, env["version"].id,
            idempotency_key="src", submit=True,
        )
        batch = db.get(Batch, result["batch_id"])
        assert batch.source == "short_drama_v3"
        assert batch.generation_type_id == env["gen_type"].id
        assert batch.workflow_version_id == env["version"].id