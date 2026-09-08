"""Director workspace v2: shot refs binding, character image modes, ordered library extras."""
from copy import deepcopy
from uuid import uuid4

from app.db import SessionLocal
from app.models import Character, CharacterVariant, GenerationType, Location, ProjectAssetVersion, Prop, Resource, Scene, ScriptManifestVersion, Shot, Workflow, WorkflowVersion
from app.models.short_drama import ShotCharacterBinding
from app.short_drama import production_service
from tests.test_short_drama_production import _setup, client


def fixture():
    headers, project, shot, gt = _setup()
    with SessionLocal() as db:
        s = db.get(Shot, shot)
        workflow = db.query(Workflow).filter_by(generation_type_id=gt).one()
        version = db.get(WorkflowVersion, workflow.current_version_id)
        params = deepcopy(version.param_schema)
        nodes = deepcopy(version.api_json)
        nodes["3"] = {"class_type": "LoadImage", "inputs": {"image": ""}}
        params.append({"key": "first", "label": "首帧", "type": "image", "node": "3", "path": "inputs.image"})
        version.param_schema, version.api_json = params, nodes
        owner = s.owner_id
        character = Character(owner_id=owner, project_id=project, name="测试角色", primary_resource_id=None)
        db.add(character); db.flush()
        variant = CharacterVariant(owner_id=owner, character_id=character.id, name="雨衣", wardrobe="蓝色雨衣")
        db.add(variant); db.flush()
        location = Location(owner_id=owner, project_id=project, name="车站")
        db.add(location); db.flush()
        prop = Prop(owner_id=owner, project_id=project, name="雨伞")
        db.add(prop); db.flush()
        rids = []
        for i in range(2):
            r = Resource(owner_id=owner, media_type="image", direction="input", filename=f"ref{i}.png", mime="image/png", size=1, sha256=uuid4().hex * 2, storage_key=f"test/r{i}.png")
            db.add(r); db.flush(); rids.append(r.id)
        db.commit()
        ids = {"character": character.id, "variant": variant.id, "location": location.id, "prop": prop.id, "resources": rids}
    root = f"/api/v2/short-drama/projects/{project}/director-workspace"
    # Bind text/number roles only; the image input stays unbound so extras auto-fill applies.
    workflows = client.get(f"{root}/workflows", headers=headers).json()
    video = next(w for w in workflows if w["media_type"] == "video")
    bound = client.put(f"{root}/workflows/{video['workflow_version_id']}/binding", headers=headers, json={"mapping": {"prompt": "prompt", "duration": "duration"}})
    assert bound.status_code == 200, bound.text
    return headers, project, shot, root, ids


def get(h, root, shot):
    response = client.get(f"{root}/shots/{shot}", headers=h)
    assert response.status_code == 200, response.text
    return response.json()


def test_copy_character_location_and_prop_is_atomic_and_detaches_images():
    h, p, _, _, ids = fixture()
    with SessionLocal() as db:
        owner_id = db.get(Character, ids["character"]).owner_id
        for kind in ("character", "location", "prop"):
            db.add(ProjectAssetVersion(owner_id=owner_id, project_id=p, entity_type=kind, entity_id=ids[kind], version=1, prompt=f"{kind} copied prompt", generation_snapshot={"purpose":"prompt_edit"}))
        db.commit()
    for kind in ("character", "location", "prop"):
        response = client.post(f"/api/v2/short-drama/projects/{p}/assets/{kind}/{ids[kind]}/copy", headers=h)
        assert response.status_code == 201, response.text
        copied = response.json()
        assert "副本" in copied["name"] and copied["entity_type"] == kind
        with SessionLocal() as db:
            model = {"character": Character, "location": Location, "prop": Prop}[kind]
            item = db.get(model, copied["entity_id"])
            assert item.status == "draft" and item.reference_resource_ids == []
            assert getattr(item, "resource_id" if kind == "prop" else "primary_resource_id") is None
            version = db.query(ProjectAssetVersion).filter_by(project_id=p, entity_type=kind, entity_id=item.id).one()
            assert version.prompt == f"{kind} copied prompt" and version.resource_id is None


def test_update_refs_binds_characters_location_props_and_validates_ownership():
    h, p, s, root, ids = fixture()
    body = {"character_ids": [ids["character"]], "bindings": {str(ids["character"]): ids["variant"]}, "location_id": ids["location"], "prop_ids": [ids["prop"]]}
    saved = client.put(f"{root}/shots/{s}/refs", headers=h, json=body)
    assert saved.status_code == 200, saved.text
    view = saved.json()
    assert view["character_ids"] == [ids["character"]] and view["location_id"] == ids["location"] and view["prop_ids"] == [ids["prop"]]
    with SessionLocal() as db:
        db.get(Prop, ids["prop"]).resource_id = ids["resources"][1]
        db.commit()
    view = get(h, root, s)
    prop_asset = next(a for a in view["assets"] if a["role"] == "prop_references")
    assert prop_asset["resource_id"] == ids["resources"][1]
    char = next(a for a in view["assets"] if a["role"] == "character_references")
    assert char["variant_id"] == ids["variant"] and "雨衣" in char["name"]
    with SessionLocal() as db:
        binding = db.query(ShotCharacterBinding).filter_by(shot_id=s, character_id=ids["character"]).one()
        assert binding.variant_id == ids["variant"] and binding.inheritance_source == "shot_override"
    # Foreign resources are rejected.
    h2, p2, s2, root2, _ = fixture()
    assert client.put(f"{root}/shots/{s}/refs", headers=h, json={**body, "character_ids": [ids["character"] + 99999]}).status_code == 422
    assert client.put(f"{root}/shots/{s}/refs", headers=h, json={**body, "bindings": {str(ids["character"]): 987654}}).status_code == 422
    assert client.put(f"{root}/shots/{s}/refs", headers=h, json={**body, "prop_ids": [ids["prop"] + 99999]}).status_code == 422
    assert client.put(f"{root}/shots/{s}/refs", headers=h, json={**body, "location_id": ids["location"] + 99999}).status_code == 422
    # Removing a character drops the binding row.
    removed = client.put(f"{root}/shots/{s}/refs", headers=h, json={"character_ids": [], "bindings": {}, "location_id": None, "prop_ids": []})
    assert removed.status_code == 200 and removed.json()["assets"] == []
    with SessionLocal() as db:
        assert db.query(ShotCharacterBinding).filter_by(shot_id=s).count() == 0


