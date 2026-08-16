from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import GenerationType, GenerationTypeConfigVersion, Workflow, WorkflowVersion
from app.services.generation_type_service import normalize_param_template


SUPPORTED_PARAMETER_TYPES = {
    "text", "textarea", "int", "float", "bool", "select", "seed",
    "image", "video", "audio", "size", "slider",
}


def _next_version(db: Session, type_id: int) -> int:
    current = db.query(func.max(GenerationTypeConfigVersion.version)).filter(
        GenerationTypeConfigVersion.generation_type_id == type_id
    ).scalar()
    return int(current or 0) + 1


def build_default_config(db: Session, generation_type: GenerationType) -> dict[str, Any]:
    bindings: list[dict[str, Any]] = []
    if generation_type.default_workflow_id:
        workflow = db.get(Workflow, generation_type.default_workflow_id)
        if workflow and workflow.current_version_id:
            bindings.append({
                "workflow_id": workflow.id,
                "workflow_version_id": workflow.current_version_id,
                "is_default": True,
            })
    return {
        "schema_version": 1,
        "basic": {
            "name": generation_type.name,
            "code": generation_type.code,
            "media_type": generation_type.media_type,
            "menu_order": generation_type.menu_order,
        },
        "page": {"title": generation_type.name, "description": ""},
        "parameters": deepcopy(normalize_param_template(generation_type.param_template, generation_type.code)),
        "parameter_schemes": [],
        "workflow_bindings": bindings,
        "outputs": {"media_type": generation_type.media_type, "multiple": True},
    }


def _merged_workflow_parameters(version: WorkflowVersion, legacy_parameters: list[dict]) -> list[dict]:
    """Use the workflow version as source of truth while enriching old mappings.

    Older versions sometimes contain only key/type/node/path. During the V2
    transition their presentation metadata is inherited by key from the old
    generation-type parameter list without mutating the immutable version.
    """
    legacy_by_key = {
        str(item.get("key")): item for item in legacy_parameters
        if isinstance(item, dict) and item.get("key")
    }
    source_schema = version.param_schema or legacy_parameters
    merged: list[dict] = []
    media_order = 0
    for item in source_schema:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        parameter = {**deepcopy(legacy_by_key.get(str(item["key"]), {})), **deepcopy(item)}
        parameter.setdefault("group", "media" if parameter.get("type") in {"image", "video", "audio"} else "parameter")
        if parameter["group"] == "media":
            media_order += 1
            parameter.setdefault("media_order", media_order)
        merged.append(parameter)
    return merged


def build_runtime_workflows(db: Session, generation_type: GenerationType, config: dict[str, Any]) -> list[dict]:
    """Return pinned, bound workflow versions with their independent forms."""
    bindings = config.get("workflow_bindings") if isinstance(config, dict) else []
    bindings = bindings if isinstance(bindings, list) else []
    if not bindings:
        workflows = db.query(Workflow).filter_by(
            generation_type_id=generation_type.id, status="active"
        ).order_by(Workflow.id).all()
        bindings = [{
            "workflow_id": item.id,
            "workflow_version_id": item.current_version_id,
            "is_default": item.id == generation_type.default_workflow_id,
        } for item in workflows if item.current_version_id]
    legacy_parameters = config.get("parameters", []) if isinstance(config, dict) else []
    legacy_parameters = legacy_parameters if isinstance(legacy_parameters, list) else []
    result: list[dict] = []
    for order, binding in enumerate(bindings):
        if not isinstance(binding, dict):
            continue
        version = db.get(WorkflowVersion, binding.get("workflow_version_id"))
        workflow = db.get(Workflow, version.workflow_id) if version else None
        if not workflow or workflow.status != "active" or workflow.generation_type_id != generation_type.id:
            continue
        result.append({
            "workflow_id": workflow.id,
            "workflow_version_id": version.id,
            "version": version.version,
            "name": workflow.name,
            "is_default": bool(binding.get("is_default")),
            "order": order,
            "parameters": _merged_workflow_parameters(version, legacy_parameters),
            "parameter_schemes": deepcopy(binding.get("parameter_schemes") or config.get("parameter_schemes") or []),
        })
    if result and not any(item["is_default"] for item in result):
        result[0]["is_default"] = True
    return result


