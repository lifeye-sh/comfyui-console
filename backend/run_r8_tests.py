"""Standalone R8 test runner (VM mount doesn't support sqlite file I/O from conftest)."""
from __future__ import annotations

import sys
sys.path.insert(0, '.')

from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    Batch, GenerationType, ShortDramaProject, Task, User, Workflow, WorkflowVersion,
    V3GenerationManifest, V3LocationViewVersion, V3ManifestItem,
    V3ManifestItemTaskLink, V3PaletteVersion, V3PropAnchorVersion,
    V3CharacterAnchorVersion, V3SpatialPlanVersion, V3StyleBibleVersion,
    Resource, TaskResource,
)
from app.short_drama.v3_director import manifest_compiler
from app.short_drama.v3_director.production_intent_service import (
    ManifestCompileError, build_intents,
)


def make_env(db: Session):
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

    manifest = V3GenerationManifest(project_id=project.id, version=1, status="approved",
        style_bible_id=style.id, notes="")
    db.add(manifest); db.flush()
    for i in range(3):
        db.add(V3ManifestItem(manifest_id=manifest.id, project_id=project.id,
            asset_stable_key="CH-001", asset_type="character_anchor",
            required_view=["front", "side", "back"][i], scenes=[],
            reference_ids=[], prompt=f"角色主角 {['正面','侧面','背面'][i]} 视图",
            negative_constraints="面部变形", aspect_ratio="9:16"))
    db.add(V3ManifestItem(manifest_id=manifest.id, project_id=project.id,
        asset_stable_key="PR-001", asset_type="prop_anchor", required_view="hero", scenes=[],
        reference_ids=[], prompt="道具特写", negative_constraints="变形", aspect_ratio="9:16"))
    db.add(V3ManifestItem(manifest_id=manifest.id, project_id=project.id,
        asset_stable_key="LV-001", asset_type="location_view", required_view="view", scenes=[],
        reference_ids=[], prompt="地点主视图", negative_constraints="透视错误", aspect_ratio="9:16"))
    db.flush()

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
    return {"user": user, "project": project, "manifest": manifest,
            "gen_type": gen_type, "workflow": workflow, "version": version}