def test_bound_variant_without_image_falls_back_to_character_primary_image():
    h, p, s, root, ids = fixture()
    with SessionLocal() as db:
        db.get(Character, ids["character"]).primary_resource_id = ids["resources"][0]
        db.commit()
    saved = client.put(f"{root}/shots/{s}/refs", headers=h, json={
        "character_ids": [ids["character"]],
        "bindings": {str(ids["character"]): ids["variant"]},
        "location_id": None,
        "prop_ids": [],
    })
    assert saved.status_code == 200, saved.text
    asset = next(item for item in saved.json()["assets"] if item["role"] == "character_references")
    assert asset["variant_id"] == ids["variant"]
    assert asset["resource_id"] == ids["resources"][0]

    with SessionLocal() as db:
        db.get(CharacterVariant, ids["variant"]).primary_resource_id = ids["resources"][1]
        db.commit()
    asset = next(item for item in get(h, root, s)["assets"] if item["role"] == "character_references")
    assert asset["resource_id"] == ids["resources"][1]


def test_character_image_mode_prefers_latest_turnaround_with_fallback():
    h, p, s, root, ids = fixture()
    assert client.put(f"{root}/shots/{s}/refs", headers=h, json={"character_ids": [ids["character"]], "bindings": {}, "location_id": None, "prop_ids": []}).status_code == 200
    # Default draft has empty asset choices; image_mode defaults to primary (no image yet).
    view = get(h, root, s)
    assert view["draft"]["asset_choices"]["extras"] == [] and view["draft"]["asset_choices"]["characters"] == []
    assert next(a for a in view["assets"] if a["role"] == "character_references")["resource_id"] is None
    # A newly linked library three-view is usable before it replaces any primary asset.
    rid = ids["resources"][0]
    with SessionLocal() as db:
        db.add(ProjectAssetVersion(owner_id=db.get(Shot, s).owner_id, project_id=p, entity_type="character", entity_id=ids["character"], version=1,
                                   resource_id=rid, status="candidate", is_current=False, generation_snapshot={"purpose": "character_turnaround"}))
        db.commit()
    # Switch image mode to turnaround through the draft save path.
    draft = deepcopy(view["draft"])
    draft["asset_choices"]["characters"] = [{"character_id": ids["character"], "image_mode": "turnaround"}]
    saved = client.put(f"{root}/shots/{s}", headers=h, json={"revision": view["revision"], "draft": draft})
    assert saved.status_code == 200, saved.text
    char = next(a for a in saved.json()["assets"] if a["role"] == "character_references")
    assert char["image_mode"] == "turnaround" and char["resource_id"] == rid
    # Without a confirmed turnaround the mode falls back to the base image.
    with SessionLocal() as db:
        item = db.query(ProjectAssetVersion).filter_by(project_id=p, entity_type="character", entity_id=ids["character"]).one()
        db.delete(item); db.commit()
    fallback = get(h, root, s)
    assert next(a for a in fallback["assets"] if a["role"] == "character_references")["resource_id"] is None


