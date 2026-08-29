# V3 AI 导演前期制作模块——开发实施计划

> 本计划是 `v3-ai-director-replan.md` 的工程拆分。采用渐进迁移、功能开关、候选审批和 V2.1 兼容策略。每轮都必须包含迁移、API、前端、测试和回退验证，不能先堆完数据库再一次性联调。

## 1. 实施约束

### 1.1 不可破坏的现有能力

- 现有 SourceDocument、NovelAnalysisVersion、StoryVersion 数据继续有效。
- 现有项目、剧本、世界设定、分镜和镜头生产页面继续可用。
- WorkflowVersion.param_schema、build_prompt 和资源权限校验继续作为任务编译入口。
- Task → ComfyUI → Resource → Take 回写链路不改为另一套任务系统。
- 所有 AI 生成先保存候选，不覆盖人工草稿或已批准版本。

### 1.2 全程共用的工程规则

- 前后端分别使用 `VITE_V3_DIRECTOR_ENABLED`、`v3_director_enabled`。
- 新表必须带 owner_id/project_id、必要索引和归属测试。
- 新版本实体必须保存 source version、parent version、generation record、审批和 lock_version。
- AI Job 带 project revision、idempotency key；旧 revision 结果不得回写当前状态。
- WebSocket 先完成用户/项目隔离，之后才允许推送导演数据。
- 每轮更新 API 类型、OpenAPI 行为测试和 README/开发文档。

## 2. 目标架构

```text
前端 Director Workbench
  ├─ 规则化步骤/门禁
  ├─ 当前版本产物
  ├─ AI 候选/建议/影响
  └─ Action diff + 人工确认
             ↓
Director API / Application Services
  ├─ WorkflowRuleService（确定性状态机）
  ├─ VersionedArtifactService（候选、审批、版本）
  ├─ DependencyService（依赖与 stale）
  ├─ ContextSelector（任务相关上下文）
  ├─ DirectorAIService（结构化候选和审查建议）
  └─ ManifestCompiler（接入现有 production_service）
             ↓
现有 V2.1 数据与任务基础设施
```

## 3. 迁移拆分

不要使用一个 `0017` 同时创建所有表。建议按依赖拆分：

| 迁移 | 内容 | 回填策略 |
|---|---|---|
| 0017 | 功能基础、StableIdentity、DirectorWorkflowRun、DirectorStepState、ApprovalDecision | 旧项目不自动创建 WorkflowRun；首次进入 V3 时按需创建 |
| 0018 | ScriptLedgerVersion、StoryBeat、LedgerScene、LedgerDecision、ContinuityFact | 不伪造旧分析；用户选择来源版本后创建候选台账 |
| 0019 | SceneCharacterAppearance、ScenePropState | 从已有 Scene JSON 只生成 inferred 候选，不自动批准 |
| 0020 | StyleBibleVersion、PaletteVersion | ProjectBrief.visual_style 可作为 legacy 来源候选 |
| 0021 | CharacterAnchorVersion、CharacterStateVersion、PropAnchorVersion | 现有 primary_resource_id 作为参考，不自动标记批准 |
| 0022 | SpatialPlanVersion、LocationViewVersion | Location.spatial_layout 作为 legacy 文本来源 |
| 0023 | ArtifactDependency、StaleRecord、DetectedGap | 仅为新版本产物建立依赖 |
| 0024 | GenerationManifestVersion/Item/Reference、AuditRun/Issue/Target | 不改动现有 Task/Take 表 |
| 0025 | DirectorConversation、DirectorMessage、DirectorActionProposal | 复用 AIGenerationRecord，不重复保存 provider 调用日志 |

每个迁移需验证 upgrade、downgrade、SQLite 和目标数据库兼容。回退不得删除用户已经创建的 V3 资产。

## 4. 开发轮次

## 第 0 轮：领域契约和兼容基线

### 目标

在写业务模型前固定名称、状态、版本和权限契约，并记录 V2.1 基线。

### 工作项

- 定义稳定键类型、资产状态、审批状态、门禁状态和 stale 原因枚举。
- 定义各版本实体的统一字段与状态转换图。
- 定义故事级台账和场景级台账的职责边界。
- 定义 ContextSnapshot、AI 候选、ActionProposal 和 Manifest 编译 DTO。
- 为现有导入、改编、剧本、分镜和 production 测试建立基线。
- 增加双端功能开关，默认关闭。

### 验收

- 领域 RFC 与数据库命名和现有 `drama_*` 表一致。
- 关闭 V3 后，现有后端测试和前端构建全部通过。
- 明确禁止 AI 直接推进状态或直接执行 CRUD。

