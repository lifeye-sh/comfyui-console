from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import Base
from app.models import Batch, Task, Resource, GenerationType, Workflow, WorkflowVersion
from app.api.v2.gallery import Binding, Request, publish, generate
from app.models import ImageProviderConfig


def test_gallery_workflow_pins_inputs_and_retries_once():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    user = SimpleNamespace(id=7)
    with Session(engine) as db:
        gt = GenerationType(code="i2i_gallery_test",name="图库测试",media_type="image",enabled=True)
        db.add(gt); db.flush()
        wf = Workflow(name="参考生图",media_type="image",generation_type_id=gt.id)
        db.add(wf); db.flush()
        v = WorkflowVersion(workflow_id=wf.id,version=1,api_json={},param_schema=[
            {"key":"prompt","type":"textarea"},{"key":"input","type":"image","required":True}])
        ref = Resource(owner_id=7,media_type="image",filename="pose.png",mime="image/png",size=3,storage_key="pose")
        db.add_all([v,ref]);db.flush()
        cfg = publish(Binding(workflow_version_id=v.id,prompt_key="prompt",mapping={"pose":"input"}),user,db)
        req = Request(request_id=uuid4(),revision=cfg["revision"],refs={"pose":[ref.id]},prompt="测试")
        result = generate(req,user,db)
        assert generate(req,user,db) == result
        assert db.query(Batch).count() == db.query(Task).count() == 1
        task = db.get(Task,result["task_id"])
        assert task.status == "PENDING" and task.params["input"] == ref.id and task.workflow_version_id == v.id
        with pytest.raises(HTTPException):
            generate(req.model_copy(update={"request_id":uuid4(),"revision":"old"}),user,db)
        with pytest.raises(HTTPException):
            generate(req.model_copy(update={"request_id":uuid4()}),SimpleNamespace(id=8),db)
        second = WorkflowVersion(workflow_id=wf.id,version=2,api_json={},param_schema=[
            *v.param_schema, {"key":"second","type":"image","required":True}])
        db.add(second); db.flush()
        for mode, role in (("outfit", "costume"), ("pose", "pose")):
            cfg = publish(Binding(workflow_version_id=second.id, prompt_key="prompt",
                                  mapping={"portrait":"input", role:"second"}),user,db,mode)
            duo = Request(mode=mode,request_id=uuid4(),revision=cfg["revision"],prompt="双图",
                          refs={"portrait":[ref.id],role:[ref.id]})
            created = generate(duo,user,db)
            assert db.get(Task,created["task_id"]).params == {"prompt":"双图","input":ref.id,"second":ref.id}
            for refs in ({"portrait":[ref.id]}, {**duo.refs, ("pose" if role=="costume" else "costume"):[ref.id]}):
                with pytest.raises(HTTPException):
                    generate(duo.model_copy(update={"request_id":uuid4(),"refs":refs}),user,db)
        provider = ImageProviderConfig(name="测试提供方",base_url="http://localhost",model="test",api_key_encrypted="")
        mixed = GenerationType(code="mixed",name="混合生图",media_type="image",enabled=True)
        db.add_all([provider,mixed]); db.flush()
        for mode, second_role in (("outfit","costume"),("pose","pose")):
            req = Request(request_id=uuid4(),provider_id=provider.id,mode=mode,prompt="参考生成",
                          refs={"portrait":[ref.id],second_role:[ref.id]},options={"size":"1088x1920"})
            result = generate(req,user,db)
            task = db.get(Task,result["task_id"])
            assert task.status=="PENDING" and task.generation_type_id==mixed.id and task.workflow_version_id is None
            assert task.params["reference_resource_ids"]==[ref.id,ref.id]
            assert task.params["__provider_config_id"]==provider.id and task.params["__execution_provider"]=="gemini_image"
            with pytest.raises(HTTPException):
                generate(req.model_copy(update={"request_id":uuid4()}),SimpleNamespace(id=8),db)
