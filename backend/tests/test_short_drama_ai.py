"""Real AI-provider and novel-to-screenplay job pipeline tests."""
from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.main import app
from app.models import AIProviderConfig, CreativeJob, Resource, SourceChapter, SourceDocument, SourceParagraph, User
from app.short_drama.ai_service import decrypt_api_key
from app.short_drama.worker import story_worker

client=TestClient(app)


def _login(username:str,password:str)->dict[str,str]:
    response=client.post("/api/v1/auth/login",json={"username":username,"password":password});assert response.status_code==200
    return {"Authorization":f"Bearer {response.json()['access_token']}"}


def _fixture()->tuple[dict[str,str],dict[str,str],int,int,int]:
    init_db();admin=_login("admin","admin123");username=f"ai-{uuid4().hex[:10]}"
    assert client.post("/api/v1/users",headers=admin,json={"username":username,"password":"user12345","role":"user"}).status_code==201
    headers=_login(username,"user12345");project=client.post("/api/v2/short-drama/projects",headers=headers,json={"name":"AI改编测试","source_type":"novel","brief":{"episode_count":1,"episode_duration":60}}).json()
    db=SessionLocal()
    try:
        user=db.query(User).filter(User.username==username).one();resource=Resource(owner_id=user.id,media_type="document",direction="input",filename="novel.txt",mime="text/plain",size=10,storage_key=f"tests/{uuid4().hex}.txt")
        db.add(resource);db.flush();document=SourceDocument(owner_id=user.id,project_id=project["id"],resource_id=resource.id,filename="novel.txt",source_format="txt",title="测试小说",status="ready",total_chapters=1,total_paragraphs=2,total_chars=20)
        db.add(document);db.flush();chapter=SourceChapter(owner_id=user.id,document_id=document.id,number=1,title="相遇",sort_order=1,paragraph_count=2,char_count=20);db.add(chapter);db.flush()
        db.add_all([SourceParagraph(owner_id=user.id,chapter_id=chapter.id,paragraph_index=1,text="林夏在雨夜走进车站。",char_count=10,source_locator="chapter:1/paragraph:1"),SourceParagraph(owner_id=user.id,chapter_id=chapter.id,paragraph_index=2,text="周野：你终于来了。",char_count=10,source_locator="chapter:1/paragraph:2")]);db.commit();return admin,headers,project["id"],document.id,user.id
    finally:db.close()


class FakeResponse:
    def __init__(self,payload:dict):self.payload=payload
    def raise_for_status(self)->None:return None
    def json(self)->dict:return self.payload