def test_draft_rejects_unknown_extras_and_video_compile_fills_inputs_in_order():
    h, p, s, root, ids = fixture()
    view = get(h, root, s)
    draft = deepcopy(view["draft"])
    draft["asset_choices"]["extras"] = [{"resource_id": 987654, "media_type": "image", "label": "幽灵"}]
    assert client.put(f"{root}/shots/{s}", headers=h, json={"revision": view["revision"], "draft": draft}).status_code == 422
    # Two image extras; only the first is checked (order 1), the unchecked one must not feed inputs.
    draft = deepcopy(view["draft"])
    first, second = ids["resources"]
    draft["asset_choices"]["extras"] = [
        {"resource_id": first, "media_type": "image", "label": "勾选素材", "enabled": True, "order": 1},
        {"resource_id": second, "media_type": "image", "label": "未勾选素材", "enabled": False, "order": 0},
    ]
    saved = client.put(f"{root}/shots/{s}", headers=h, json={"revision": view["revision"], "draft": draft})
    assert saved.status_code == 200, saved.text
    revision = saved.json()["revision"]
    body = {"scope": "video", "mode": "manual", "workflow_version_id": None, "params": {}, "idempotency_key": "extras-order"}
    workflows = client.get(f"{root}/workflows", headers=h).json()
    video = next(w for w in workflows if w["media_type"] == "video")
    body["workflow_version_id"] = video["workflow_version_id"]
    compiled = client.post(f"{root}/shots/{s}/compile", headers=h, json=body)
    assert compiled.status_code == 200, compiled.text
    result = compiled.json()
    assert result["errors"] == [], result
    assert result["params"]["first"] == first  # only the checked extra feeds the input
    assert result["warnings"] == []  # unchecked extras are not counted as unmatched
    view = get(h, root, s)
    # 默认两个帧都启用（order 0 按 index 平局），勾选素材排第 3。
    assert view["extras"] == [
        {"resource_id": first, "media_type": "image", "label": "勾选素材", "enabled": True, "order": 1, "check_order": 3, "filename": "ref0.png"},
        {"resource_id": second, "media_type": "image", "label": "未勾选素材", "enabled": False, "order": 0, "check_order": 0, "filename": "ref1.png"},
    ]
    # Check both with explicit order: fill follows the check order, not list order.
    draft = deepcopy(view["draft"])
    draft["asset_choices"]["extras"] = [
        {"resource_id": second, "media_type": "image", "label": "第二个勾选", "enabled": True, "order": 2},
        {"resource_id": first, "media_type": "image", "label": "第一个勾选", "enabled": True, "order": 1},
    ]
    saved = client.put(f"{root}/shots/{s}", headers=h, json={"revision": view["revision"], "draft": draft})
    assert saved.status_code == 200, saved.text
    compiled = client.post(f"{root}/shots/{s}/compile", headers=h, json=body).json()
    assert compiled["params"]["first"] == first and compiled["warnings"] != []  # second unmatched -> warning
    # Explicit param overrides the automatic order fill.
    overridden = client.post(f"{root}/shots/{s}/compile", headers=h, json={**body, "params": {"first": second}}).json()
    assert overridden["params"]["first"] == second and overridden["errors"] == []
    # Snapshot fingerprint now covers extras; adopting frames marks videos stale when extras change.
    assert "extras" in compiled["source_snapshot"] and compiled["source_snapshot"]["extras"][0]["resource_id"] == first


def test_check_orders_span_frames_extras_and_context_assets():
    """关键帧、库素材、上下文资产共享一个勾选顺序空间。"""
    h, p, s, root, ids = fixture()
    view = get(h, root, s)
    draft = deepcopy(view["draft"])
    first, second = ids["resources"]
    # Frame checked second; extra checked first; location enabled third.
    draft["frames"][0]["enabled"] = True; draft["frames"][0]["order"] = 2
    draft["frames"][1]["enabled"] = False; draft["frames"][1]["order"] = 0
    draft["asset_choices"]["extras"] = [{"resource_id": first, "media_type": "image", "label": "先勾选", "enabled": True, "order": 1}]
    draft["asset_choices"]["location_enabled"] = True; draft["asset_choices"]["location_order"] = 3
    assert client.put(f"{root}/shots/{s}", headers=h, json={"revision": view["revision"], "draft": draft}).status_code == 200
    body = {"scope": "video", "mode": "manual", "workflow_version_id": None, "params": {}, "idempotency_key": "global-order"}
    workflows = client.get(f"{root}/workflows", headers=h).json()
    body["workflow_version_id"] = next(w for w in workflows if w["media_type"] == "video")["workflow_version_id"]
    result = client.post(f"{root}/shots/{s}/compile", headers=h, json=body).json()
    assert result["errors"] == [], result
    orders = result["source_snapshot"]  # snapshot embeds assets/extras; check orders live in shot_view
    assert "extras" in orders
    shot = get(h, root, s)
    assert shot["check_orders"] == {"extra:%d" % first: 1, "frame:start": 2, "location": 3}
    # 尾帧未勾选：即便未采用尾帧资源，也不参与 first/last 自动值之外的活动清单。
    assert "frame:end" not in shot["check_orders"]