---

## 第 1 轮：稳定键、版本、审批和确定性状态机

### 后端

- 实施迁移 0017。
- 新增 `stable_identity_service.py`：分配、沿用、退役，禁止复用和重排。
- 新增 `director_workflow_service.py`：确定性步骤和门禁，不调用 LLM。
- 新增统一 `artifact_approval_service.py`：候选、批准、拒绝和从批准版本派生新候选。
- API：获取工作流状态、创建工作流运行、提交审批。

### 前端

- 项目概览增加“导演前期（实验）”入口。
- 初版步骤导航只展示规则状态，不展示 AI 判断结果。

### 测试

- owner 隔离、唯一约束、并发分配稳定键。
- 稳定键退役后不能复用。
- 已批准版本不能原地修改。
- `current_step` 只有 DirectorWorkflowRun 一个事实源。

### 验收

- 可为项目创建独立 V3 工作流，但不会改变 Project.stage 或 V2.1 页面。

---

## 第 2 轮：故事台账、情感曲线首反馈和 Checkpoint A

### 后端

- 实施迁移 0018。
- 扩展 AI prompt：故事节拍、情感数值、证据等级、来源定位、置信度。
- 新增 `ledger_service.py`，台账绑定 SourceDocument/NovelAnalysisVersion。
- 情感曲线直接查询 StoryBeat，禁止另存一套可漂移的数据 JSON。
- 新 Job 类型：`director_story_ledger`；加入幂等、revision guard、取消和旧结果 superseded。
- Checkpoint A 用 LedgerDecision 保存最小决策集和用户决定。

### 前端

- `DirectorWorkbench.vue` 基础壳。
- `StoryLedgerStep.vue`：节拍表、证据和矛盾决策。
- `EmotionCurveChart.vue`：强度与效价双轴/双线，附数据表回退。
- 源分析完成后自动进入曲线页；这是第一个实质结果。
- 展示最高峰、最低谷、主要转折、节奏风险和结构结论。

### 测试

- 强度范围 0–10、效价范围 -5–+5。
- 每个点必须有稳定 BT/SC 键、事件、主导情绪和叙事功能。
- explicit/inferred/assumed 和 source locator 必填校验。
- 临时曲线能展示假设与置信度。
- 未处理 blocker 时规则层阻止进入需要可靠下游资产的步骤。

### 验收

- 导入并分析内容后，用户首先看到的是曲线本身，而不是“完成”提示或文档链接。

---

## 第 3 轮：StoryVersion 场景台账与稳定键对齐

### 后端

- 实施迁移 0019。
- 当用户确认改编候选生成 StoryVersion 后，创建场景台账候选。
- 实现 Scene alignment：基于来源引用、场景语义和顺序给出匹配候选；最终写入前允许用户修正。
- 保存 LedgerScene 与当前 Scene 的映射，不把稳定键直接依赖 Scene.id。
- 增加 SceneCharacterAppearance、ScenePropState、ContinuityFact CRUD。

### 前端

- `SceneLedgerStep.vue`：场景表、角色状态、服装/发妆/伤损、道具状态、出入场和移动。
- Stable ID 对齐审查页：沿用、新增、退役和人工改配。

### 测试

- 替换 StoryVersion 后，匹配场景沿用稳定键。
- 被删除的场景键退役但不重排；新增场景只取得新键。
- 服装和道具状态能按场景追溯变化。

### 验收

- Episode/Scene 重建不会使 Manifest 或连续性引用失效。

---

## 第 4 轮：风格圣经、色卡和 Checkpoint B

### 后端

- 实施迁移 0020。
- `style_bible_service.py`：最多三个候选、推荐项、版本审批、参考素材 provenance。
- StyleBibleVersion 和 PaletteVersion 分离，但通过真实外键关联。
- 实际资产生成规则检查 Checkpoint B；仅规划文档可带假设继续。

### 前端

- `StyleBibleStep.vue`：候选比较、字段化编辑和版本历史。
- 室内/室外色卡及时间段变体。
- Checkpoint B 对话框显示 AI 审查材料和用户审批。

### 测试

- 批次不能混用不兼容风格版本。
- 修改批准风格产生新候选，旧版本保持不变。
- 无批准风格时禁止批量创建实际锚点生成任务。

### 验收

- 每个下游资产都能引用确定的 StyleBibleVersion 和 PaletteVersion。

---

## 第 5 轮：角色、服装、道具锚点和 Checkpoint C

### 后端