def get_or_create_draft(db: Session, generation_type: GenerationType, user_id: int | None) -> GenerationTypeConfigVersion:
    draft = db.query(GenerationTypeConfigVersion).filter_by(
        generation_type_id=generation_type.id, status="draft"
    ).order_by(GenerationTypeConfigVersion.id.desc()).first()
    if draft:
        return draft
    source = db.get(GenerationTypeConfigVersion, generation_type.published_config_version_id) \
        if generation_type.published_config_version_id else None
    draft = GenerationTypeConfigVersion(
        generation_type_id=generation_type.id,
        version=_next_version(db, generation_type.id),
        status="draft",
        config=deepcopy(source.config) if source else build_default_config(db, generation_type),
        source_version_id=source.id if source else None,
        created_by=user_id,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def save_draft(
    db: Session, generation_type: GenerationType, config: dict[str, Any], user_id: int | None
) -> GenerationTypeConfigVersion:
    draft = get_or_create_draft(db, generation_type, user_id)
    result = validate_config(db, generation_type, config)
    draft.config = deepcopy(config)
    draft.validation_errors = result["errors"]
    db.commit()
    db.refresh(draft)
    return draft


def validate_config(db: Session, generation_type: GenerationType, config: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    workflow_checks: list[dict[str, Any]] = []

    def issue(target: list, path: str, code: str, message: str) -> None:
        target.append({"path": path, "code": code, "message": message})

    if not isinstance(config, dict):
        issue(errors, "$", "invalid_type", "配置必须是对象")
        return {"valid": False, "errors": errors, "warnings": warnings, "workflow_checks": []}
    basic = config.get("basic")
    if not isinstance(basic, dict):
        issue(errors, "basic", "required", "缺少基础信息")
    else:
        if not str(basic.get("name") or "").strip():
            issue(errors, "basic.name", "required", "类型名称不能为空")
        if basic.get("code") not in (None, generation_type.code):
            issue(errors, "basic.code", "immutable", "类型编码不可修改")
        if basic.get("media_type") not in (None, generation_type.media_type):
            issue(errors, "basic.media_type", "immutable", "媒体类型不可修改")

    workflow_parameter_mode = int(config.get("schema_version") or 1) >= 2
    parameters = config.get("parameters")
    if not isinstance(parameters, list):
        issue(errors, "parameters", "invalid_type", "参数配置必须是数组")
        parameters = []
    keys: set[str] = set()
    for index, parameter in enumerate(parameters if not workflow_parameter_mode else []):
        path = f"parameters.{index}"
        if not isinstance(parameter, dict):
            issue(errors, path, "invalid_type", "参数必须是对象")
            continue
        key = str(parameter.get("key") or "").strip()
        if not key:
            issue(errors, f"{path}.key", "required", "参数键不能为空")
        elif key in keys:
            issue(errors, f"{path}.key", "duplicate", f"参数键 {key} 重复")
        else:
            keys.add(key)
        parameter_type = parameter.get("type")
        if parameter_type not in SUPPORTED_PARAMETER_TYPES:
            issue(errors, f"{path}.type", "unsupported", f"不支持的参数类型：{parameter_type}")
        if parameter_type == "select" and not parameter.get("options") and not parameter.get("options_from"):
            issue(errors, f"{path}.options", "required", "下拉参数必须配置选项")
        value = parameter.get("default")
        if value is not None and isinstance(value, (int, float)) and not isinstance(value, bool):
            if parameter.get("min") is not None and value < parameter["min"]:
                issue(errors, f"{path}.default", "out_of_range", "默认值小于最小值")
            if parameter.get("max") is not None and value > parameter["max"]:
                issue(errors, f"{path}.default", "out_of_range", "默认值大于最大值")

    bindings = config.get("workflow_bindings", [])
    if not isinstance(bindings, list):
        issue(errors, "workflow_bindings", "invalid_type", "工作流绑定必须是数组")
        bindings = []
    default_count = 0
    for index, binding in enumerate(bindings):
        path = f"workflow_bindings.{index}"
        if not isinstance(binding, dict):
            issue(errors, path, "invalid_type", "工作流绑定必须是对象")
            continue
        version = db.get(WorkflowVersion, binding.get("workflow_version_id"))
        workflow = db.get(Workflow, version.workflow_id) if version else None
        check = {
            "workflow_version_id": binding.get("workflow_version_id"),
            "valid": bool(workflow and workflow.generation_type_id == generation_type.id),
            "missing_parameters": [],
        }
        if not check["valid"]:
            issue(errors, f"{path}.workflow_version_id", "wrong_type", "工作流版本不存在或不属于当前类型")
        else:
            mapped = {item.get("key") for item in (version.param_schema or []) if isinstance(item, dict)}
            missing = sorted(key for key in keys if key not in mapped) if not workflow_parameter_mode else []
            check["missing_parameters"] = missing
            if missing:
                issue(warnings, path, "incomplete_mapping", f"工作流尚未映射参数：{', '.join(missing)}")
            workflow_keys: set[str] = set()
            size_parameter_count = 0
            for parameter_index, parameter in enumerate(version.param_schema or []):
                parameter_path = f"{path}.parameters.{parameter_index}"
                if not isinstance(parameter, dict):
                    issue(errors, parameter_path, "invalid_type", "工作流参数必须是对象")
                    continue
                parameter_key = str(parameter.get("key") or "").strip()
                if not parameter_key:
                    issue(errors, f"{parameter_path}.key", "required", "工作流参数键不能为空")
                elif parameter_key in workflow_keys:
                    issue(errors, f"{parameter_path}.key", "duplicate", f"工作流参数键 {parameter_key} 重复")
                else:
                    workflow_keys.add(parameter_key)
                if parameter.get("type") not in SUPPORTED_PARAMETER_TYPES:
                    issue(errors, f"{parameter_path}.type", "unsupported", f"不支持的参数类型：{parameter.get('type')}")
                if parameter.get("type") == "select" and not parameter.get("options") and not parameter.get("options_from"):
                    issue(errors, f"{parameter_path}.options", "required", "下拉参数必须配置选项来源")
                if parameter.get("type") == "size":
                    size_parameter_count += 1
                    expected_source = f"{generation_type.media_type}_size"
                    if parameter.get("options_from") != expected_source:
                        issue(errors, f"{parameter_path}.options_from", "invalid_size_source", f"尺寸参数必须使用 {expected_source} 维护项")
                    targets = parameter.get("targets") if isinstance(parameter.get("targets"), dict) else {}
                    for dimension in ("width", "height"):
                        target = targets.get(dimension) if isinstance(targets.get(dimension), dict) else {}
                        target_node = (version.api_json or {}).get(str(target.get("node") or ""))
                        if not target_node or not target.get("path"):
                            issue(errors, f"{parameter_path}.targets.{dimension}", "mapping_required", f"尺寸参数尚未映射{dimension == 'width' and '宽度' or '高度'}节点")
                default_value = parameter.get("default")
                if isinstance(default_value, (int, float)) and not isinstance(default_value, bool):
                    if parameter.get("min") is not None and default_value < parameter["min"]:
                        issue(errors, f"{parameter_path}.default", "out_of_range", "默认值小于最小值")
                    if parameter.get("max") is not None and default_value > parameter["max"]:
                        issue(errors, f"{parameter_path}.default", "out_of_range", "默认值大于最大值")
                if parameter.get("type") != "size":
                    node = (version.api_json or {}).get(str(parameter.get("node") or ""))
                    path_value = str(parameter.get("path") or "")
                    if parameter.get("required") and (not node or not path_value):
                        issue(errors, parameter_path, "mapping_required", f"必填参数“{parameter.get('label') or parameter_key}”尚未映射节点")
                    elif not node or not path_value:
                        issue(warnings, parameter_path, "mapping_empty", f"参数“{parameter.get('label') or parameter_key}”将使用工作流默认值")
            if size_parameter_count > 1:
                issue(errors, f"{path}.parameters", "duplicate_size", "每个工作流只能配置一个复合尺寸参数")
            check["parameter_count"] = len(workflow_keys)
        workflow_checks.append(check)
        if binding.get("is_default"):
            default_count += 1
    if bindings and default_count != 1:
        issue(errors, "workflow_bindings", "default_count", "有工作流绑定时必须且只能设置一个默认工作流")
    if not bindings:
        issue(warnings, "workflow_bindings", "empty", "尚未绑定工作流，发布后不能创建任务")

    outputs = config.get("outputs")
    if not isinstance(outputs, dict):
        issue(errors, "outputs", "required", "缺少输出配置")
    elif outputs.get("media_type") not in (None, generation_type.media_type):
        issue(errors, "outputs.media_type", "mismatch", "输出媒体类型与生成类型不一致")

    return {"valid": not errors, "errors": errors, "warnings": warnings, "workflow_checks": workflow_checks}


def publish_draft(
    db: Session, generation_type: GenerationType, draft: GenerationTypeConfigVersion, user_id: int | None
) -> GenerationTypeConfigVersion:
    if draft.generation_type_id != generation_type.id or draft.status != "draft":
        raise ValueError("只能发布当前生成类型的草稿")
    result = validate_config(db, generation_type, draft.config)
    draft.validation_errors = result["errors"]
    if result["errors"]:
        db.commit()
        raise ValueError("配置校验失败，不能发布")
    draft.status = "published"
    draft.published_by = user_id
    draft.published_at = datetime.now(timezone.utc)
    generation_type.published_config_version_id = draft.id
    basic = draft.config.get("basic", {})
    generation_type.name = basic.get("name") or generation_type.name
    generation_type.menu_order = basic.get("menu_order", generation_type.menu_order)
    db.commit()
    db.refresh(draft)
    return draft


def list_versions(db: Session, type_id: int) -> list[GenerationTypeConfigVersion]:
    return db.query(GenerationTypeConfigVersion).filter_by(generation_type_id=type_id).order_by(
        GenerationTypeConfigVersion.version.desc()
    ).all()


def get_version(db: Session, type_id: int, version_id: int) -> GenerationTypeConfigVersion | None:
    return db.query(GenerationTypeConfigVersion).filter_by(
        id=version_id, generation_type_id=type_id
    ).first()


def diff_versions(first: GenerationTypeConfigVersion, second: GenerationTypeConfigVersion) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []

    def walk(path: str, before: Any, after: Any) -> None:
        if isinstance(before, dict) and isinstance(after, dict):
            for key in sorted(set(before) | set(after)):
                walk(f"{path}.{key}" if path else key, before.get(key), after.get(key))
        elif before != after:
            changes.append({"path": path, "before": before, "after": after})

    walk("", first.config, second.config)
    return changes


def rollback(
    db: Session, generation_type: GenerationType, source: GenerationTypeConfigVersion, user_id: int | None
) -> GenerationTypeConfigVersion:
    if source.generation_type_id != generation_type.id or source.status != "published":
        raise ValueError("只能回滚到当前类型已发布的版本")
    existing_drafts = db.query(GenerationTypeConfigVersion).filter_by(
        generation_type_id=generation_type.id, status="draft"
    ).all()
    for draft in existing_drafts:
        draft.status = "superseded"
    target = GenerationTypeConfigVersion(
        generation_type_id=generation_type.id,
        version=_next_version(db, generation_type.id),
        status="draft",
        config=deepcopy(source.config),
        source_version_id=source.id,
        created_by=user_id,
    )
    db.add(target)
    db.flush()
    return publish_draft(db, generation_type, target, user_id)
