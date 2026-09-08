"""Regressions for dialogue preservation, timing, frozen inputs and safe editing."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4
import json
import pytest
from app.db import SessionLocal
from app.models import Shot, ShortDramaProject, AIPromptTemplate, CreativeJob
from app.short_drama.dialogue import extract_dialogue_lines, dialogue_metrics, total_duration
from app.short_drama.director_rules import script_diagnostics, validate_schema, AI_RESPONSE_SCHEMAS
from app.short_drama.phase1_service import _normalize_manifest, _analyze_manifest
from app.short_drama.manifest_editing import split_preview
from tests.test_short_drama_phase1 import _headers, client
from tests.test_short_drama_production import _setup


def manifest_content(text):
    return {"story_summary":"test", "characters":[], "locations":[{"name":"room"}], "props":[],
            "scenes":[{"location_name":"room", "shots":[{"content":text,"duration":8,"timing_schema_version":2,
                "reaction_pause":.5,"character_names":[],"prop_names":[]}]}]}


@pytest.mark.parametrize("source", ['甲：你好。', '对白：甲：“你好。”', '@甲\n“你好。”'])
def test_supported_dialogue_syntax(source):
    assert extract_dialogue_lines(source) == [{"speaker":"甲", "text":"你好。"}]
    assert extract_dialogue_lines('画面：夜色\n旁白：风停了。\n镜头备注：保持平视') == []


def test_known_cast_does_not_promote_document_metadata_to_speakers():
    source = "服装6：蓝色长裙\n时间预算：15秒\n镜头10：推近\n空间锚点：门口\n叶岚：别过来。"
    assert extract_dialogue_lines(source, ["叶岚", "顾景辰"]) == [
        {"speaker": "叶岚", "text": "别过来。"}
    ]


def test_metrics_use_sentence_and_reaction_not_whole_turn():
    metrics = dialogue_metrics('你来了。'*10, 15, 0.5)
    assert metrics['characters'] > 24 and metrics['longest_sentence'] == 3
    assert metrics['status'] == 'ok'
    assert dialogue_metrics('我来了', .6, .5)['status'] == 'overtime'
    assert total_duration(3, {'reaction_pause':.5}) == 3.5
    assert total_duration(3, {'reaction_pause':.5,'timing_schema_version':2}) == 3
    assert script_diagnostics('甲：你好')['dialogues'][0]['scores'] is None
    assert script_diagnostics('甲：你好')['gates'][0]['status'] == 'not_evaluated'


def test_canonical_dialogue_empty_cast_and_override():
    content = manifest_content('甲（画外）：不要开门。')
    shot = content['scenes'][0]['shots'][0]
    shot.update(dialogue_lines=[{'speaker':'甲','text':'陈旧内容'}], prompt={
        'original':{'base_visual':'旧画面'},'override':{'base_visual':'手工覆盖'},'effective':{'base_visual':'过期缓存'}})
    content['_analysis_meta'] = {'raw_validation_errors':[{'message':'raw'}]}
    normalized = _normalize_manifest(content, SimpleNamespace(script_text='',script_settings={}))
    result = normalized['scenes'][0]['shots'][0]
    assert result['character_names'] == [] and result['prop_names'] == []
    assert result['dialogue_lines'][0]['text'] == '不要开门。'
    assert result['prompt']['effective']['base_visual'] == '手工覆盖'
    assert normalized['_analysis_meta']['raw_validation_errors'][0]['message'] == 'raw'
    assert validate_schema(manifest_content('空镜'),AI_RESPONSE_SCHEMAS['script_manifest']) == []


@pytest.mark.parametrize('source', [
    '画面：门打开。\n甲：你今天为什么又瞒着我偷偷来到这个没有人的地方，我一定要问清楚。\n动作任务：收起钥匙。',
    '@甲\n“我回来了。你还好吗？”\n画面：关门。',
    '甲：你好。\n动作任务：抬手。\n乙：你终于来了。',
])
def test_split_preserves_raw_text_and_dialogue_without_duplicate_actions(source):
    content = manifest_content(source)
    content['scenes'][0]['shots'][0]['prompt'] = {
        'original': {
            'initial_frame': '门半开，人物位于门内侧',
            'character_consistency': '保持甲的脸型、发型和服装一致',
            'negative_constraints': '禁止多手、穿模和字幕',
        },
        'override': {'initial_frame': '人工锁定：门半开，人物位于门内侧'},
        'effective': {
            'initial_frame': '人工锁定：门半开，人物位于门内侧',
            'character_consistency': '保持甲的脸型、发型和服装一致',
            'negative_constraints': '禁止多手、穿模和字幕',
        },
    }
    old = deepcopy(content)
    result = split_preview(content,0,0,1)
    assert content == old
    assert ''.join(s['content'][len(s['split_source']['inserted_prefix']):len(s['content'])-len(s['split_source']['inserted_suffix'])] for s in result['shots']) == source
    expected = ''.join(x['text'] for x in extract_dialogue_lines(source))
    actual = ''.join(x['text'] for s in result['shots'] for x in extract_dialogue_lines(s['content']))
    assert actual == expected
    assert all(s['keyframe_plan'] == {} for s in result['shots'])
    for shot in result['shots']:
        assert shot['prompt']['original']['character_consistency'] == '保持甲的脸型、发型和服装一致'
        assert shot['prompt']['original']['negative_constraints'] == '禁止多手、穿模和字幕'
        assert shot['prompt']['override']['initial_frame'] == '人工锁定：门半开，人物位于门内侧'
        assert shot['prompt']['effective']['initial_frame'] == '人工锁定：门半开，人物位于门内侧'
    assert sum(s['reaction_pause'] for s in result['shots']) == .5
    assert split_preview(content,0,0,2)['preview_hash'] != result['preview_hash']


def new_project():
    headers = _headers()
    response = client.post('/api/v2/short-drama/projects/quick-create',headers=headers,json={
        'name':'contract','brief':{'visual_style':'水墨','episode_duration':20}})
    assert response.status_code == 201, response.text
    project = response.json()['project']; episode = response.json()['episode_id']
    base = f"/api/v2/short-drama/projects/{project['id']}/episodes/{episode}"
    script = client.get(base+'/script',headers=headers).json()
    response = client.patch(base+'/script',headers=headers,json={
        'lock_version':script['lock_version'],'mode':'storyboard','settings':script['settings'],
        'text':'甲：我回来了。你今天过得怎么样？\n画面：放下包。'})
    assert response.status_code == 200, response.text
    return headers, project, episode, base


def test_split_preview_apply_conflict_and_owner_boundaries():
    headers, project, episode, base = new_project()
    job = client.post(base+'/manifests/generate',headers=headers,json={'idempotency_key':uuid4().hex}).json()
    manifest = client.get(base+'/manifests',headers=headers).json()[0]
    url = base+f"/manifests/{manifest['id']}"
    body = {'lock_version':manifest['lock_version'],'scene_index':0,'shot_index':0}
    preview = client.post(url+'/split-preview',headers=headers,json=body)
    assert preview.status_code == 200, preview.text
    assert client.get(base+'/manifests',headers=headers).json()[0]['lock_version'] == body['lock_version']
    other = _headers()
    assert client.post(url+'/split-preview',headers=other,json=body).status_code == 404
    bad = client.post(url+'/split-apply',headers=headers,json={**body,'preview_hash':'bad'})
    assert bad.status_code == 409
    applied = client.post(url+'/split-apply',headers=headers,json=preview.json())
    assert applied.status_code == 200, applied.text
    assert len(applied.json()['content']['scenes'][0]['shots']) == len(manifest['content']['scenes'][0]['shots'])+1
    assert client.post(url+'/split-apply',headers=headers,json=preview.json()).status_code == 409
    assert client.post(url+'/split-preview',headers=headers,json={**body,'scene_index':-1}).status_code == 422


def test_production_uses_override_and_does_not_double_count_v2_reaction():
    headers, project_id, shot_id, generation_type_id = _setup()
    with SessionLocal() as db:
        shot = db.get(Shot,shot_id)
        shot.duration=4.2
        shot.production_settings={'timing_schema_version':2,'reaction_pause':.8,
            'manifest_prompt':{'original':{'base_visual':'old'},'override':{'base_visual':'OVERRIDE_SENTINEL'},'effective':{'base_visual':'STALE_SENTINEL'}},
            'dialogue_lines':[{'speaker':'甲','text':'不要开门。'}], 'narration':'清晨。',
            'keyframe_plan':{'strategy':'first','first_frame_prompt':'FRAME_SENTINEL'}}
        db.commit()
    url=f'/api/v2/short-drama/projects/{project_id}/production/compile'
    response=client.post(url,headers=headers,json={'shot_ids':[shot_id],'generation_type_id':generation_type_id})
    assert response.status_code==200,response.text
    params=response.json()[0]['params']
    assert params['duration']==5
    assert 'OVERRIDE_SENTINEL' in params['prompt'] and 'STALE_SENTINEL' not in params['prompt']
    assert '不要开门。' in params['prompt'] and 'FRAME_SENTINEL' in params['prompt'] and '清晨。' in params['prompt']
    with SessionLocal() as db:
        shot=db.get(Shot,shot_id); shot.production_settings={**shot.production_settings,'timing_schema_version':1,'reaction_pause':1.3};db.commit()
    assert client.post(url,headers=headers,json={'shot_ids':[shot_id],'generation_type_id':generation_type_id}).json()[0]['params']['duration']==6


def test_snapshot_freezes_project_and_prompt_and_is_used_by_worker(monkeypatch):
    from app.short_drama import ai_service
    headers, project, episode, base = new_project()
    admin=client.post('/api/v1/auth/login',json={'username':'admin','password':'admin123'}).json()
    provider=client.post('/api/v2/short-drama/ai/providers',headers={'Authorization':f"Bearer {admin['access_token']}"},json={
        'name':'snapshot-'+uuid4().hex[:6],'base_url':'http://mock.local/v1','model':'test','api_key':'test'}).json()
    with SessionLocal() as db:
        job=ai_service.create_script_manifest_job(db,project['owner_id'],project['id'],episode,provider_config_id=provider['id'],idempotency_key=uuid4().hex)
        snapshot=deepcopy(job.input_payload['analysis_snapshot'])
        assert snapshot['context']['brief']['visual_style']=='水墨'
        assert snapshot['source_lines'][0]['id']=='L0001'
        template=db.get(AIPromptTemplate,snapshot['template']['id'])
        old_prompt=template.user_prompt
        template.user_prompt='MUTATED_TEMPLATE'
        db.get(ShortDramaProject,project['id']).brief.visual_style='MUTATED_STYLE'
        db.commit()
        def fake_post(*args,**kwargs):
            messages=kwargs['json']['messages']; rendered=messages[1]['content']
            assert 'MUTATED_TEMPLATE' not in rendered and 'MUTATED_STYLE' not in rendered
            assert '水墨' in rendered and 'L0001' in rendered
            return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'choices':[{'message':{'content':json.dumps(manifest_content(snapshot['script']['text']),ensure_ascii=False)}}]})
        monkeypatch.setattr(ai_service.httpx,'post',fake_post)
        try:
            ai_service.process_ai_job(db,job,lambda *args:True)
            assert job.status=='succeeded'
        finally:
            template.user_prompt=old_prompt;db.commit()
    manifests=client.get(base+'/manifests',headers=headers).json()
    assert manifests[0]['content']['analysis_context']['context']['brief']['visual_style']=='水墨'


def test_source_dialogue_mismatch_blocks_confirmation_but_not_draft():
    content=manifest_content('甲：被修改的内容。')
    content['analysis_context']={'source_lines':[{'id':'L0001','text':'甲：原文。'}]}
    normalized=_normalize_manifest(content,SimpleNamespace(script_text='',script_settings={}))
    _,issues=_analyze_manifest(normalized,8)
    assert any(x.get('blocking_stage')=='confirm' and x.get('source')=='source_check' for x in issues)


def test_narrative_inferred_speaker_never_hard_blocks_confirmation():
    content = manifest_content("崔哥：小沐橙来啦？")
    content["characters"] = [{"name": "苏沐橙"}, {"name": "崔哥"}]
    content["analysis_context"] = {
        "source_lines": [{"id": "L0001", "text": "苏沐橙望向喧闹，网管挥手招呼：“小沐橙来啦？”"}]
    }
    normalized = _normalize_manifest(content, SimpleNamespace(script_text="", script_settings={}))
    _, issues = _analyze_manifest(normalized, 8)
    assert not any(issue.get("blocking_stage") == "confirm" for issue in issues)
    assert any(issue.get("path") == "source_dialogue_attribution" for issue in issues)


def test_source_dialogue_allows_resolving_previously_unattributed_turns():
    content = manifest_content("甲：原文。\n乙：补全归属。")
    content["characters"] = [{"name": "甲"}, {"name": "乙"}]
    content["analysis_context"] = {
        "source_lines": [{"id": "L0001", "text": "甲：原文。\n“补全归属。”"}]
    }
    normalized = _normalize_manifest(content, SimpleNamespace(script_text="", script_settings={}))
    _, issues = _analyze_manifest(normalized, 8)
    assert not any(issue.get("blocking_stage") == "confirm" for issue in issues)


def test_complete_character_prompt_does_not_require_legacy_split_fields():
    content = manifest_content("空镜")
    content["characters"] = [{
        "stable_key": "CHR-001",
        "name": "苏沐橙",
        "asset_grade": "A",
        "visual_prompt": "鹅蛋脸少女，弯月眉，圆杏眼，盘发，珍珠耳钉，暖色电影光。",
    }]
    normalized = _normalize_manifest(content, SimpleNamespace(script_text="", script_settings={}))
    _, issues = _analyze_manifest(normalized, 8)
    character_issues = [issue for issue in issues if issue.get("path") == "characters[0]"]
    assert character_issues == []


@pytest.mark.parametrize('source,expected', [
    ('林舟站在一旁，对坐在椅子上的苏青说：“过来。”苏青惊醒，慌忙回应：“什么？”林舟重复：“站到我面前。”', [('林舟','过来。'),('苏青','什么？'),('林舟','站到我面前。')]),
    ('林舟站起身，然后走到苏青身边，用只有两人能听到的声音轻声说：“等一下。”苏青听到他的嗓音，停了下来。', [('林舟','等一下。')]),
    ('苏青穿好外套后说：“好了。”', [('苏青','好了。')]),
    ('“别急。”林舟说。', [('林舟','别急。')]),
    ('**苏青（轻声）**：“我回来了。”', [('苏青','我回来了。')]),
    ('@林舟（画外）\n（压低声音）\n“不要开门。”', [('林舟','不要开门。')]),
    ('苏青说：“第一行\n第二行。”', [('苏青','第一行\n第二行。')]),
    ('“有人吗？”', [('', '有人吗？')]),
    ('音效：“砰！”\n字幕：“三天后”\n林舟心想：“糟了。”', []),
])
def test_prose_dialogue_attribution(source,expected):
    result=extract_dialogue_lines(source,['林舟','苏青'])
    assert [(x['speaker'],x['text']) for x in result] == expected


def test_narrative_split_preserves_quoted_speech_and_source():
    source='林舟说：“我明天就要出发，不能继续等你了。”苏青回答：“我知道了。”'
    content=manifest_content(source);content['characters']=[{'name':'林舟'},{'name':'苏青'}]
    result=split_preview(content,0,0,1)
    reconstructed=''.join(s['content'][len(s['split_source']['inserted_prefix']):len(s['content'])-len(s['split_source']['inserted_suffix'])] for s in result['shots'])
    assert reconstructed==source
    actual=[(x['speaker'],x['text']) for s in result['shots'] for x in extract_dialogue_lines(s['content'],['林舟','苏青'])]
    assert actual==[('林舟','我明天就要出发，不能继续等你了。'),('苏青','我知道了。')]