def test_video_prompt_composition_and_ratio_autofill():
    """宽屏/竖屏自动映射尺寸；视频提示词按 H3 Ref2VA 六段式规范综合 AI 分析内容。"""
    h, p, s, root, ids = fixture()
    with SessionLocal() as db:
        shot = db.get(Shot, s)
        shot.production_settings = {**(shot.production_settings or {}),
            "manifest_prompt": {"effective": {"base_visual": "女孩在雨夜的站台回头", "visual_style": "冷雨夜霓虹质感", "negative_constraints": "no other people, no facial distortion"}},
            "scene_context": {"atmosphere": "雨夜孤寂"}}
        db.commit()
    project_root = f"/api/v2/short-drama/projects/{p}"
    # 项目 brief 默认 9:16 竖屏。
    workflows = client.get(f"{root}/workflows", headers=h).json()
    video = next(w for w in workflows if w["media_type"] == "video")
    assert client.put(f"{root}/workflows/{video['workflow_version_id']}/binding", headers=h, json={"mapping": {"prompt": "prompt", "duration": "duration"}}).status_code == 200
    prompt = client.post(f"{root}/shots/{s}/video-prompt", headers=h).json()["prompt"]
    # 六段固定顺序、字段名小写。
    section_keys = ["subject_definitions:", "summary:", "retention_analysis:", "detailed_description:", "overall_soundscape:", "non_diegetic_music:"]
    positions = [prompt.index(key) for key in section_keys]
    assert positions == sorted(positions), prompt
    assert "non_diegetic_music: N/A" in prompt
    # AI 分析内容进入 detailed_description 的技能格式；外层 Negative 保持兼容。
    assert "冷雨夜霓虹质感" in prompt and "女孩在雨夜的站台回头" in prompt
    assert "Negative: no other people, no facial distortion" in prompt
    for rule in ("严禁多手多脚肢体穿模", "严禁画面内出现字幕文字", "不得改变服装", "不得改变发型颜色"):
        assert prompt.count(rule) == 1
    detailed = prompt.split("detailed_description:", 1)[1].split("overall_soundscape:", 1)[0]
    assert "【时间轴分镜】：" in detailed and "【接续状态】：" in detailed
    for removed in ("【画幅风格】", "【场景资产】", "【核心人物】", "【负面排除】"):
        assert removed not in detailed
    # 无已采用角色参考图时不虚构 Picture 标签。
    assert "<Picture" not in prompt
    # 对白用 <d> 包裹保留中文（本镜头无对白，检查不误报）。
    shot_view = get(h, root, s)
    # compile：未绑定的 size/aspect_ratio 参数按 brief 自动填充。
    version_id = video["workflow_version_id"]
    with SessionLocal() as db:
        v = db.get(WorkflowVersion, version_id)
        api = deepcopy(v.api_json)
        api["1"]["inputs"]["size"] = ""
        api["1"]["inputs"]["ratio"] = ""
        schema = deepcopy(v.param_schema)
        schema.append({"key": "size", "label": "尺寸", "type": "select", "node": "1", "path": "inputs.size", "options": [{"label": "1080x1920", "value": "1080x1920"}, {"label": "1920x1080", "value": "1920x1080"}]})
        schema.append({"key": "aspect_ratio", "label": "画幅", "type": "select", "node": "1", "path": "inputs.ratio", "options": [{"label": "9:16", "value": "9:16"}, {"label": "16:9", "value": "16:9"}]})
        v.param_schema = schema; v.api_json = api; db.commit()
    body = {"scope": "video", "mode": "manual", "workflow_version_id": version_id, "params": {}, "idempotency_key": "ratio-autofill"}
    result = client.post(f"{root}/shots/{s}/compile", headers=h, json=body).json()
    assert result["errors"] == [], result
    assert result["params"]["size"] == "1080x1920"
    assert result["params"]["aspect_ratio"] == "9:16"
    assert result["params"]["duration"] == 4


def test_video_prompt_labels_subjects_pictures_and_dialogue():
    """有已采用参考图时保留 H3 Subject，并在技能正文中输出带角色的台词。"""
    from app.models import Take
    h, p, s, root, ids = fixture()
    with SessionLocal() as db:
        shot = db.get(Shot, s)
        character = Character(owner_id=shot.owner_id, project_id=p, name="唐糖", primary_resource_id=ids["resources"][0], identity="24岁中国年轻女性，棕色长发")
        db.add(character); db.flush()
        prop = Prop(owner_id=shot.owner_id, project_id=p, name="信纸", resource_id=ids["resources"][1])
        db.add(prop); db.flush()
        shot.character_ids = [character.id]; shot.prop_ids = [prop.id]
        shot.dialogue = "唐糖：你为什么一直不肯告诉我真相？"
        character_id = character.id
        prop_id = prop.id
        db.add(ShotCharacterBinding(owner_id=shot.owner_id, shot_id=s, character_id=character.id))
        db.commit()
        # 勾选角色与道具进入视频制作（统一勾选体系：后端按 asset_choices 判定启用）。
    view = get(h, root, s)
    draft = deepcopy(view["draft"])
    draft["asset_choices"]["prop_orders"] = {str(prop_id): 1}
    assert client.put(f"{root}/shots/{s}", headers=h, json={"revision": view["revision"], "draft": draft}).status_code == 200
    prompt = client.post(f"{root}/shots/{s}/video-prompt", headers=h).json()["prompt"]
    assert "<Subject 1>: 唐糖" in prompt
    assert "完全参照 <Picture 1> 外观" in prompt  # 角色图在 Subject 定义中引用
    assert "<Picture 1>: 已勾选唐糖" not in prompt  # 镜头上下文已在 Subject 中说明，不重复列出
    assert "<Subject" in prompt and "信纸" in prompt  # 道具也是 Subject
    assert "台词：【唐糖：你为什么一直不肯告诉我真相？】" in prompt
    detailed = prompt.split("detailed_description:", 1)[1].split("overall_soundscape:", 1)[0]
    assert "【核心人物】" not in detailed
    assert "【场景资产】" not in detailed
    section_keys = ["subject_definitions:", "summary:", "retention_analysis:", "detailed_description:", "overall_soundscape:", "non_diegetic_music:"]
    positions = [prompt.index(key) for key in section_keys]
    assert positions == sorted(positions)
    assert len(prompt) <= 7000

    # 取消上下文勾选后，角色和道具仍绑定镜头，但不再写入视频提示词资产段。
    view = get(h, root, s)
    draft = deepcopy(view["draft"])
    draft["asset_choices"]["characters"] = [{"character_id": character_id, "image_mode": "primary", "enabled": False, "order": 0}]
    draft["asset_choices"]["prop_orders"] = {}
    assert client.put(f"{root}/shots/{s}", headers=h, json={"revision": view["revision"], "draft": draft}).status_code == 200
    unchecked = client.post(f"{root}/shots/{s}/video-prompt", headers=h).json()["prompt"]
    assert "<Subject 1>: 唐糖" not in unchecked
    assert "【核心人物】" not in unchecked.split("detailed_description:", 1)[1].split("overall_soundscape:", 1)[0]
    assert "信纸" not in unchecked


