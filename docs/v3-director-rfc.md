# V3 AI 导演前期制作模块 —— 领域契约 RFC

> 第 0 轮交付物：在写业务模型前固定名称、状态、版本和权限契约。所有 V3 代码必须遵循本契约。
> 版本：v0.1（2026-08-22）

## 1. 功能开关

| 端 | 环境变量 | 默认值 | 说明 |
|---|---|---|---|
| 后端 | `COMFY_CONSOLE_V3_DIRECTOR_ENABLED` | `false` | V3 模块总开关 |
| 前端 | `VITE_V3_DIRECTOR_ENABLED` | `false` | 前端入口开关，依赖短剧开关 |

- 关闭时：现有 V2.1 后端测试、前端构建全部通过，V3 路由/菜单不可见。
- 禁止 AI 直接推进工作流状态或直接执行 CRUD；一切写操作经规则服务 + 人工确认。

## 2. 稳定键（Stable Identity）

### 2.1 实体类型 `entity_type` 枚举

| 值 | 说明 | 键示例 |
|---|---|---|
| `scene` | 场景（故事级/场景级台账） | `SC-001` |
| `beat` | 故事节拍 | `BT-001` |
| `character` | 角色 | `CH-001` |
| `character_state` | 角色状态变体 | `CH-001-S01` |
| `location` | 地点 | `LOC-001` |
| `location_view` | 地点视图变体 | `LOC-001-V01` |
| `prop` | 道具 | `PR-001` |
| `style` | 风格圣经 | `STYLE-v01` |
| `palette` | 调色 | `PAL-v01` |
| `spatial_plan` | 空间结构版本 | `SPL-v01` |

### 2.2 稳定键状态 `stable_key_status` 枚举

- `active` — 当前有效
- `retired` — 已退役（不复用、不重排）

规则：
- 键在同一 `(project_id, entity_type)` 内唯一。
- 已退役键不得复用。
- 业务键不依赖数据库主键，Scene/Episode 重建不改变稳定键。

## 3. 资产状态与审批

### 3.1 版本化资产统一字段

所有 V3 版本实体（台账/风格/锚点/空间/Manifest）必须包含：

```
id, project_id, stable_identity_id
version, parent_version_id
source_story_version_id, source_ledger_version_id
status, generation_record_id
approved_by, approved_at, lock_version
provenance (JSON)
created_at, updated_at
```

### 3.2 资产状态 `asset_status` 枚举

| 值 | 说明 |
|---|---|
| `draft` | 草稿，未提交审批 |
| `candidate` | AI 生成候选，待人工审批 |
| `approved` | 已批准，可作为下游事实源 |
| `rejected` | 已拒绝 |
| `stale` | 因上游变更而过期，需重新审查 |
| `retired` | 已退役 |

### 3.3 审批决策 `approval_decision` 枚举

- `approved` — 批准
- `rejected` — 拒绝（附理由）
- `waived` — 豁免（附审批人和原因，仅限 blocker 降级场景）

状态转换图：

```
draft ──提交──▶ candidate ──批准──▶ approved ──上游变更──▶ stale
                  │  ▲                                   │
                  │  └──────────重新生成──────────────────┘
                  └──拒绝──▶ rejected（可修改后重新提交）
approved ──版本化修改──▶ 产生新候选（旧版保持 approved 不变）
```

- 已批准版本不得原地修改；修改必须产生新候选 + 新版本号。
- 用 `lock_version` 乐观锁防止并发覆盖。

## 4. 工作流门禁

### 4.1 步骤（DirectorWorkflowRun.step）

```
0 源材料导入（沿用 V2.1）
1 故事级台账 + 情感曲线     ← Checkpoint A
2 改编候选确认 → StoryVersion（沿用 V2.1）
3 场景级剧本台账
4 风格圣经 + 色卡           ← Checkpoint B
5 主角/配角/道具锚点         ← Checkpoint C
6 外景拓扑/内景平面图
7 Manifest + 连续性审计
8 生产编译（接入 V2.1）
```

### 4.2 门禁状态 `gate_status` 枚举

- `pending` — 未到检查点
- `blocked` — 存在未解决 blocker
- `passed` — 已通过
- `waived` — 已豁免

### 4.3 检查点强制规则（确定性规则，不调用 LLM）

- **Checkpoint A**：故事台账存在且无未解决的 blocker 矛盾，才能进入改编候选。
- **Checkpoint B**：批准 StyleBibleVersion 后才允许批量创建实际锚点生成任务；仅规划文档可带假设继续。
- **Checkpoint C**：每个角色/道具批准一个锚点后才能生成变体；不允许全局 AI 自动通过。
- 依赖顺序：`STYLE → 主角 → 配角 → 道具 → 拓扑/平面图 → 关键视图 → 变体`；不可用下游反向定义上游。

