"""ProductionIntent 服务：ManifestItem → ProductionIntent 转换与校验。

契约见实施计划第 8 轮 / RFC §8.4：
- ManifestItem 不直接提交 ComfyUI，先转换为 ProductionIntent
- 依据 WorkflowVersion.param_schema 映射 prompt、negative、素材、尺寸、时长
- 执行现有必填、媒体类型、节点路径和资源权限校验
- 映射失败时返回结构化 errors，不抛异常中断整批编译
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.comfy.prompt_builder import build_prompt
from app.models import (
    GenerationType,
    Resource,
    V3GenerationManifest,
    V3LocationViewVersion,
    V3ManifestItem,
    V3ManifestReference,
    Workflow,
    WorkflowVersion,
)
from app.services.video_rules import duration_errors


class ManifestCompileError(ValueError):
    pass


# asset_type → 建议的生成类型 code 前缀（配置驱动，不在页面硬编码生成类型）
ASSET_MEDIA_TYPE: dict[str, str] = {
    "character_anchor": "image",
    "prop_anchor": "image",
    "location_view": "image",
}


@dataclass
class ProductionIntent:
    """ManifestItem 的生产意图 DTO（RFC §8.4）。"""

    manifest_item_id: int
    asset_stable_key: str
    asset_type: str
    required_view: str
    prompt: str
    negative_constraints: str
    aspect_ratio: str
    media_type: str
    generation_type_id: int
    workflow_version_id: int | None
    params: dict[str, Any] = field(default_factory=dict)
    input_resource_ids: list[int] = field(default_factory=list)
    reference_resource_ids: list[int] = field(default_factory=list)
    validation_errors: list[dict[str, Any]] = field(default_factory=list)
    validation_warnings: list[dict[str, Any]] = field(default_factory=list)

    def out(self) -> dict[str, Any]:
        return {
            "manifest_item_id": self.manifest_item_id,
            "asset_stable_key": self.asset_stable_key,
            "asset_type": self.asset_type,
            "required_view": self.required_view,
            "prompt": self.prompt,
            "negative_constraints": self.negative_constraints,
            "aspect_ratio": self.aspect_ratio,
            "media_type": self.media_type,
            "generation_type_id": self.generation_type_id,
            "workflow_version_id": self.workflow_version_id,
            "params": self.params,
            "input_resource_ids": self.input_resource_ids,
            "reference_resource_ids": self.reference_resource_ids,
            "validation_errors": self.validation_errors,
            "validation_warnings": self.validation_warnings,
        }


def _owned_manifest(db: Session, owner_id: int, project_id: int, manifest_id: int) -> V3GenerationManifest:
    manifest = db.query(V3GenerationManifest).filter(
        V3GenerationManifest.id == manifest_id,
        V3GenerationManifest.project_id == project_id,
    ).first()
    if not manifest:
        raise ManifestCompileError("生成清单不存在")
    return manifest


def resolve_reference_resources(db: Session, owner_id: int, item: V3ManifestItem) -> list[int]:
    """解析 ManifestItem 引用的素材资源（归属校验 + 媒体类型为图片）。"""
    ref_rows = db.query(V3ManifestReference).filter(
        V3ManifestReference.manifest_item_id == item.id
    ).all()
    resource_ids: list[int] = []
    anchors = {
        "character_anchor": "V3CharacterAnchorVersion",
        "prop_anchor": "V3PropAnchorVersion",
    }
    for ref in ref_rows:
        if ref.reference_type == "character_anchor":
            from app.models import V3CharacterAnchorVersion
            anchor = db.query(V3CharacterAnchorVersion).filter(
                V3CharacterAnchorVersion.stable_key == ref.reference_key,
                V3CharacterAnchorVersion.project_id == item.project_id,
            ).order_by(V3CharacterAnchorVersion.id.desc()).first()
            if anchor:
                for rid in (anchor.front_resource_id, anchor.side_resource_id, anchor.back_resource_id):
                    if rid:
                        resource_ids.append(rid)
        elif ref.reference_type == "prop_anchor":
            from app.models import V3PropAnchorVersion
            anchor = db.query(V3PropAnchorVersion).filter(
                V3PropAnchorVersion.stable_key == ref.reference_key,
                V3PropAnchorVersion.project_id == item.project_id,
            ).order_by(V3PropAnchorVersion.id.desc()).first()
            if anchor and anchor.hero_shot_resource_id:
                resource_ids.append(anchor.hero_shot_resource_id)
        elif ref.reference_type == "location_view":
            from app.models import V3LocationViewVersion
            view = db.query(V3LocationViewVersion).filter(
                V3LocationViewVersion.stable_key == ref.reference_key,
                V3LocationViewVersion.project_id == item.project_id,
            ).order_by(V3LocationViewVersion.id.desc()).first()
            if view and view.resource_id:
                resource_ids.append(view.resource_id)
    # 归属校验：只保留当前用户拥有且未删除的图片素材
    valid: list[int] = []
    for rid in dict.fromkeys(resource_ids):
        resource = db.query(Resource).filter(
            Resource.id == rid,
            Resource.owner_id == owner_id,
            Resource.deleted_at.is_(None),
        ).first()
        if resource and resource.media_type == "image":
            valid.append(rid)
    return valid


def build_intent(
    db: Session,
    owner_id: int,
    item: V3ManifestItem,
    generation_type: GenerationType,
    workflow_version_id: int | None,
    overrides: dict[str, Any] | None = None,
) -> ProductionIntent:
    """将单个 ManifestItem 编译为 ProductionIntent 并执行校验。

    校验项与现有生产链路一致：
    - 生成类型存在且启用
    - 工作流版本匹配生成类型且 active、归属合法
    - param_schema 必填参数、节点映射、素材类型
    """
    from app.short_drama.production_service import _mapping_exists, _workflow

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    overrides = overrides or {}

    expected_media = ASSET_MEDIA_TYPE.get(item.asset_type, "image")
    if generation_type.media_type != expected_media:
        errors.append({
            "path": "generation_type",
            "code": "media_type_mismatch",
            "message": f"生成类型媒体类型 {generation_type.media_type} 与资产类型 {item.asset_type} 期望的 {expected_media} 不匹配",
        })

    workflow: Workflow | None = None
    version: WorkflowVersion | None = None
    try:
        workflow, version = _workflow(db, owner_id, generation_type, workflow_version_id)
    except Exception as exc:
        errors.append({"path": "workflow", "code": "workflow_invalid", "message": str(exc)})

    reference_ids = resolve_reference_resources(db, owner_id, item)
    params: dict[str, Any] = {}
    if version is not None:
        image_cursor = 0
        for spec in version.param_schema or []:
            key = str(spec.get("key") or "").strip()
            if not key:
                continue
            kind = spec.get("type")
            lowered = key.lower()
            value = deepcopy(spec.get("default"))
            if kind in {"text", "textarea"} and lowered in {"prompt", "positive_prompt", "text", "description"}:
                value = item.prompt
            elif lowered in {"negative_prompt", "negative", "excluded"}:
                value = item.negative_constraints
            elif lowered in {"aspect_ratio", "ratio"}:
                value = item.aspect_ratio
            elif kind == "image":
                value = reference_ids[image_cursor] if image_cursor < len(reference_ids) else None
                image_cursor += bool(value)
            params[key] = value
        params.update(overrides)
        for message in duration_errors(generation_type.media_type, params):
            warnings.append({"path": "duration", "code": "video_duration_advice", "message": message,
                             "actionable": True, "action": "set_duration", "action_label": "调整为15秒"})
        schema_keys = {str(s.get("key")) for s in version.param_schema or []}
        for key in overrides:
            if key not in schema_keys:
                warnings.append({"path": key, "code": "unknown_override", "message": "覆盖参数不在工作流映射中"})
        for spec in version.param_schema or []:
            key = str(spec.get("key") or "")
            if spec.get("required") and params.get(key) in (None, "", []):
                errors.append({"path": key, "code": "required", "message": f"缺少必填参数：{spec.get('label') or key}"})
            if not _mapping_exists(version.api_json or {}, spec):
                errors.append({"path": key, "code": "mapping_missing", "message": f"参数“{spec.get('label') or key}”没有有效的工作流节点映射"})
            if spec.get("type") in {"image", "video", "audio"} and params.get(key) not in (None, ""):
                try:
                    rid = int(params[key])
                except (TypeError, ValueError):
                    rid = 0
                resource = db.query(Resource).filter(
                    Resource.id == rid,
                    Resource.owner_id == owner_id,
                    Resource.deleted_at.is_(None),
                ).first()
                if not resource or resource.media_type != spec.get("type"):
                    errors.append({"path": key, "code": "invalid_resource", "message": f"参数“{spec.get('label') or key}”引用的素材不存在、无权访问或类型不匹配"})
                else:
                    params[key] = rid
        try:
            build_prompt(version.api_json, version.param_schema or [], params)
        except Exception as exc:
            errors.append({"path": "workflow", "code": "mapping_failed", "message": str(exc)})

    input_ids = sorted({
        int(params[str(spec.get("key"))])
        for spec in ((version.param_schema or []) if version is not None else [])
        if spec.get("type") in {"image", "video", "audio"}
        and isinstance(params.get(str(spec.get("key"))), int)
    })

    return ProductionIntent(
        manifest_item_id=item.id,
        asset_stable_key=item.asset_stable_key,
        asset_type=item.asset_type,
        required_view=item.required_view,
        prompt=item.prompt,
        negative_constraints=item.negative_constraints,
        aspect_ratio=item.aspect_ratio,
        media_type=generation_type.media_type,
        generation_type_id=generation_type.id,
        workflow_version_id=version.id if version else workflow_version_id,
        params=params,
        input_resource_ids=input_ids,
        reference_resource_ids=reference_ids,
        validation_errors=errors,
        validation_warnings=warnings,
    )


def build_intents(
    db: Session,
    owner_id: int,
    project_id: int,
    manifest_id: int,
    generation_type_id: int,
    workflow_version_id: int | None,
    item_ids: list[int] | None = None,
    overrides: dict[str, Any] | None = None,
    per_item_overrides: dict[int, dict[str, Any]] | None = None,
) -> tuple[V3GenerationManifest, list[ProductionIntent]]:
    """编译整个 Manifest（或指定 Item 列表）为 ProductionIntent 列表。

    返回 (manifest, intents)。要求 manifest 已审批；逐条校验不中断整批。
    """
    manifest = _owned_manifest(db, owner_id, project_id, manifest_id)
    if manifest.status != "approved":
        raise ManifestCompileError(f"清单 v{manifest.version} 尚未审批，不能编译")

    generation_type = db.get(GenerationType, generation_type_id)
    if not generation_type or not generation_type.enabled or generation_type.deleted_at:
        raise ManifestCompileError("生成类型不存在或已停用")

    query = db.query(V3ManifestItem).filter(V3ManifestItem.manifest_id == manifest.id)
    if item_ids:
        query = query.filter(V3ManifestItem.id.in_(item_ids))
    items = query.order_by(V3ManifestItem.id).all()
    if not items:
        raise ManifestCompileError("清单中没有可编译的清单项")

    intents = [
        build_intent(
            db, owner_id, item, generation_type, workflow_version_id,
            {**(overrides or {}), **(per_item_overrides or {}).get(item.id, {})},
        )
        for item in items
    ]
    return manifest, intents
