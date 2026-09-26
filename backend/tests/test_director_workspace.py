"""Executable director loop; isolated migrated SQLite and fake Comfy transport."""
from copy import deepcopy
import asyncio
from uuid import uuid4
import pytest
from app.db import SessionLocal
from app.models import Batch, Resource, Scene, Shot, Task, TaskResource, Take, Workflow, WorkflowVersion
from app.queue.dispatcher import Dispatcher
from app.short_drama import production_service
from tests.test_short_drama_production import _setup, client


def fixture():
    headers, project, shot, gt = _setup()
    with SessionLocal() as db:
        s = db.get(Shot, shot)
        s.dialogue = '你为什么一直不肯告诉我真相？'
        workflow = db.query(Workflow).filter_by(generation_type_id=gt).one()
        version = db.get(WorkflowVersion, workflow.current_version_id)
        params = deepcopy(version.param_schema)
        nodes = deepcopy(version.api_json)
        for key, node in [('first', '3'), ('last', '4')]:
            nodes[node] = {'class_type': 'LoadImage', 'inputs': {'image': ''}}
            params.append({'key': key, 'type': 'image', 'node': node, 'path': 'inputs.image'})
        version.param_schema, version.api_json = params, nodes
        owner, version_id = s.owner_id, version.id
        ids = []
        for i in range(3):
            r = Resource(owner_id=owner,media_type='image',direction='input',filename=f'{i}.png',mime='image/png',size=1,sha256=uuid4().hex*2,storage_key=f'test/{i}.png')
            db.add(r); db.flush(); ids.append(r.id)
        db.commit()
    root = f'/api/v2/short-drama/projects/{project}/director-workspace'
    response = client.put(f'{root}/workflows/{version_id}/binding',headers=headers,json={'mapping':{'prompt':'prompt','duration':'duration','first':'first_frame','last':'last_frame'}})
    assert response.status_code == 200, response.text
    return headers, project, shot, version_id, ids, root


def get(headers, root, shot):
    response=client.get(f'{root}/shots/{shot}',headers=headers)
    assert response.status_code == 200,response.text
    return response.json()


def test_director_can_create_free_shots_without_manifest_or_existing_scene_selection():
    headers, project, existing_shot, _, _, root = fixture()
    with SessionLocal() as db:
        episode_id = db.get(Scene, db.get(Shot, existing_shot).scene_id).episode_id
    payload={"title":"自由广告镜头","visual_description":"玻璃瓶在黑色台面缓慢旋转","duration":6.5,
             "shot_size":"特写","camera_movement":"环绕运镜"}
    first=client.post(f"{root}/episodes/{episode_id}/shots",headers=headers,json=payload)
    second=client.post(f"{root}/episodes/{episode_id}/shots",headers=headers,json={**payload,"title":"第二个自由镜头"})
    assert first.status_code==201,first.text
    assert second.status_code==201,second.text
    assert first.json()["scene"]=="自由制作"
    assert first.json()["title"]=="自由广告镜头"
    assert first.json()["description"]==payload["visual_description"]
    assert first.json()["duration"]==6.5
    assert first.json()["character_ids"]==[] and first.json()["assets"]==[]
    assert {frame["id"] for frame in first.json()["draft"]["frames"]}=={"start","end"}
    assert all(frame["enabled"] is False and frame["order"] == 0 for frame in first.json()["draft"]["frames"])
    batch_payload={"shots":[
        {**payload,"title":"批量镜头 A","duration":2.5},
        {**payload,"title":"批量镜头 B","duration":3.0},
        {**payload,"title":"批量镜头 C","duration":3.5},
    ]}
    batch=client.post(f"{root}/episodes/{episode_id}/shots/batch",headers=headers,json=batch_payload)
    assert batch.status_code==201,batch.text
    assert [shot["title"] for shot in batch.json()]==["批量镜头 A","批量镜头 B","批量镜头 C"]
    assert [shot["shot_no"] for shot in batch.json()]==[3,4,5]
    assert len({shot["scene_id"] for shot in batch.json()})==1
    with SessionLocal() as db:
        free_scenes=db.query(Scene).filter_by(episode_id=episode_id,scene_no="DIRECTOR_FREE").all()
        assert len(free_scenes)==1
        assert db.query(Shot).filter_by(scene_id=free_scenes[0].id).count()==5
        created=db.get(Shot,first.json()["id"])
        assert created.source_story_version_id is None
        assert created.production_settings["director_free"] is True