def test_video_prompt_recovers_manifest_dialogue_and_preserves_action_draft():
    h, p, s, root, ids = fixture()
    with SessionLocal() as db:
        shot = db.get(Shot, s)
        shot.dialogue = ""
        shot.production_settings = {**(shot.production_settings or {}), "dialogue_lines": [
            {"speaker": "甲", "text": "别走！"}, {"speaker": "乙", "text": "为什么？"},
            {"speaker": "甲", "text": "别走！"}], "narration": "夜色降临。"}
        db.commit()
    view = get(h, root, s)
    assert view["dialogue"] == "甲：别走！\n乙：为什么？\n甲：别走！"
    draft = deepcopy(view["draft"])
    draft["video_prompt"] = "保持原有推镜和动作描述"
    assert client.put(f"{root}/shots/{s}", headers=h, json={"revision": view["revision"], "draft": draft}).status_code == 200
    response = client.post(f"{root}/shots/{s}/video-prompt", headers=h)
    assert response.status_code == 200
    prompt = response.json()["prompt"]
    assert prompt.count("甲：别走！") == 2
    assert "台词：【甲：别走！；乙：为什么？；甲：别走！】" in prompt
    assert "台词：【夜色降临。】" not in prompt
    assert get(h, root, s)["draft"]["video_prompt"] == draft["video_prompt"]
    video = next(w for w in client.get(f"{root}/workflows", headers=h).json() if w["media_type"] == "video")
    body = {"scope": "video", "mode": "manual", "workflow_version_id": video["workflow_version_id"], "params": {"prompt": prompt}, "idempotency_key": "dialogue-prompt"}
    compiled = client.post(f"{root}/shots/{s}/compile", headers=h, json=body)
    assert compiled.status_code == 200
    assert compiled.json()["params"]["prompt"] == prompt


def test_explicit_shot_dialogue_overrides_stale_manifest_lines():
    from app.short_drama.director_workspace_service import shot_dialogue
    shot = Shot(dialogue="甲：更新后的台词", production_settings={"dialogue_lines": [{"speaker": "甲", "text": "过时台词"}]})
    assert shot_dialogue(shot) == "甲：更新后的台词"


def test_checked_resources_reach_created_task_and_uploaded_workflow(monkeypatch):
    import asyncio
    from app.models import Task, TaskResource
    from app.queue.dispatcher import Dispatcher
    h,p,s,root,ids=fixture()
    video=next(w for w in client.get(f"{root}/workflows",headers=h).json() if w["media_type"]=="video")
    wid=video["workflow_version_id"]
    with SessionLocal() as db:
        shot=db.get(Shot,s)
        resource_ids=[]
        for index,kind in enumerate(["image"]*5+["audio","video"]):
            ext={"image":"png","audio":"wav","video":"mp4"}[kind]
            r=Resource(owner_id=shot.owner_id,media_type=kind,direction="input",filename=f"checked{index}.{ext}",mime=f"{kind}/{ext}",size=1,sha256=uuid4().hex*2,storage_key=f"test/checked{index}.{ext}")
            db.add(r);db.flush();resource_ids.append(r.id)
        frame,char,location,prop,extra,audio,clip=resource_ids
        shot.first_frame_resource_id=frame
        db.get(Character,ids["character"]).primary_resource_id=char
        db.get(Location,ids["location"]).primary_resource_id=location
        db.get(Prop,ids["prop"]).resource_id=prop
        version=db.get(WorkflowVersion,wid)
        nodes=deepcopy(version.api_json);schema=deepcopy(version.param_schema)
        nodes["3"]["inputs"]["image"]=[]
        schema[-1]["multiple"]=True
        for node,key,kind in [("4","sound","audio"),("5","clip","video")]:
            nodes[node]={"class_type":"LoadMedia","inputs":{"file":""}}
            schema.append({"key":key,"type":kind,"node":node,"path":"inputs.file"})
        version.api_json=nodes;version.param_schema=schema;db.commit()
    assert client.put(f"{root}/shots/{s}/refs",headers=h,json={"character_ids":[ids["character"]],"bindings":{},"location_id":ids["location"],"prop_ids":[ids["prop"]]}).status_code==200
    view=get(h,root,s);draft=deepcopy(view["draft"])
    draft["frames"][0].update(enabled=True,order=2)
    draft["frames"][1]["enabled"]=False
    draft["asset_choices"]={"extras":[{"resource_id":rid,"media_type":kind,"enabled":True,"order":order} for rid,kind,order in [(extra,"image",1),(audio,"audio",6),(clip,"video",7)]],"characters":[{"character_id":ids["character"],"image_mode":"primary","enabled":True,"order":3}],"location_enabled":True,"location_order":4,"prop_orders":{str(ids["prop"]):5}}
    assert client.put(f"{root}/shots/{s}",headers=h,json={"revision":view["revision"],"draft":draft}).status_code==200
    body={"scope":"video","mode":"manual","workflow_version_id":wid,"params":{"first":[],"sound":0},"idempotency_key":"checked-task"}
    compiled=client.post(f"{root}/shots/{s}/compile",headers=h,json=body).json()
    expected=[extra,frame,char,location,prop]
    assert compiled.get("errors")==[],compiled
    assert compiled["params"]["first"]==expected
    assert compiled["params"]["sound"]==audio and compiled["params"]["clip"]==clip
    assert compiled["warnings"]==[]
    created=client.post(f"{root}/shots/{s}/generate",headers=h,json={**body,"expected_fingerprint":compiled["fingerprint"]})
    assert created.status_code==201,created.text
    class Storage:
        def read(self,key): return b"test media"
    class Comfy:
        async def upload_image(self,data,name): return {"name":name,"subfolder":"inputs"}
    monkeypatch.setattr("app.queue.dispatcher.get_storage",lambda:Storage())
    with SessionLocal() as db:
        task=db.get(Task,created.json()["task_id"]);version=db.get(WorkflowVersion,wid)
        assert task.params["first"]==expected
        assert task.params["sound"]==audio and task.params["clip"]==clip
        prompt=asyncio.run(Dispatcher()._upload_inputs(db,Comfy(),deepcopy(version.api_json),version.param_schema,task))
        assert prompt["3"]["inputs"]["image"]==[f"inputs/checked{i}.png" for i in [4,0,1,2,3]]
        assert prompt["4"]["inputs"]["file"]=="inputs/checked5.wav"
        assert prompt["5"]["inputs"]["file"]=="inputs/checked6.mp4"
        assert {r.resource_id for r in db.query(TaskResource).filter_by(task_id=task.id)}==set(resource_ids)


