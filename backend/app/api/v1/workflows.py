"""工作流路由 /api/v1/workflows。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import CurrentUser, DBSession
from app.comfy.formats import parse_api_json
from app.models import Workflow, WorkflowVersion
from app.services import workflow_service
from app.schemas.schemas import WorkflowCreateIn, WorkflowOut, WorkflowPatchIn, WorkflowVersionIn, WorkflowVersionOut

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("/parse", response_model=None)
def parse_json(user: CurrentUser, body: dict, db: DBSession) -> dict:
    """解析 ComfyUI API JSON。

    如果传入 generation_type_code，则以该类型的参数模板为基准返回参数映射框架，
    让用户把 JSON 节点映射到固定参数上。否则自动识别。
    """
    api_json = body.get("api_json")
    if not api_json or not isinstance(api_json, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请提供有效的 API JSON 对象")

    gt_code = body.get("generation_type_code")
    if gt_code:
        # 以生成类型参数模板为基准
        from app.services.generation_type_service import PARAM_TEMPLATES, get_all_select_options
        # V2 配置编辑器传入当前草稿参数，匹配必须以用户正在设计的参数为准；
        # 未传入时继续兼容 V1 固定模板调用方。
        supplied_parameters = body.get("parameters")
        template = supplied_parameters if isinstance(supplied_parameters, list) else PARAM_TEMPLATES.get(gt_code, [])
        select_options = get_all_select_options(db)
        # 解析节点列表
        from app.comfy.formats import parse_api_json, NODE_TYPE_RULES, match_input_field, title_matches_parameter
        auto = parse_api_json(api_json)
        # 构建参数映射框架：每个参数带 node/path 留空，type/label/default 来自模板
        params = []
        used_media_nodes: set[str] = set()
        for p in template:
            if not isinstance(p, dict) or not p.get("key") or not p.get("type"):
                continue
            item = dict(p)
            # 页面联动等配置不属于工作流参数映射，避免写入版本快照。
            item.pop("visible_when", None)
            item.pop("help", None)
            # select 类型补上 options
            if item.get("options_from"):
                item["options"] = select_options.get(item["options_from"], [])
            # 尝试自动匹配节点
            matched_node = ""
            matched_path = ""
            key = str(item.get("key") or "")
            param_type = str(item.get("type") or "")
            for node_id, node in api_json.items():
                ct = node.get("class_type", "")
                inputs = node.get("inputs", {}) or {}
                rule = NODE_TYPE_RULES.get(ct, {})
                if not rule.get("params"):
                    continue
                for field, spec in rule["params"].items():
                    is_media_match = (
                        item.get("type") in ("image", "video", "audio")
                        and spec.get("type") == item.get("type")
                        and str(node_id) not in used_media_nodes
                    )
                    is_prompt_match = key == "prompt" and rule.get("is_prompt") and field == "text"
                    is_negative_match = key == "negative_prompt" and rule.get("is_negative_prompt") and field == "text"
                    if field == key or spec.get("label") == item.get("label") or is_media_match or is_prompt_match or is_negative_match:
                        actual_field = match_input_field(inputs, param_type, field)
                        if not actual_field:
                            continue
                        matched_node = node_id
                        matched_path = f"inputs.{actual_field}"
                        break
                if matched_node:
                    break
            if not matched_node:
                for node_id, node in api_json.items():
                    inputs = node.get("inputs", {}) or {}
                    title = str((node.get("_meta") or {}).get("title", ""))
                    if not title_matches_parameter(title, key, str(item.get("label") or "")):
                        continue
                    field = match_input_field(inputs, param_type)
                    if field:
                        matched_node = node_id
                        matched_path = f"inputs.{field}"
                        break
            item["node"] = matched_node
            item["path"] = matched_path
            if matched_node and item.get("type") in ("image", "video", "audio"):
                used_media_nodes.add(str(matched_node))
            params.append(item)

        return {
            "nodes": auto["nodes"],
            "param_schema": params,
            "output_mapping": auto["output_mapping"],
            "suggested_name": auto["suggested_name"],
            "media_type": auto["media_type"],
            "template_source": gt_code,
        }
    else:
        return parse_api_json(api_json)


@router.get("", response_model=list[WorkflowOut])
def list_(
    user: CurrentUser,
    db: DBSession,
    media_type: str | None = None,
    generation_type_code: str | None = None,
) -> list[WorkflowOut]:
    return [WorkflowOut.model_validate(w) for w in workflow_service.list_workflows(db, media_type, generation_type_code)]


@router.post("", response_model=WorkflowOut, status_code=201)
def create(body: WorkflowCreateIn, user: CurrentUser, db: DBSession) -> WorkflowOut:
    try:
        workflow = workflow_service.create_workflow(db, body, user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return WorkflowOut.model_validate(workflow)


@router.patch("/{workflow_id}", response_model=WorkflowOut)
def patch_workflow(
    workflow_id: int,
    body: WorkflowPatchIn,
    user: CurrentUser,
    db: DBSession,
) -> WorkflowOut:
    workflow = db.get(Workflow, workflow_id)
    if not workflow or workflow.status != "active":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "工作流不存在")
    try:
        workflow = workflow_service.patch_workflow(db, workflow, body.name)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return WorkflowOut.model_validate(workflow)


@router.post("/{workflow_id}/versions", response_model=WorkflowVersionOut, status_code=201)
def add_version(workflow_id: int, body: WorkflowVersionIn, user: CurrentUser, db: DBSession) -> WorkflowVersionOut:
    try:
        v = workflow_service.add_version(db, workflow_id, body)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return WorkflowVersionOut.model_validate(v)


@router.get("/{workflow_id}/versions/{version_id}/detail")
def get_version_detail(workflow_id: int, version_id: int, user: CurrentUser, db: DBSession) -> dict:
    """获取工作流版本详情：api_json、param_schema、output_mapping，以及解析出的节点列表。"""
    v = db.get(WorkflowVersion, version_id)
    if not v or v.workflow_id != workflow_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "版本不存在")
    from app.comfy.formats import parse_api_json
    auto = parse_api_json(v.api_json or {})
    return {
        "id": v.id,
        "version": v.version,
        "api_json": v.api_json,
        "param_schema": v.param_schema or [],
        "output_mapping": v.output_mapping or {},
        "nodes": auto["nodes"],
    }


@router.patch("/{workflow_id}/versions/{version_id}")
def update_version(
    workflow_id: int,
    version_id: int,
    body: dict,
    user: CurrentUser,
    db: DBSession,
) -> dict:
    """更新工作流版本的参数映射和输出映射。"""
    v = db.get(WorkflowVersion, version_id)
    if not v or v.workflow_id != workflow_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "版本不存在")
    if "param_schema" in body:
        v.param_schema = body["param_schema"]
    if "output_mapping" in body:
        v.output_mapping = body["output_mapping"]
    if "api_json" in body:
        v.api_json = body["api_json"]
    db.commit()
    db.refresh(v)
    return {"ok": True, "id": v.id}


@router.post("/{workflow_id}/versions/{version_id}/test")
async def test_version(
    workflow_id: int,
    version_id: int,
    body: dict,
    user: CurrentUser,
    db: DBSession,
) -> dict:
    node_id = body.get("node_id")
    params = body.get("params", {})
    if not node_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "缺少 node_id")
    try:
        return await workflow_service.test_execute(db, version_id, int(node_id), params, user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"节点执行失败：{e}")


@router.delete("/{workflow_id}", status_code=204)
def delete(workflow_id: int, user: CurrentUser, db: DBSession) -> None:
    wf = db.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "工作流不存在")
    wf.status = "deleted"
    db.commit()