- 实施迁移 0021。
- `anchor_service.py`：主角优先级、不可变身份、可控状态、禁止漂移。
- CharacterStateVersion 表达服装、年龄、发妆、伤损、污渍、情绪和灯光状态。
- PropAnchorVersion 和 ScenePropState 记录尺寸、材质、磨损、所有者、状态变化和场次。
- 锚点生成任务仍通过现有 GenerationType/WorkflowVersion/Task 系统。

### 前端

- `AnchorStep.vue`：主角、配角、关键道具队列。
- 身份锚点与状态变体分区展示。
- 中性正/侧/背视图和表达表的版本、预览、审批。
- Checkpoint C 逐实体审批，不允许“全局 AI 自动通过”。

### 测试

- 配角生成不能绕过主角依赖规则。
- 变体必须引用已批准锚点。
- 修改状态变量不能覆盖身份锚点。
- 无权限 Resource 不能成为参考或批准资源。

### 验收

- 可完整回答某角色在任意场景中的身份版本、服装、伤损和携带道具。

---

## 第 6 轮：空间拓扑、平面图和关键视图

### 后端

- 实施迁移 0022。
- 定义 exterior topology 与 interior floor-plan JSON Schema，包括单位、坐标系、锚点和 180 度线。
- `spatial_asset_service.py`：先结构版本、后视图版本。
- LocationViewVersion 必须引用批准或选定的 SpatialPlanVersion。

### 前端

- `SpatialStep.vue`：外景拓扑/内景平面图模式。
- 表单与简化画布编辑结构锚点、路径、机位、门窗、家具和光源。
- 关键视图联系表和室内/室外色卡引用。

### 测试

- 视图不能反向覆盖空间结构。
- 方位、坐标、单位和引用锚点 schema 校验。
- 空间版本更新后，旧关键视图被准确标记 stale。

### 验收

- 同一地点所有关键视图可追溯到同一空间版本和色卡。

---

## 第 7 轮：依赖图、Manifest 和连续性审计

### 后端

- 实施迁移 0023、0024。
- `dependency_service.py` 先以确定性规则建立 ArtifactDependency，并传递生成 StaleRecord。
- `manifest_service.py` 创建版本化 Manifest 和每资产/镜头一行的 Item。
- `continuity_service.py` 创建 AuditRun/AuditIssue；LLM 补充语义问题但不能覆盖规则结果。
- 审计覆盖身份、服装、道具、地理、屏幕方向、光照、色彩、时间和因果。

### 前端

- `ManifestStep.vue`：筛选、版本比较、引用展开和状态操作。
- `ContinuityPanel.vue`：blocker/conflict/risk/optimization 分组。
- `StaleDependencyView.vue`：源变更、传递路径、受影响资产和修复状态。

### 测试

- 每个 Item 引用真实版本外键和稳定键。
- 上游变化只影响有依赖边的下游资产。
- blocker 与 polish 分开，waive 操作带审批人和原因。
- 已批准 Manifest 不可原地修改。

### 验收

- 可从任一 ManifestItem 追溯来源故事、风格、锚点、空间、prompt 和审批链。

---

## 第 8 轮：Manifest 接入现有 ComfyUI 生产链路

### 后端

- 新增 `production_intent_service.py` 和 `manifest_compiler.py`。
- ManifestItem 转换 ProductionIntent，再交给现有 production_service。
- 继续经过 WorkflowVersion.param_schema、build_prompt、素材权限和媒体类型校验。
- 创建现有 Task/ShotTaskLink；成功后回写 Resource、Take 和 ManifestItem。
- 保留无 Manifest 的 `_prompt` fallback，不直接用 Manifest 绕过编译器。

### 前端

- ManifestItem 可选择生成类型与本类型工作流，并预览动态参数。
- 显示编译差异、必填缺失、素材引用和任务执行状态。
- 从 Take 审批结果回到 Manifest 状态。

### 测试

- 不同工作流动态参数映射完整。
- 图片、视频、音频素材归属与媒体类型校验不退化。
- 多输出任务正确生成多个 Take 并关联 ManifestItem。
- V2.1 项目无 Manifest 时继续正常生产。

### 验收

- V3 从批准资产到 ComfyUI 输出形成闭环，同时现有生产测试全部通过。

---

## 第 9 轮：AI 导演对话、建议和安全实时推送

### 前置条件

必须先修复 WebSocket 用户/项目隔离，并完成依赖图和候选审批体系。

### 后端