def test_explicit_input_reserves_resource_before_automatic_inputs():
    h,p,s,root,ids=fixture()
    video=next(w for w in client.get(f"{root}/workflows",headers=h).json() if w["media_type"]=="video")
    wid=video["workflow_version_id"]
    with SessionLocal() as db:
        version=db.get(WorkflowVersion,wid)
        nodes=deepcopy(version.api_json);nodes["4"]={"class_type":"LoadImage","inputs":{"image":""}}
        version.api_json=nodes;version.param_schema=[*version.param_schema,{"key":"other_image","type":"image","node":"4","path":"inputs.image"}];db.commit()
    view=get(h,root,s);draft=deepcopy(view["draft"])
    draft["asset_choices"]["extras"]=[{"resource_id":rid,"media_type":"image","enabled":True,"order":i+1} for i,rid in enumerate(ids["resources"])]
    assert client.put(f"{root}/shots/{s}",headers=h,json={"revision":view["revision"],"draft":draft}).status_code==200
    body={"scope":"video","mode":"manual","workflow_version_id":wid,"params":{"other_image":ids["resources"][0]},"idempotency_key":"reserve-input"}
    compiled=client.post(f"{root}/shots/{s}/compile",headers=h,json=body).json()
    assert compiled.get("errors")==[],compiled
    assert compiled["params"]["first"]==ids["resources"][1]
    assert compiled["warnings"]==[]


def test_empty_bound_media_input_uses_checked_library_resource():
    h,p,s,root,ids=fixture()
    video=next(w for w in client.get(f"{root}/workflows",headers=h).json() if w["media_type"]=="video")
    wid=video["workflow_version_id"]
    assert client.put(f"{root}/workflows/{wid}/binding",headers=h,json={"mapping":{"prompt":"prompt","duration":"duration","first":"first_frame"}}).status_code==200
    view=get(h,root,s);draft=deepcopy(view["draft"])
    draft["asset_choices"]["extras"]=[{"resource_id":ids["resources"][0],"media_type":"image","enabled":True,"order":1}]
    assert client.put(f"{root}/shots/{s}",headers=h,json={"revision":view["revision"],"draft":draft}).status_code==200
    body={"scope":"video","mode":"first","workflow_version_id":wid,"params":{"first":None},"idempotency_key":"bound-auto"}
    response=client.post(f"{root}/shots/{s}/compile",headers=h,json=body)
    assert response.status_code==200,response.text
    compiled=response.json()
    assert compiled.get("errors")==[],compiled
    assert compiled["params"]["first"]==ids["resources"][0]
    view=get(h,root,s);draft=deepcopy(view["draft"]);draft["asset_choices"]["extras"][0]["enabled"]=False
    assert client.put(f"{root}/shots/{s}",headers=h,json={"revision":view["revision"],"draft":draft}).status_code==200
    compiled=client.post(f"{root}/shots/{s}/compile",headers=h,json=body).json()
    assert any("缺少视频输入" in e for e in compiled["errors"])
    assert compiled["input_resource_ids"]==[]