## 5. 台账职责边界

### 5.1 故事级台账（ScriptLedgerVersion）

- 绑定 `SourceDocument` + `NovelAnalysisVersion`。
- 产出：`StoryBeat`（BT）、故事级人物/地点/道具候选、情感曲线。
- `StoryBeat` 必含：稳定键、事件、目标、冲突、反转、结果、因果依赖、情绪强度 `0-10`、效价 `-5~+5`、主导情绪、叙事功能、证据等级、来源定位。
- 情感曲线**直接查询 StoryBeat**，禁止另存一套可漂移 JSON。

### 5.2 场景级台账（LedgerScene）

- 绑定 `StoryVersion`（改编确认后的版本）。
- 产出：场景稳定键、`SceneCharacterAppearance`（角色状态：服装/发妆/伤损/情绪）、`ScenePropState`（道具状态：所有者/位置/状态变化）、`ContinuityFact`。
- 与当前 `Scene` 通过映射关联，稳定键不直接依赖 Scene.id。
- 场景删除 → 键退役；场景新增 → 只取新键。

## 6. 证据等级

| 值 | 说明 |
|---|---|
| `explicit` | 原文明确 |
| `inferred` | 推断 |
| `assumed` | 假设（需置信度） |

每个 StoryBeat / LedgerScene 必须带 `evidence_type` 和 `source_locator`（章节/段落定位）。

## 7. Stale 原因枚举

| 值 | 说明 |
|---|---|
| `source_story_changed` | 源故事版本变更 |
| `ledger_changed` | 台账变更 |
| `style_changed` | 风格圣经版本变更 |
| `anchor_changed` | 锚点变更 |
| `spatial_changed` | 空间结构版本变更 |
| `manual` | 人工标记 |

## 8. DTO 定义

### 8.1 ContextSnapshot（上下文快照）

```json
{
  "project_id": 1,
  "story_version_id": 3,
  "ledger_version_id": 2,
  "style_version_id": 4,
  "approved_anchors": ["CH-001", "CH-002", "PR-001"],
  "spatial_plan_ids": [5],
  "manifest_version_id": 6,
  "revision": 12
}
```

- AI Job 携带 `project_revision` + `idempotency_key`。
- 旧 revision 的 AI 结果不得回写当前状态。

### 8.2 AICandidate（AI 候选）

```json
{
  "id": 1,
  "target_type": "story_beat",
  "target_ref": "BT-007",
  "source_snapshot_revision": 12,
  "payload": { "...": "AI 结构化输出" },
  "validation_errors": [],
  "status": "candidate",
  "generation_record_id": 8
}
```

### 8.3 ActionProposal（操作提案）

```json
{
  "id": 1,
  "type": "apply_ledger_scene",
  "target": "SC-012",
  "payload": { "changes": ["..."] },
  "impact": ["SC-013", "CH-001-S01"],
  "requires_approval": true,
  "status": "pending"
}
```

### 8.4 ManifestItem → ProductionIntent 编译

```
ManifestItem {
  stable_key, asset_type, scenes, style_version,
  palette_version, reference_ids, required_view,
  prompt, negative_constraints, aspect_ratio, status
}
→ ProductionIntent {
  generation_type_code, workflow_version_id,
  params (动态参数), shot_id, take_id
}
→ 现有 production_service → WorkflowVersion.param_schema → build_prompt → Task
```

- 保留无 Manifest 的 `_prompt` fallback。
- 不改动现有 Task/ShotTaskLink/Take 表；ManifestItem 与 Task/Take 通过新增关联。

## 9. 权限与归属

- 所有新表带 `owner_id` + `project_id` + 必要索引。
- 资源引用（`reference_resource_ids`/`primary_resource_id`）必须校验归属和媒体类型。
- 无权限 Resource 不能成为参考或批准资源。
- WebSocket 先完成用户/项目隔离后才允许推送导演数据。

## 10. 兼容基线

- 关闭 V3 后，现有 V2.1 短剧（导入/改编/剧本/分镜/生产）和后端测试全部通过。
- 现有 `drama_*` 表命名不变；V3 新表使用 `v3_*` 前缀（如 `v3_stable_identities`）。
- AI 生成先保存候选，不覆盖人工草稿或已批准版本。

## 11. 迁移计划（0017–0025）

见 `docs/v3-implementation-plan.md` 第 3 节。每个迁移幂等，回退不删除用户已创建的 V3 资产。