- 实施迁移 0025。
- `context_selector.py`：任务相关 ContextSnapshot、token budget、hash 和截断记录。
- `director_ai_service.py`：按用途分开的结构化 schema，不使用通用 actions JSON。
- `action_proposal_service.py`：生成 diff、用户确认、重新鉴权、乐观锁和执行审计。
- 变更分析采用 debounce/coalesce、revision guard、任务取消、调用限额。
- WebSocket 按 user/project/channel 发送 director 事件。

### 前端

- `GuidancePanel.vue`：建议、缺失、影响和审计问题。
- `DirectorChat.vue`：会话历史、来源版本和候选操作。
- 所有写操作显示目标、变更前后 diff、影响范围、应用/忽略。
- 移动端使用页签/抽屉单栏布局。

### 测试

- 两个用户同时在线时互相收不到项目事件。
- AI 输出不能直接执行未定义操作。
- ActionProposal 在版本过期时拒绝执行并要求重新生成 diff。
- 快速连续编辑只产生合并后的分析任务。
- 旧 revision AI 结果不能改变当前状态。

### 验收

- AI 是可审计的导演助理，不是绕过业务规则的自治代理。

## 5. API 分组建议

统一前缀：`/api/v2/short-drama/projects/{project_id}/director`

```text
GET/POST  /workflow-runs
GET       /workflow-runs/{run_id}/steps
POST      /approvals

POST/GET  /ledgers
GET       /ledgers/{id}/beats
GET       /ledgers/{id}/emotion-curve
POST      /ledgers/{id}/scene-alignment

POST/GET  /style-bibles
POST/GET  /anchors/characters
POST/GET  /anchors/props
POST/GET  /spatial-plans

POST/GET  /manifests
POST      /manifests/{id}/compile
POST/GET  /audits
GET       /stale-records

POST/GET  /conversations
POST      /conversations/{id}/messages
POST      /action-proposals/{id}/apply
POST      /action-proposals/{id}/dismiss
```

所有详情和写入端点必须同时校验 owner_id、project_id 和目标版本归属。

## 6. 测试矩阵

### 单元测试

- 稳定键分配/沿用/退役；
- 版本状态机和审批规则；
- 台账、空间和 AI 输出 schema；
- 依赖图和 stale 传播；
- ContextSelector token 预算与 revision hash；
- Manifest → ProductionIntent 参数转换。

### API/集成测试

- 权限与跨项目资源隔离；
- AI 候选确认前不修改当前版本；
- 乐观锁、幂等、重试、取消和 superseded；
- Checkpoint A/B/C 门禁；
- Manifest → Task → Resource → Take → Manifest 回写；
- WebSocket 用户与项目隔离。

### 前端测试

- 情感曲线首反馈和表格回退；
- 稳定 ID 对齐人工修正；
- 版本历史、审批和 stale 提示；
- ActionProposal diff 确认；
- 桌面三栏和移动单栏；
- 长列表、分页和大项目性能。

### 回归测试

- V2.1 导入、剧本、世界、分镜、production 全套测试；
- 生成类型和动态工作流参数映射；
- 素材库选择、预览和媒体输入；
- 调度器和 StoryWorker 不因 V3 建议任务饥饿。

## 7. 性能和成本预算

- 首屏不加载完整原文、全部 Manifest 或全部历史消息。
- 情感曲线/台账按版本和分集分页。
- 大 JSON 字段提供摘要接口，详情按需加载。
- AI 调用记录 input/output token、预计成本、耗时和缓存命中。
- 项目级并发、每日预算、最大重试和最大上下文均可配置。
- 自动影响分析只在保存事件后触发，不在表单每次按键时触发。

## 8. 发布与回退

1. 开发环境默认关闭功能开关，指定测试用户开启。
2. 完成第 1–3 轮后进行只读/候选模式内测。
3. 完成第 4–7 轮后允许生成前期资产，但不自动提交 ComfyUI。
4. 完成第 8 轮后开放生产链路闭环。
5. 第 9 轮对话能力单独灰度。
6. 回退时关闭开关和停止新 Job；不删除版本、审批、任务或素材。

## 9. 完成定义

V3 只有同时满足以下条件才算完成：

- 情感曲线首反馈、台账字段和证据分级符合交付契约；
- 风格、锚点、空间、Manifest 全部版本化并有明确审批；
- 服装、道具、地理、屏幕方向、光照、色彩、时间和因果可审计；
- 稳定 ID 跨故事版本保持可靠；
- stale 传播可解释、可追踪、不会删除历史资产；
- Manifest 通过现有动态工作流编译器执行；
- API、AI 上下文和 WebSocket 均按用户/项目隔离；
- V2.1 旧项目和现有生成页面没有功能回归；
- 文档、迁移、测试和回退说明完整。