def test_prompt_sources_roundtrip_edit_clear_and_task_compilation():
    h,p,s,root,ids=fixture()
    with SessionLocal() as db:
        shot=db.get(Shot,s);shot.duration=18
        shot.production_settings={**(shot.production_settings or {}),"title":"完整镜头标题：雨夜站台的最后一次回望","reaction_pause":2,"timing_schema_version":1}
        db.commit()
    view=get(h,root,s)
    assert view["title"]=="完整镜头标题：雨夜站台的最后一次回望"
    assert view["duration"]==20
    draft=deepcopy(view["draft"])
    edits={"visual_description":"编辑后的画面","action":"攥紧车票","expression":"嘴角微颤","dialogue":"甲：请等我。","shot_size":"特写","camera_angle":"俯视","camera_movement":"缓慢拉远","composition":"人物在左侧","transition":"切黑","visual_style":"黑白胶片","atmosphere":"窗外雷雨","negative_constraints":"no watermark"}
    draft["prompt_inputs"].update(edits)
    saved=client.put(f"{root}/shots/{s}",headers=h,json={"revision":view["revision"],"draft":draft})
    assert saved.status_code==200,saved.text
    assert get(h,root,s)["draft"]["prompt_inputs"]=={**edits,"timeline_storyboard":"","continuity":""}
    prompt=client.post(f"{root}/shots/{s}/video-prompt",headers=h).json()["prompt"]
    for value in edits.values(): assert value in prompt
    assert "20.0 秒" in prompt and "00:00-00:20" in prompt
    latest=get(h,root,s)
    generated_draft=deepcopy(latest["draft"])
    generated_draft["video_prompt"]=prompt
    assert client.put(f"{root}/shots/{s}",headers=h,json={"revision":latest["revision"],"draft":generated_draft}).status_code==200
    wid=next(w for w in client.get(f"{root}/workflows",headers=h).json() if w["media_type"]=="video")["workflow_version_id"]
    compiled=client.post(f"{root}/shots/{s}/compile",headers=h,json={"scope":"video","mode":"manual","workflow_version_id":wid,"params":{},"idempotency_key":"source-edit"}).json()
    assert compiled["params"]["duration"]==20
    assert "编辑后的画面" in compiled["params"]["prompt"]
    assert compiled["source_snapshot"]["video_settings"]["prompt_inputs"]["dialogue"]==edits["dialogue"]
    view=get(h,root,s);draft=view["draft"];draft["prompt_inputs"]["dialogue"]=""
    assert client.put(f"{root}/shots/{s}",headers=h,json={"revision":view["revision"],"draft":draft}).status_code==200
    assert "<d>" not in client.post(f"{root}/shots/{s}/video-prompt",headers=h).json()["prompt"]


def test_standard_duration_and_size_match_actual_workflow_options():
    from app.models import ShortDramaProject
    h,p,s,root,ids=fixture()

    wid=next(w for w in client.get(f"{root}/workflows",headers=h).json() if w["media_type"]=="video")["workflow_version_id"]
    # Standard parameter identifiers do not require manually bound roles.
    assert client.put(f"{root}/workflows/{wid}/binding",headers=h,json={"mapping":{}}).status_code==200
    for ratio,options,expected in [("16:9",["9:16","16:9"],"16:9"),("16:9",["9:16 (Portrait Widescreen)","16:9 (Widescreen)"],"16:9 (Widescreen)"),("9:16",["9:16 (Portrait Widescreen)","16:9 (Widescreen)"],"9:16 (Portrait Widescreen)"),("9:16",["16:9","9:16"],"9:16")]:
        with SessionLocal() as db:
            db.get(ShortDramaProject,p).brief.aspect_ratio=ratio
            version=db.get(WorkflowVersion,wid)
            nodes=deepcopy(version.api_json);nodes["6"]={"class_type":"Size","inputs":{"size":""}}
            version.api_json=nodes
            version.param_schema=[x for x in version.param_schema if x["key"]!="size"]+[{"key":"size","type":"select","node":"6","path":"inputs.size","options":[{"label":v,"value":v} for v in options]}]
            db.commit()
        response=client.post(f"{root}/shots/{s}/compile",headers=h,json={"scope":"video","mode":"manual","workflow_version_id":wid,"params":{},"idempotency_key":"size-standard"})
        assert response.status_code==200,response.text
        result=response.json()
        assert result["errors"]==[],result
        assert result["params"]["size"]==expected
        assert result["params"]["duration"]==get(h,root,s)["duration"]
        assert result["params"]["prompt"]


def test_director_recovers_dialogue_from_confirmed_manifest_for_legacy_rows():
    h,p,s,root,ids=fixture()
    with SessionLocal() as db:
        shot=db.get(Shot,s);scene=db.get(Scene,shot.scene_id)
        shot.dialogue="";shot.production_settings={**(shot.production_settings or {}),"dialogue_lines":[]}
        content={"scenes":[]}
        for index in range(scene.sort_order+1): content["scenes"].append({"shots":[]})
        content["scenes"][scene.sort_order]["shots"]=[{} for _ in range(shot.sort_order+1)]
        content["scenes"][scene.sort_order]["shots"][shot.sort_order]={"dialogue_lines":[{"speaker":"甲","text":"清单中的对白。"},{"speaker":"乙","text":"已经带入镜头。"}]}
        version=(db.query(ScriptManifestVersion).filter_by(episode_id=scene.episode_id).count()+1)
        db.add(ScriptManifestVersion(owner_id=shot.owner_id,project_id=p,episode_id=scene.episode_id,version=version,status="confirmed",source_script_revision=1,content=content))
        db.commit()
    view=get(h,root,s)
    expected="甲：清单中的对白。\n乙：已经带入镜头。"
    assert view["dialogue"]==expected
    assert view["draft"]["prompt_inputs"]["dialogue"]==expected
    prompt=client.post(f"{root}/shots/{s}/video-prompt",headers=h).json()["prompt"]
    assert "【时间轴分镜】：" in prompt
    assert "甲：清单中的对白。" in prompt and "乙：已经带入镜头。" in prompt