def test_encrypted_provider_and_ai_analysis_adaptation_pipeline() -> None:
    admin,headers,project_id,document_id,user_id=_fixture();provider_name=f"Mock-{uuid4().hex[:8]}"
    created=client.post("/api/v2/short-drama/ai/providers",headers=admin,json={"name":provider_name,"base_url":"http://mock.local/v1","model":"mock-model","api_key":"secret-test-key-1234","is_default":True})
    assert created.status_code==201,created.text;provider_id=created.json()["id"];assert "api_key" not in created.json();assert created.json()["api_key_hint"].endswith("1234")
    db=SessionLocal()
    try:
        stored=db.get(AIProviderConfig,provider_id);assert stored.api_key_encrypted!="secret-test-key-1234";assert decrypt_api_key(stored.api_key_encrypted)=="secret-test-key-1234"
    finally:db.close()
    assert client.post("/api/v2/short-drama/ai/providers",headers=headers,json={"name":"forbidden","base_url":"x","model":"x","api_key":"x"}).status_code==403

    analysis_payload={"synopsis":"雨夜重逢","core_conflict":"二人之间的误会","characters":[{"name":"林夏"},{"name":"周野"}],"locations":[{"name":"车站"}],"events":[{"name":"重逢"}],"timeline":[],"hooks":[],"emotional_beats":[],"facts":["二人在车站相遇"],"source_references":[{"chapter_number":1,"paragraph_start":1,"paragraph_end":2}]}
    adaptation_payload={"options":[{"key":"faithful","label":"忠实原作","description":"保留雨夜重逢","metrics":{"episode_count":1,"source_chapters":1,"pace_ratio":1},"episodes":[{"title":"第一集","synopsis":"雨夜重逢","target_duration":60,"scenes":[{"heading":"雨夜车站","location_name":"车站","time_of_day":"夜","interior_exterior":"EXT","content":"林夏走进车站。","elements":[{"type":"action","text":"林夏走进车站。"},{"type":"dialogue","speaker":"周野","text":"你终于来了。"}],"source_references":[{"document_id":document_id,"chapter_number":1,"paragraph_start":1,"paragraph_end":2}],"purpose":"人物重逢","target_duration":60}]}]}]}
    episode_payload={"title":"雨夜重逢","synopsis":"林夏与周野在车站重逢。","core_conflict":"误会尚未解除","emotional_arc":"戒备到动摇","opening_hook":"林夏收到神秘短信","ending_hook":"周野说出秘密","target_duration":60,"scenes":[{"heading":"外景·车站·夜","location_name":"车站","time_of_day":"夜","interior_exterior":"EXT","content":"雨夜重逢。","elements":[{"type":"action","text":"林夏停下脚步。"},{"type":"dialogue","speaker":"周野","text":"你终于来了。"}],"source_references":[{"document_id":document_id,"chapter_number":1,"paragraph_start":1,"paragraph_end":2}],"purpose":"建立冲突","target_duration":60}]}

    def fake_post(_url:str,**kwargs):
        prompt=kwargs["json"]["messages"][-1]["content"]
        content=episode_payload if "结构化剧本候选" in prompt else adaptation_payload if "根对象为 options" in prompt else analysis_payload
        return FakeResponse({"choices":[{"message":{"content":__import__("json").dumps(content,ensure_ascii=False)}}],"usage":{"prompt_tokens":20,"completion_tokens":10,"total_tokens":30}})

    with patch("app.short_drama.ai_service.httpx.post",side_effect=fake_post):
        body={"document_id":document_id,"chapter_start":1,"chapter_end":1,"idempotency_key":"analysis-1"}
        queued=client.post(f"/api/v2/short-drama/projects/{project_id}/ai/analyze",headers=headers,json=body);assert queued.status_code==202,queued.text
        repeated=client.post(f"/api/v2/short-drama/projects/{project_id}/ai/analyze",headers=headers,json=body);assert repeated.json()["id"]==queued.json()["id"]
        db=SessionLocal()
        try:job=db.get(CreativeJob,queued.json()["id"]);job.status="running";db.commit()
        finally:db.close()
        story_worker._process(queued.json()["id"])
        finished=client.get(f"/api/v2/short-drama/jobs/{queued.json()['id']}",headers=headers);assert finished.json()["status"]=="succeeded";assert finished.json()["token_usage"]["total_tokens"]==30
        analyses=client.get(f"/api/v2/short-drama/projects/{project_id}/ai/analyses",headers=headers);assert analyses.status_code==200;analysis=analyses.json()[0];assert analysis["content"]["synopsis"]=="雨夜重逢"
        confirmed=client.post(f"/api/v2/short-drama/projects/{project_id}/ai/analyses/{analysis['id']}/confirm",headers=headers);assert confirmed.status_code==200
        adapt=client.post(f"/api/v2/short-drama/projects/{project_id}/ai/adaptation",headers=headers,json={"analysis_id":analysis["id"],"episode_count":1,"strategies":["faithful"],"idempotency_key":"adapt-1"});assert adapt.status_code==202,adapt.text
        db=SessionLocal()
        try:job=db.get(CreativeJob,adapt.json()["id"]);job.status="running";db.commit()
        finally:db.close()
        story_worker._process(adapt.json()["id"])
        adaptation_candidate=client.get(f"/api/v2/short-drama/projects/{project_id}/adaptation-candidates",headers=headers).json()[0]
        confirmed_adaptation=client.post(f"/api/v2/short-drama/projects/{project_id}/adaptation-candidates/{adaptation_candidate['id']}/confirm",headers=headers,json={"option_key":"faithful","version_name":"AI改编基础版"})
        assert confirmed_adaptation.status_code==200,confirmed_adaptation.text
        episode=client.get(f"/api/v2/short-drama/projects/{project_id}/screenplay",headers=headers).json()["episodes"][0]
        episode_job=client.post(f"/api/v2/short-drama/projects/{project_id}/episodes/{episode['id']}/ai/generate",headers=headers,json={"provider_config_id":provider_id,"instruction":"加强重逢冲突","idempotency_key":"episode-1"})
        assert episode_job.status_code==202,episode_job.text
        db=SessionLocal()
        try:job=db.get(CreativeJob,episode_job.json()["id"]);job.status="running";db.commit()
        finally:db.close()
        story_worker._process(episode_job.json()["id"])
        episode_candidates=client.get(f"/api/v2/short-drama/projects/{project_id}/episodes/{episode['id']}/ai/candidates",headers=headers)
        assert episode_candidates.status_code==200;revision=episode_candidates.json()[0];assert revision["content"]["core_conflict"]=="误会尚未解除"
        before=client.get(f"/api/v2/short-drama/projects/{project_id}/screenplay",headers=headers).json()["episodes"][0]
        assert before["core_conflict"]==""
        applied=client.post(f"/api/v2/short-drama/projects/{project_id}/episodes/{episode['id']}/ai/candidates/{revision['id']}/confirm",headers=headers)
        assert applied.status_code==200,applied.text
        after=client.get(f"/api/v2/short-drama/projects/{project_id}/screenplay",headers=headers).json()["episodes"][0]
        assert after["core_conflict"]=="误会尚未解除";assert after["scenes"][0]["elements"][1]["speaker"]=="周野"
        locked=client.patch(f"/api/v2/short-drama/projects/{project_id}/episodes/{episode['id']}",headers=headers,json={"lock_version":after["lock_version"],"is_locked":True})
        assert locked.status_code==200
        blocked=client.post(f"/api/v2/short-drama/projects/{project_id}/episodes/{episode['id']}/ai/generate",headers=headers,json={"provider_config_id":provider_id,"idempotency_key":"episode-locked"})
        assert blocked.status_code==422
    adapted=client.get(f"/api/v2/short-drama/jobs/{adapt.json()['id']}",headers=headers);assert adapted.json()["status"]=="succeeded"
    candidates=client.get(f"/api/v2/short-drama/projects/{project_id}/adaptation-candidates",headers=headers);assert candidates.json()[0]["options"][0]["label"]=="忠实原作";assert candidates.json()[0]["status"]=="confirmed"
    assert client.get(f"/api/v2/short-drama/projects/{project_id}/ai/analyses",headers=admin).status_code==404