def run():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    passed = 0
    with Session(engine) as db:
        env = make_env(db)

        # Test 1: basic mapping
        manifest, intents = build_intents(
            db, env["user"].id, env["project"].id, env["manifest"].id,
            env["gen_type"].id, env["version"].id,
        )
        assert len(intents) == 5
        for intent in intents:
            assert intent.validation_errors == []
            assert intent.params["prompt"]
            assert intent.params["aspect_ratio"] == "9:16"
        print('✅ T1 动态参数映射：prompt/aspect_ratio 注入完整')

        # Test 2: draft rejected
        env["manifest"].status = "draft"; db.commit()
        try:
            build_intents(db, env["user"].id, env["project"].id, env["manifest"].id,
                env["gen_type"].id, env["version"].id)
            assert False
        except ManifestCompileError as e:
            assert "尚未审批" in str(e)
        env["manifest"].status = "approved"; db.commit()
        print('✅ T2 未审批清单拒绝编译')

        # Test 3: media type mismatch
        video_type = GenerationType(code=f"v3_vid_{uuid4().hex[:8]}", name="V3 视频", media_type="video", enabled=True)
        db.add(video_type); db.commit()
        _, intents = build_intents(db, env["user"].id, env["project"].id, env["manifest"].id,
            video_type.id, None)
        assert any(e["code"] == "media_type_mismatch" for i in intents for e in i.validation_errors)
        print('✅ T3 媒体类型不匹配校验')

        # Test 4: required missing
        _, intents = build_intents(db, env["user"].id, env["project"].id, env["manifest"].id,
            env["gen_type"].id, env["version"].id, overrides={"prompt": ""})
        assert any(e["code"] == "required" for i in intents for e in i.validation_errors)
        print('✅ T4 必填参数缺失报错')

        # Test 5: unknown override warns
        _, intents = build_intents(db, env["user"].id, env["project"].id, env["manifest"].id,
            env["gen_type"].id, env["version"].id, overrides={"nope": 1})
        assert any(w["code"] == "unknown_override" for i in intents for w in i.validation_warnings)
        assert all(i.validation_errors == [] for i in intents)
        print('✅ T5 未知覆盖参数产生 warning')

        # Test 6: item_ids filter
        items = db.query(V3ManifestItem).filter(V3ManifestItem.manifest_id == env["manifest"].id).all()
        subset = items[:2]
        _, intents = build_intents(db, env["user"].id, env["project"].id, env["manifest"].id,
            env["gen_type"].id, env["version"].id, item_ids=[i.id for i in subset])
        assert len(intents) == 2
        print('✅ T6 item_ids 过滤编译')

        # Test 7: preview no tasks
        result = manifest_compiler.compile_preview(
            db, env["user"].id, env["project"].id, env["manifest"].id,
            env["gen_type"].id, env["version"].id)
        assert result["total"] == 5 and result["ok_count"] == 5
        assert db.query(Task).count() == 0 and db.query(Batch).count() == 0
        print('✅ T7 编译预览不创建任务')

        # Test 8: create + idempotency
        key = "run-1"
        result = manifest_compiler.create_tasks_from_manifest(
            db, env["user"].id, env["project"].id, env["manifest"].id,
            env["gen_type"].id, env["version"].id, idempotency_key=key, submit=True)
        assert result["created"] == 5 and result["reused"] == 0
        assert all(t.status == "PENDING" for t in db.query(Task).all())
        items = db.query(V3ManifestItem).filter(V3ManifestItem.manifest_id == env["manifest"].id).all()
        assert all(i.status == "queued" for i in items)
        result2 = manifest_compiler.create_tasks_from_manifest(
            db, env["user"].id, env["project"].id, env["manifest"].id,
            env["gen_type"].id, env["version"].id, idempotency_key=key, submit=True)
        assert result2["created"] == 0 and result2["reused"] == 5
        assert db.query(Task).count() == 5
        print('✅ T8 创建任务 + 幂等复用 + ManifestItem 状态回写')

        # Test 9: validation failure rejects whole batch
        before = db.query(Task).count()
        try:
            manifest_compiler.create_tasks_from_manifest(
                db, env["user"].id, env["project"].id, env["manifest"].id,
                env["gen_type"].id, env["version"].id, idempotency_key="bad",
                submit=True, overrides={"prompt": ""})
            assert False
        except ManifestCompileError as e:
            assert "校验失败" in str(e)
        assert db.query(Task).count() == before
        print('✅ T9 校验失败整批拒绝')

        # Test 10: links listing
        links = manifest_compiler.manifest_task_links(
            db, env["user"].id, env["project"].id, env["manifest"].id)
        assert len(links) == 5
        assert all(link["task_status"] == "PENDING" for link in links)
        print('✅ T10 任务链接列表')

        # Test 11: refresh status success/failed
        tasks = db.query(Task).order_by(Task.id).all()
        tasks[0].status = "SUCCESS"
        tasks[1].status = "FAILED"; tasks[1].error = "生成失败"
        db.commit()
        result = manifest_compiler.refresh_manifest_status(
            db, env["user"].id, env["project"].id, env["manifest"].id)
        assert result["summary"] == {"generated": 1, "failed": 1, "queued": 3}
        links = db.query(V3ManifestItemTaskLink).order_by(V3ManifestItemTaskLink.id).all()
        items = {i.id: i for i in db.query(V3ManifestItem).filter(
            V3ManifestItem.manifest_id == env["manifest"].id).all()}
        assert items[links[0].manifest_item_id].status == "generated"
        assert links[0].link_status == "synced"
        assert items[links[1].manifest_item_id].status == "failed"
        assert links[1].link_status == "failed"
        print('✅ T11 任务状态回写 ManifestItem（成功/失败/排队）')

        # Test 12: multi-output asset-level reconcile (output resource association)
        task = tasks[0]
        for index in (1, 2):
            resource = Resource(
                owner_id=env["user"].id, media_type="image", direction="output",
                filename=f"out-{index}.png", mime="image/png", size=index * 100,
                sha256=uuid4().hex * 2, storage_key=f"test/out-{index}.png",
                width=576, height=1024)
            db.add(resource); db.flush()
            db.add(TaskResource(task_id=task.id, resource_id=resource.id, role="output"))
        db.commit()
        # 重置 item 状态再次刷新
        item0 = db.get(V3ManifestItem, links[0].manifest_item_id)
        item0.status = "queued"; db.commit()
        result = manifest_compiler.refresh_manifest_status(
            db, env["user"].id, env["project"].id, env["manifest"].id)
        link = db.query(V3ManifestItemTaskLink).filter(V3ManifestItemTaskLink.task_id == task.id).first()
        assert link.output_resource_id is not None, "资产级清单项应关联输出 Resource"
        assert link.link_status == "synced"
        # 输出素材是任务输出的第一张图
        outputs = db.query(Resource).join(TaskResource, TaskResource.resource_id == Resource.id).filter(
            TaskResource.task_id == task.id, TaskResource.role == "output").order_by(TaskResource.id).all()
        assert link.output_resource_id == outputs[0].id
        print('✅ T12 资产级输出关联 Resource（无 Shot 不造 Take）')

        # Test 13: prompt fallback intact
        from app.short_drama import production_service
        assert callable(production_service._prompt)
        assert callable(production_service.compile_tasks)
        assert callable(production_service.create_tasks)
        print('✅ T13 无 Manifest 的 _prompt fallback 完整保留')

        # Test 14: batch source distinct
        batch = db.get(Batch, result["batch_id"]) if result.get("batch_id") else db.query(Batch).first()
        batch = db.query(Batch).first()
        assert batch.source == "short_drama_v3"
        assert batch.generation_type_id == env["gen_type"].id
        print('✅ T14 V3 Batch source 标记 short_drama_v3')

        passed = 14

    print()
    print(f'All {passed} R8 service-level tests passed!')


if __name__ == '__main__':
    run()