def test_director_overview_can_edit_shot_details_with_revision_guard():
    headers, project, shot_id, _, _, root = fixture()
    original = get(headers, root, shot_id)
    payload = {
        "revision": original["revision"], "title": "雨夜重逢", "visual_description": "女孩在雨幕中回头",
        "action": "先停步，再缓慢回头", "dialogue": "女孩：你终于来了。", "duration": 7.5,
        "shot_size": "近景", "camera_movement": "缓慢推镜",
    }
    saved = client.put(f"{root}/shots/{shot_id}/details", headers=headers, json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["title"] == "雨夜重逢"
    assert saved.json()["description"] == "女孩在雨幕中回头"
    assert saved.json()["dialogue"] == "女孩：你终于来了。"
    assert saved.json()["duration"] == 7.5 and saved.json()["shot_size"] == "近景"
    assert saved.json()["camera"] == "缓慢推镜"
    assert client.put(f"{root}/shots/{shot_id}/details", headers=headers, json=payload).status_code == 409


def imported(headers,root,shot,scope,rid):
    response=client.post(f'{root}/shots/{shot}/frames/import',headers=headers,json={'scope':scope,'resource_id':rid})
    assert response.status_code == 201,response.text
    return next(t for t in response.json()['takes'] if t['scope']==scope and t['resource_id']==rid)


def test_draft_conflict_and_independent_frame_video_adoption():
    h,p,s,w,ids,root=fixture()
    original=get(h,root,s)
    draft=deepcopy(original['draft']);draft['frames'][1]['prompt']='女孩转身面对车站'
    saved=client.put(f'{root}/shots/{s}',headers=h,json={'revision':original['revision'],'draft':draft})
    assert saved.status_code==200,saved.text
    assert client.put(f'{root}/shots/{s}',headers=h,json={'revision':original['revision'],'draft':draft}).status_code==409
    for scope,rid in zip(['start','end'],ids):
        take=imported(h,root,s,scope,rid)
        assert take['is_selected'] is False
        for _ in range(2):
            assert client.post(f"{root}/takes/{take['id']}/adopt",headers=h).status_code==200
    view=get(h,root,s)
    assert view['selected_frames']=={'start':ids[0],'end':ids[1]}
    assert view['dialogue']==original['dialogue']
    assert len([t for t in view['takes'] if t['is_selected']])==2
    assert get(h,root,s)['draft']==draft


def test_preflight_idempotent_queue_output_sync_and_stale_dependencies():
    h,p,s,w,ids,root=fixture()
    body={'scope':'video','mode':'first_last','workflow_version_id':w,'params':{},'idempotency_key':'director-test-request'}
    response=client.post(f'{root}/shots/{s}/compile',headers=h,json=body)
    assert response.status_code==200,response.text
    assert len(response.json()['errors'])==2
    for scope,rid in zip(['start','end'],ids):
        take=imported(h,root,s,scope,rid)
        assert client.post(f"{root}/takes/{take['id']}/adopt",headers=h).status_code==200
    view=get(h,root,s)
    draft=deepcopy(view['draft'])
    for order,frame in enumerate(draft['frames'],start=1):
        frame['enabled']=True;frame['order']=order
    saved=client.put(f'{root}/shots/{s}',headers=h,json={'revision':view['revision'],'draft':draft})
    assert saved.status_code==200,saved.text
    compiled=client.post(f'{root}/shots/{s}/compile',headers=h,json=body).json()
    assert compiled['errors']==[],compiled
    assert compiled['params']['first']==ids[0] and compiled['params']['last']==ids[1]
    assert compiled['params']['duration']==4
    body['expected_fingerprint']=compiled['fingerprint']
    made=client.post(f'{root}/shots/{s}/generate',headers=h,json=body)
    assert made.status_code==201,made.text
    task_id=made.json()['task_id']
    task_view=next(item for item in get(h,root,s)['tasks'] if item['id']==task_id)
    assert task_view['workflow_version_id']==w and task_view['generation_service']=='comfyui'
    assert task_view['mode']=='first_last' and task_view['params']['first']==ids[0] and task_view['params']['last']==ids[1]
    assert '__director' not in task_view['params']
    assert client.post(f'{root}/shots/{s}/generate',headers=h,json=body).json()=={'task_id':task_id,'existing':True}
    assert client.post(f'{root}/shots/{s}/generate',headers=h,json={**body,'params':{'duration':3}}).status_code==409
    with SessionLocal() as db:
        task=db.get(Task,task_id);task.status='SUCCESS'
        for i in range(2):
            r=Resource(owner_id=task.user_id,media_type='video',direction='output',filename=f'v{i}.mp4',mime='video/mp4',size=1,sha256=uuid4().hex*2,storage_key=f'test/v{i}.mp4')
            db.add(r);db.flush();db.add(TaskResource(task_id=task_id,resource_id=r.id,role='output'))
        db.commit()
        production_service.reconcile_task_outputs(db,task_id)
        production_service.reconcile_task_outputs(db,task_id)
    view=get(h,root,s); videos=[t for t in view['takes'] if t['scope']=='video']
    assert len(videos)==2 and not any(t['is_selected'] or t['stale'] for t in videos)
    assert client.post(f"{root}/takes/{videos[0]['id']}/adopt",headers=h).status_code==200
    replacement=imported(h,root,s,'start',ids[2])
    assert client.post(f"{root}/takes/{replacement['id']}/adopt",headers=h).status_code==200
    view=get(h,root,s)
    assert len([t for t in view['takes'] if t['is_selected']])==3
    assert all(t['stale'] for t in view['takes'] if t['scope']=='video')
    assert client.post(f'{root}/shots/{s}/generate',headers=h,json={**body,'idempotency_key':'changed-dependency'}).status_code==409


def test_workflow_binding_and_resource_access_checks():
    h,p,s,w,ids,root=fixture()
    assert client.put(f'{root}/workflows/{w}/binding',headers=h,json={'mapping':{'prompt':'first_frame'}}).status_code==422
    h2,p2,s2,w2,ids2,root2=fixture()
    assert client.get(f'{root}/shots/{s}',headers=h2).status_code==404
    assert client.post(f'{root}/shots/{s}/frames/import',headers=h,json={'scope':'start','resource_id':ids2[0]}).status_code==422
    body={'scope':'video','mode':'first_last','workflow_version_id':w,'params':{'first':ids2[0],'last':ids[0]},'idempotency_key':'foreign-resource'}
    result=client.post(f'{root}/shots/{s}/compile',headers=h,json=body)
    assert result.status_code==200,result.text
    assert any('无权访问' in e for e in result.json()['errors'])
    assert client.post(f'{root}/shots/{s}/compile',headers=h,json={**body,'mode':'references'}).status_code==422
    assert client.post(f'{root}/shots/{s}/compile',headers=h,json={**body,'workflow_version_id':w2}).status_code==422


def test_multi_resource_upload_preserves_order_and_rejects_scalar_widget(monkeypatch):
    h,p,s,w,ids,root=fixture()
    with SessionLocal() as db:
        shot=db.get(Shot,s)
        version=db.get(WorkflowVersion,w); workflow=db.get(Workflow,version.workflow_id)
        batch=Batch(user_id=shot.owner_id,name='upload test',generation_type_id=workflow.generation_type_id,workflow_version_id=w)
        db.add(batch);db.flush()
        task=Task(batch_id=batch.id,generation_type_id=workflow.generation_type_id,user_id=shot.owner_id,workflow_version_id=w,params={'refs':list(reversed(ids))},status='PENDING')
        db.add(task);db.commit()
        class Storage:
            def read(self,key): return b'image'
        class Comfy:
            async def upload_image(self,data,name): return {'name':name,'subfolder':'inputs'}
        monkeypatch.setattr('app.queue.dispatcher.get_storage',lambda:Storage())
        spec=[{'key':'refs','type':'image','multiple':True,'node':'1','path':'inputs.images'}]
        prompt={'1':{'class_type':'ListLoader','inputs':{'images':[]}}}
        result=asyncio.run(Dispatcher()._upload_inputs(db,Comfy(),prompt,spec,task))
        assert result['1']['inputs']['images']==['inputs/2.png','inputs/1.png','inputs/0.png']
        assert [r.resource_id for r in db.query(TaskResource).filter_by(task_id=task.id).order_by(TaskResource.id)]==list(reversed(ids))
        with pytest.raises(RuntimeError,match='未声明列表输入'):
            asyncio.run(Dispatcher()._upload_inputs(db,Comfy(),{'1':{'inputs':{'images':''}}},spec,task))

def test_image_generation_variant_reference_and_legacy_unselect_consistency():
    from app.models import Character, CharacterVariant, GenerationType
    from app.models.short_drama import ShotCharacterBinding
    h,p,s,w,ids,root=fixture()
    with SessionLocal() as db:
        shot=db.get(Shot,s)
        character=Character(owner_id=shot.owner_id,project_id=p,name='女孩',primary_resource_id=ids[0])
        db.add(character);db.flush()
        variant=CharacterVariant(owner_id=shot.owner_id,character_id=character.id,name='雨衣造型',wardrobe='蓝色雨衣',primary_resource_id=ids[1])
        db.add(variant);db.flush()
        db.add(ShotCharacterBinding(owner_id=shot.owner_id,shot_id=s,character_id=character.id,variant_id=variant.id))
        shot.character_ids=[character.id]
        gt=GenerationType(code='image_'+uuid4().hex[:10],name='图片',media_type='image',enabled=True);db.add(gt);db.flush()
        workflow=Workflow(owner_id=shot.owner_id,generation_type_id=gt.id,name='静态帧',media_type='image',status='active');db.add(workflow);db.flush()
        version=WorkflowVersion(workflow_id=workflow.id,version=1,api_json={'1':{'class_type':'Text','inputs':{'text':''}},'2':{'class_type':'LoadImage','inputs':{'image':''}}},param_schema=[{'key':'prompt','type':'textarea','node':'1','path':'inputs.text','required':True},{'key':'ref','type':'image','node':'2','path':'inputs.image','required':True}],output_mapping={})
        db.add(version);db.flush();workflow.current_version_id=version.id;gt.default_workflow_id=workflow.id
        version_id=version.id;db.commit()
    assert client.put(f'{root}/workflows/{version_id}/binding',headers=h,json={'mapping':{'prompt':'prompt','ref':'character_references'}}).status_code==200
    body={'scope':'start','workflow_version_id':version_id,'params':{},'idempotency_key':'image-variant-test'}
    compiled=client.post(f'{root}/shots/{s}/compile',headers=h,json=body)
    assert compiled.status_code==200,compiled.text
    assert compiled.json()['errors']==[],compiled.text
    assert compiled.json()['params']['ref']==ids[1]
    assert '雨衣造型' in compiled.json()['params']['prompt']
    response=client.post(f'{root}/shots/{s}/generate',headers=h,json=body)
    assert response.status_code==201,response.text
    task_id=response.json()['task_id']
    with SessionLocal() as db:
        task=db.get(Task,task_id);task.status='SUCCESS';db.add(TaskResource(task_id=task_id,resource_id=ids[2],role='output'));db.commit()
        production_service.reconcile_task_outputs(db,task_id)
    view=get(h,root,s);take=view['takes'][0]
    assert take['scope']=='start' and take['is_selected']  # 关键帧产物自动采用
    assert get(h,root,s)['selected_frames']['start']==take['resource_id']
    assert client.post(f"/api/v2/short-drama/projects/{p}/takes/{take['id']}/unselect",headers=h).status_code==200
    assert get(h,root,s)['selected_frames']=={}


def test_preflight_detects_binding_change_before_submission():
    h,p,s,w,ids,root=fixture()
    body={'scope':'video','mode':'manual','workflow_version_id':w,'params':{},'idempotency_key':'binding-change'}
    before=client.post(f'{root}/shots/{s}/compile',headers=h,json=body).json()
    assert before['errors']==[]
    assert client.put(f'{root}/workflows/{w}/binding',headers=h,json={'mapping':{'prompt':'prompt'}}).status_code==200
    response=client.post(f'{root}/shots/{s}/generate',headers=h,json={**body,'expected_fingerprint':before['fingerprint']})
    assert response.status_code==409,response.text

def gemini_fixture():
    from app.services import image_provider_service
    from app.services.image_provider_service import ImageProviderInput
    h,p,s,w,ids,root=fixture()
    with SessionLocal() as db:
        owner=db.get(Shot,s).owner_id
        provider=image_provider_service.save(db,owner,ImageProviderInput(name='Director Gemini '+uuid4().hex[:8],provider='gemini_web2api',base_url='http://localhost:8083/v1',model='test-image',api_key='test',enabled=True))
        provider_id=provider.id
    body={'scope':'start','generation_service':'gemini_image','provider_config_id':provider_id,'params':{'size':'1024x1024','reference_resource_ids':[]},'idempotency_key':'gemini-director-test'}
    return h,p,s,ids,root,body


def test_gemini_frame_uses_shared_queue_and_registers_candidate_without_adopting(monkeypatch):
    from app.services import image_provider_service
    from tests.test_gemini_image_provider import PNG_1X1
    h,p,s,ids,root,body=gemini_fixture()
    old=imported(h,root,s,'start',ids[0])
    assert client.post(f"{root}/takes/{old['id']}/adopt",headers=h).status_code==200
    preflight=client.post(f'{root}/shots/{s}/compile',headers=h,json=body)
    assert preflight.status_code==200,preflight.text
    assert preflight.json()['errors']==[]
    assert preflight.json()['workflow']['workflow_version_id'] is None
    response=client.post(f'{root}/shots/{s}/generate',headers=h,json={**body,'expected_fingerprint':preflight.json()['fingerprint']})
    assert response.status_code==201,response.text
    task_id=response.json()['task_id']
    assert client.post(f'{root}/shots/{s}/generate',headers=h,json=body).json()=={'task_id':task_id,'existing':True}
    received=[]
    async def generate(config,prompt,references,size):
        received.append((prompt,references,size))
        return image_provider_service.GeneratedImage(PNG_1X1,'image/png')
    async def publish(*args,**kwargs): pass
    monkeypatch.setattr(image_provider_service,'generate',generate)
    dispatcher=Dispatcher();dispatcher._publish=publish
    with SessionLocal() as db:
        task=db.get(Task,task_id)
        assert task.workflow_version_id is None
        assert task.params['__execution_provider']=='gemini_image'
        assert '__asset_context' not in task.params
        asyncio.run(dispatcher._dispatch_gemini_image(db,task))
        db.expire_all();assert db.get(Task,task_id).status=='SUCCESS'
    assert received[0][1:]==([], '1024x1024')
    assert '静态画面' in received[0][0]
    for rule in ("严禁多手多脚肢体穿模", "严禁画面内出现字幕文字", "不得改变服装", "不得改变发型颜色"):
        assert rule in received[0][0]
    view=get(h,root,s)
    assert view['selected_frames']['start']==view['takes'][0]['resource_id']  # 自动采用
    generated=next(t for t in view['takes'] if t['source_task_id']==task_id)
    assert generated['scope']=='start' and generated['is_selected']
    assert view['tasks'][0]['sync_status']=='synced'


@pytest.mark.parametrize('change',[{'scope':'video'},{'provider_config_id':999999},{'params':{'size':'invalid'}},{'params':{'reference_resource_ids':[999999],'size':'1024x1024'}}])
def test_gemini_rejects_video_invalid_provider_size_and_references(change):
    h,p,s,ids,root,body=gemini_fixture()
    response=client.post(f'{root}/shots/{s}/generate',headers=h,json={**body,**change})
    assert response.status_code==422,response.text
    assert get(h,root,s)['tasks']==[]


def test_gemini_sync_failure_does_not_fail_successful_generation(monkeypatch):
    from app.models import ShotTaskLink
    from app.services import image_provider_service
    from tests.test_gemini_image_provider import PNG_1X1
    h,p,s,ids,root,body=gemini_fixture()
    response=client.post(f'{root}/shots/{s}/generate',headers=h,json=body)
    assert response.status_code==201,response.text
    task_id=response.json()['task_id']
    async def generate(*args): return image_provider_service.GeneratedImage(PNG_1X1,'image/png')
    async def publish(*args,**kwargs): pass
    def fail_sync(*args): raise RuntimeError('temporary sync failure')
    monkeypatch.setattr(image_provider_service,'generate',generate)
    original=production_service.reconcile_task_outputs
    monkeypatch.setattr(production_service,'reconcile_task_outputs',fail_sync)
    dispatcher=Dispatcher();dispatcher._publish=publish
    with SessionLocal() as db:
        asyncio.run(dispatcher._dispatch_gemini_image(db,db.get(Task,task_id)))
        db.expire_all();assert db.get(Task,task_id).status=='SUCCESS'
        assert db.query(ShotTaskLink).filter_by(task_id=task_id).one().status=='sync_failed'
        monkeypatch.setattr(production_service,'reconcile_task_outputs',original)
        original(db,task_id)
    assert len(get(h,root,s)['takes'])==1