def test_video_prompt_groups_dense_beats_and_preserves_imported_timestamps():
    h,p,s,root,ids=fixture()
    with SessionLocal() as db:
        shot=db.get(Shot,s)
        shot.duration=8
        shot.dialogue='甲：“快走。”'
        shot.timeline_storyboard="1. 动作一；2. 动作二；3. 动作三；4. 动作四；5. 动作五；6. 动作六。"
        db.commit()
    prompt=client.post(f"{root}/shots/{s}/video-prompt",headers=h).json()["prompt"]
    timeline=prompt.split("【时间轴分镜】：",1)[1].split("【接续状态】：",1)[0]
    assert timeline.count("[镜头") == 2
    assert "00:00-00:04" in timeline and "00:04-00:08" in timeline
    assert "台词：【甲：快走。】" in timeline
    with SessionLocal() as db:
        shot=db.get(Shot,s)
        shot.timeline_storyboard="00:00-00:03 [镜头1] 原始内容。\n00:03-00:08 [镜头2] 原始结尾。"
        db.commit()
    prompt=client.post(f"{root}/shots/{s}/video-prompt",headers=h).json()["prompt"]
    assert "00:00-00:03 [镜头1] 原始内容。" in prompt
    assert "00:03-00:08 [镜头2] 原始结尾。" in prompt


def test_explicit_empty_director_dialogue_override_is_preserved_with_manifest_fallback():
    h,p,s,root,ids=fixture()
    with SessionLocal() as db:
        shot=db.get(Shot,s);scene=db.get(Scene,shot.scene_id)
        content={"scenes":[{"shots":[{"dialogue_lines":[{"speaker":"甲","text":"原对白"}]}]}]}
        db.add(ScriptManifestVersion(owner_id=shot.owner_id,project_id=p,episode_id=scene.episode_id,version=1,status="confirmed",source_script_revision=1,content=content))
        db.commit()
    view=get(h,root,s);draft=deepcopy(view["draft"]);draft["prompt_inputs"]["dialogue"]="";draft["prompt_input_overrides"]=["dialogue"]
    saved=client.put(f"{root}/shots/{s}",headers=h,json={"revision":view["revision"],"draft":draft})
    assert saved.status_code==200,saved.text
    assert get(h,root,s)["draft"]["prompt_inputs"]["dialogue"]==""
    assert "<d>" not in client.post(f"{root}/shots/{s}/video-prompt",headers=h).json()["prompt"]


def test_unmarked_legacy_empty_dialogue_does_not_hide_confirmed_manifest():
    h,p,s,root,ids=fixture()
    initial=get(h,root,s)
    with SessionLocal() as db:
        shot=db.get(Shot,s);scene=db.get(Scene,shot.scene_id)
        content={"scenes":[{"shots":[]} for _ in range(scene.sort_order+1)]}
        content["scenes"][scene.sort_order]["shots"]=[{} for _ in range(shot.sort_order+1)]
        content["scenes"][scene.sort_order]["shots"][shot.sort_order]={"dialogue_lines":[{"speaker":"甲","text":"恢复旧空值"}]}
        db.add(ScriptManifestVersion(owner_id=shot.owner_id,project_id=p,episode_id=scene.episode_id,version=1,status="confirmed",source_script_revision=1,content=content))
        workspace=deepcopy(initial["draft"])
        workspace["prompt_inputs"]["dialogue"]="";workspace.pop("prompt_input_overrides",None)
        shot.production_settings={**(shot.production_settings or {}),"director_workspace":workspace};db.commit()
    view=get(h,root,s)
    assert view["dialogue"]=="甲：恢复旧空值"
    assert view["draft"]["prompt_inputs"]["dialogue"]=="甲：恢复旧空值"

def test_ai_video_prompt_describes_checked_frames_and_library_images_only():
    h,p,s,root,ids=fixture()
    frame_rid,end_rid=ids["resources"]
    view=get(h,root,s);draft=deepcopy(view["draft"])
    draft["frames"][0]["enabled"]=True;draft["frames"][0]["order"]=1
    draft["frames"][0]["prompt"]="雨夜站台，女孩回头"
    draft["frames"][1]["enabled"]=True;draft["frames"][1]["order"]=2
    draft["frames"][1]["prompt"]="列车远去，女孩停在站台边"
    draft["asset_choices"]["extras"]=[]
    saved=client.put(f"{root}/shots/{s}",headers=h,json={"revision":view["revision"],"draft":draft})
    assert saved.status_code==200,saved.text
    imported=client.post(f"{root}/shots/{s}/frames/import",headers=h,json={"scope":"start","resource_id":frame_rid})
    assert imported.status_code==201,imported.text
    take=next(t for t in imported.json()["takes"] if t["scope"]=="start" and t["resource_id"]==frame_rid)
    assert client.post(f"{root}/takes/{take['id']}/adopt",headers=h).status_code==200
    imported_end=client.post(f"{root}/shots/{s}/frames/import",headers=h,json={"scope":"end","resource_id":end_rid})
    assert imported_end.status_code==201,imported_end.text
    end_take=next(t for t in imported_end.json()["takes"] if t["scope"]=="end" and t["resource_id"]==end_rid)
    assert client.post(f"{root}/takes/{end_take['id']}/adopt",headers=h).status_code==200
    prompt=client.post(f"{root}/shots/{s}/video-prompt",headers=h).json()["prompt"]
    assert "<Picture 1>: 已勾选首帧（0.0秒）" in prompt
    assert "<Picture 2>: 已勾选尾帧（4.0秒）" in prompt
    detailed=prompt.split("detailed_description:",1)[1].split("overall_soundscape:",1)[0]
    assert "画面开始于首帧[雨夜站台，女孩回头]<Picture 1>，" in detailed
    assert "画面结束于尾帧[列车远去，女孩停在站台边]<Picture 2>，" in detailed
    assert detailed.index("画面开始于首帧") < detailed.index("画面结束于尾帧")
    for removed in ("【画幅风格】", "【场景资产】", "【核心人物】", "【负面排除】"):
        assert removed not in detailed
