"""Non-destructive deterministic split preview with optimistic application."""
from copy import deepcopy
import hashlib
import json
import re
from app.short_drama.dialogue import QUOTE_PAIRS, dialogue_spans, dialogue_metrics, extract_dialogue_lines, total_duration
from app.short_drama import phase1_service, project_service


def split_preview(content: dict, scene_index: int, shot_index: int, lock_version: int) -> dict:
    try:
        source = content["scenes"][scene_index]["shots"][shot_index]
    except (KeyError, IndexError, TypeError):
        raise project_service.ProjectConflictError("镜头不存在，请刷新清单")
    text = str(source.get("content") or "")
    if len(text.strip()) < 2:
        raise project_service.ProjectConflictError("内容不足以拆镜，请先补充剧本")
    # Prefer a boundary between utterances. For one long utterance keep every
    # original character and add only a speaker label to its continuation.
    names = [c["name"] for c in content.get("characters", [])]
    spans = dialogue_spans(text, names)
    boundaries = [x["block_start"] for x in spans[1:] if x["block_start"] > 0]
    if not boundaries:
        boundaries = [m.end() for m in re.finditer(r"[，。！？；,.!?;]", text) if m.end() < len(text.rstrip())]
    cut = min(boundaries, key=lambda x: abs(x-len(text)/2)) if boundaries else len(text)//2
    continuation = next((x for x in spans if x["start"] <= cut < x["end"]), None)
    boundary = next((x for x in spans if x["start"]-1 == cut), None)
    current = continuation or boundary
    prefix = (current["speaker"] + ("（画外）" if current["offscreen"] else "") + "：") if current and current["speaker"] else ""
    opening = text[continuation["start"]-1] if continuation and continuation["start"] else ""
    suffix = QUOTE_PAIRS.get(opening, "")
    if suffix: prefix += opening
    pieces = [text[:cut] + suffix, prefix + text[cut:]]
    old_total = total_duration(float(source.get("duration") or 3), source)
    source_prompt = source.get("prompt") if isinstance(source.get("prompt"), dict) else {}
    source_original = source_prompt.get("original") if isinstance(source_prompt.get("original"), dict) else {}
    source_override = source_prompt.get("override") if isinstance(source_prompt.get("override"), dict) else {}
    source_effective = source_prompt.get("effective") if isinstance(source_prompt.get("effective"), dict) else {}
    inherited_fields = ("initial_frame", "character_consistency", "negative_constraints")
    inherited_original = {
        key: str(source_original.get(key) or source_effective.get(key) or "").strip()
        for key in inherited_fields
    }
    inherited_override = {
        key: str(source_override.get(key) or "").strip()
        for key in inherited_fields if str(source_override.get(key) or "").strip()
    }
    inherited_prompt = {
        "original": inherited_original,
        "override": inherited_override,
        "effective": {
            key: inherited_override.get(key) or inherited_original[key]
            for key in inherited_fields
        },
    }
    shots = []
    for index, piece in enumerate(pieces):
        shot = deepcopy(source)
        shot.update(content=piece, visual_description=piece, timing_schema_version=2,
                    reaction_pause=float(source.get("reaction_pause") or 0) if index == 1 else 0,
                    dialogue_lines=extract_dialogue_lines(piece, names), prompt=deepcopy(inherited_prompt), keyframe_plan={},
                    shot_jobs=[], job_reason="", qc_issues=[],
                    split_source={"shot_no": source.get("shot_no"), "start": 0 if index == 0 else cut,
                                  "end": cut if index == 0 else len(text), "inserted_prefix": "" if index == 0 else prefix, "inserted_suffix": suffix if index == 0 else ""})
        for key in ("action", "expression", "dialogue", "narration", "inner_monologue"):
            shot[key] = ""
        speech = "\n".join(x["text"] for x in shot["dialogue_lines"])
        minimum = dialogue_metrics(speech, old_total, shot["reaction_pause"])["required_seconds"]
        fraction = (cut if index == 0 else len(text)-cut) / len(text)
        shot["duration"] = round(max(.1, old_total*fraction, minimum), 2)
        shots.append(shot)
    updated = deepcopy(content)
    updated["scenes"][scene_index]["shots"][shot_index:shot_index+1] = shots
    digest = hashlib.sha256(json.dumps({"content": content, "lock_version": lock_version,
        "scene_index": scene_index, "shot_index": shot_index, "shots": shots}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {"lock_version": lock_version, "scene_index": scene_index, "shot_index": shot_index,
            "preview_hash": digest, "before": source, "shots": shots, "content": updated,
            "before_duration": old_total, "after_duration": round(sum(x["duration"] for x in shots), 2),
            "warnings": ["保留原文分段；出场资产暂沿用原镜，请复核各段实际出场。", "已继承原镜的起始帧、角色一致性和负面约束；其余镜头提示词、关键帧和镜头任务需按拆分结果补全。"]}


def edit_split(db, owner_id, project_id, episode_id, manifest_id, body, *, apply=False):
    manifest = phase1_service.owned_manifest(db, owner_id, project_id, episode_id, manifest_id)
    if manifest.status == "confirmed" or manifest.lock_version != body.lock_version:
        raise project_service.ProjectConflictError("清单已锁定或版本变化，请刷新后重新预览")
    preview = split_preview(manifest.content, body.scene_index, body.shot_index, manifest.lock_version)
    if not apply:
        return {key: value for key, value in preview.items() if key != "content"}
    if not body.preview_hash or body.preview_hash != preview["preview_hash"]:
        raise project_service.ProjectConflictError("拆镜预览已失效，请重新预览")
    return phase1_service.patch_manifest(db, owner_id, project_id, episode_id, manifest_id,
        lock_version=body.lock_version, summary=manifest.summary, content=preview["content"])
