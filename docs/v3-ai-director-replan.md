# V3 AI 导演前期制作模块——修订总体方案

> 本方案将 `ai-director-preproduction` 方法论转化为 comfyui-console 的短剧项目能力。V2.1 现有的导入、改编、剧本、世界设定、分镜、ComfyUI 任务、素材和 Take 链路保持可用；V3 以版本化前期资产和确定性门禁增强现有流程，不另建一套互不兼容的生产系统。

## 1. 目标与边界

### 1.1 产品目标

把小说、剧本、故事大纲或创意逐步转化为可复用、可追溯、可审批的 AI 短剧前期制作包：

- 故事节拍、剧本台账和情感曲线；
- 版本化视听风格圣经及室内/室外色卡；
- 角色、服装状态和关键道具锚点；
- 外景拓扑、内景平面图和关键视图；
- 资产与镜头生成清单；
- 连续性审计和过期依赖追踪；
- 将已批准的生产意图编译到现有 ComfyUI 工作流参数系统。

### 1.2 明确边界

- AI 负责分析、候选方案、解释、风险提示和修复建议，不直接决定业务状态。
- 服务端确定性规则负责权限、状态流转、审批门禁、依赖和过期标记。
- 用户是最终审批者；AI 输出的 `passed=true` 不等于业务审批通过。
- 已批准版本不可被覆盖；修改产生新版本，旧版本继续可追溯。
- Manifest 是生产意图，不替代现有 WorkflowVersion 参数映射、Task、ShotTaskLink、Resource 和 Take。
- 未实际生成的图片、声音、视频或成片只能标记为“规划/待生成”，不能宣称已经完成。

## 2. 核心设计原则

1. **批准资产是事实源**：prompt 只是执行指令，不能靠 prompt 文本代替锚点、空间规则和连续性状态。
2. **稳定业务键不依赖数据库主键**：`SC-001` 等键跨版本保持不变，数据库关系仍使用外键。
3. **所有关键产物版本化**：台账、情感曲线、风格圣经、锚点、空间方案和 Manifest 都绑定来源版本。
4. **候选与当前版本分离**：AI 先生成候选，用户确认后才成为当前已批准版本。
5. **门禁由规则执行**：AI 可以诊断缺失项，但不得绕过 Checkpoint A/B/C。
6. **变更只令下游过期，不删除历史资产**：通过依赖图计算传递影响并形成修复队列。
7. **上下文按任务选择**：每次 AI 调用携带完成当前任务所需的上下文快照，而非无条件复制整个项目。
8. **保持 V2.1 兼容**：V3 使用功能开关、渐进迁移和回退路径；旧项目无需立即转换。

## 3. 修订后的业务流程

```text
项目创建与创作约束
  ↓
源材料导入与解析
  ↓
故事级台账：稳定节拍、角色/地点/道具候选、情感曲线
  ↓  首个实质反馈必须展示情感曲线
Checkpoint A：处理会影响下游的源材料矛盾
  ↓
改编候选 → 用户确认 → StoryVersion / Episode / Scene
  ↓
场景级剧本台账：场景状态、出入场、动作、服装、道具、连续性事实
  ↓
视听风格圣经 + 室内/室外色卡
  ↓
Checkpoint B：批准风格方向或代表性风格帧
  ↓
主角锚点 → 配角锚点 → 关键道具 → 服装/伤损等状态变体
  ↓
Checkpoint C：批准每个角色及关键道具的一个锚点
  ↓
外景拓扑 / 内景平面图 → 关键视图
  ↓
资产 Manifest + 连续性审计
  ↓
现有 Scene → Shot → ManifestItem/ProductionIntent
  ↓
现有 WorkflowVersion 参数编译 → Task → ComfyUI → Resource → Take
```

### 3.1 为什么需要两层台账

在 V2.1 中，Episode/Scene 只有在改编方案确认后才存在，而且应用新故事版本时可能重建。因此不能在导入后直接把 `SC-001` 绑定某个 `drama_scenes.id`。

- **故事级台账**绑定 SourceDocument/NovelAnalysisVersion，负责 BT、人物、地点、道具候选和情感曲线。
- **场景级台账**绑定 StoryVersion，负责稳定场景键、场景连续性状态以及与当前 Scene 的映射。
- 新 StoryVersion 生成后执行稳定键对齐：匹配成功则沿用稳定键；新增内容分配新键；删除内容退役键但不复用、不重排。

## 4. 各步骤交付要求

### 4.1 故事级台账和情感曲线

每个节拍至少记录：

- 稳定键、事件、目标、冲突、反转、结果、因果依赖；
- 情绪强度 `0–10`、效价 `-5–+5`、主导情绪、叙事功能；
- `explicit / inferred / assumed` 证据等级、来源定位和置信度。

情感曲线是源内容分析完成后的首个实质性结果：

- 页面必须直接显示图表；图表不可用时显示数据表；
- 同时说明最高峰、最低谷、主要转折、节奏风险和结构结论；
- 不完整材料也要展示临时曲线，并标记假设和置信度；
- 曲线数据与节拍使用同一事实源，不能分别维护两套数值；
- 保存为版本化分析资产时，不覆盖已批准版本。

### 4.2 场景级剧本台账

每个场景至少记录：

- 内/外景、地点、故事时间、天气和预计时长；
- 参与角色、服装/发妆/伤损状态、携带道具；
- 角色出入场、移动、事件、目标、冲突、反转和结果；
- 引入、消费或改变的连续性事实；
- 对应节拍、原文证据和 StoryVersion。

Checkpoint A 只阻止会让下游资产不可靠的矛盾。纯规划模式允许用户带着明确标记的假设继续。

### 4.3 风格圣经和色卡

风格圣经必须是独立版本实体，包含：

- 视觉论点、时代、地域、季节、写实度和制作价值目标；
- 构图、宽高比、镜头范围、景深、机高、运动和快门感；
- 主光/辅光/轮廓光、对比、曝光、氛围和动机光源；
- 主色、辅色、强调色、中性色、肤色保护和禁用色；
- 质感、材质语言、服装逻辑、美术规则；
- 对白语域、环境声、拟音重点和 BGM 原则；
- 参考素材来源、借鉴的高层属性、不可妥协项和禁止漂移。

无用户指定风格时，AI 最多提供三个真正不同的候选方向并推荐一个。实际批量生成资产前必须通过 Checkpoint B。

### 4.4 角色、服装和道具锚点

- Character 保留角色的规范身份和叙事信息。
- CharacterAnchorVersion 保存不可变身份锚点、禁止漂移规则、版本和批准资源。
- CharacterStateVersion 保存可变的服装、年龄状态、发妆、伤损、污渍、表情范围和配件。
- 主角锚点先于配角锚点；亲缘角色保留家族相似性但不能同脸。
- 关键道具按复现率、因果性、交互性和特写重要性排序。
- PropAnchorVersion 记录尺寸、材质、磨损、所有者和英雄视图。
- ScenePropState 记录道具在每场的地点、状态、交互和变化。

Checkpoint C 批准的是锚点版本。后续变体只能引用已批准锚点，不能覆盖身份定义。

### 4.5 空间资产

外景先建立拓扑，再生成关键视图；内景先建立平面图，再生成房间视图。

- 外景：地标、相对距离、坡向、方位、路径、出入口、人物动线、屏幕方向、空间轴线、可用机位。
- 内景：尺寸/比例、邻接、门窗、楼梯、家具锚点、光源、人物动线、摄影区和 180 度线。
- 结构数据使用有版本的 JSON Schema，包含单位、坐标系和锚点 ID。
- 关键视图必须引用批准的空间版本，不能反向改写拓扑和平面图。

### 4.6 Manifest 与连续性审计

每个资产、之后每个镜头对应一个 ManifestItem，至少引用：

- 稳定业务键和目标实体；
- StyleBibleVersion、PaletteVersion、AnchorVersion、SpatialVersion；
- 场景范围、相关参考素材、需要的视图；
- prompt、负面约束、宽高比、来源和状态；
- 生成类型、工作流版本和参数编译结果；
- Task、输出 Resource、Take 和审批结果。

连续性审计分为 AuditRun 和 AuditIssue，按以下优先级输出：

1. blocker：会导致下游生成不可靠；
2. conflict：事实矛盾或缺少锚点；
3. risk：潜在连续性风险；
4. optimization：可选优化。

审计维度包括角色身份、服装状态、道具状态、地理、屏幕方向、光照、色彩、时间顺序和因果连续性。

## 5. 领域模型设计

### 5.1 稳定标识

新增 `StableIdentity`：

```text
id, owner_id, project_id
entity_type (scene/beat/character/character_state/location/location_view/prop/style/palette)
stable_key
status (active/retired)
created_from_type, created_from_id
retired_at, retirement_reason
```

约束：`(project_id, entity_type, stable_key)` 唯一；稳定键不重排、不复用。业务外键仍指向数据库 ID。

### 5.2 台账与状态

- `ScriptLedgerVersion`：来源文档、分析版本、StoryVersion、父版本、状态、审批信息。
- `StoryBeat`：属于 LedgerVersion，存放情感数值和证据；曲线直接读取这些行。
- `LedgerScene`：属于 LedgerVersion，关联稳定场景键和可选的当前 Scene。
- `SceneCharacterAppearance`：场景中的角色状态、入场/离场和移动。
- `ScenePropState`：场景中的道具状态和变化。
- `ContinuityFact`：事实、证据等级、引入/消费/变化场景。
- `LedgerDecision`：Checkpoint A 的问题、最小选项、用户决定和假设。

### 5.3 版本化前期资产

- `StyleBibleVersion`
- `PaletteVersion`
- `CharacterAnchorVersion`
- `CharacterStateVersion`
- `PropAnchorVersion`
- `SpatialPlanVersion`
- `LocationViewVersion`

通用字段：

```text
version, parent_version_id, source_story_version_id
source_ledger_version_id, status (draft/candidate/approved/rejected/stale/retired)
generation_record_id, approved_by, approved_at
lock_version, provenance, created_at, updated_at
```

批准操作只改变候选状态并创建审批记录；修改批准版本必须创建新候选。

### 5.4 工作流、审批和依赖

- `DirectorWorkflowRun`：项目的一次 V3 工作流运行，保存单一 `current_step`。
- `DirectorStepState`：每步状态和完成度，避免把全部状态放在 JSON 中。
- `ApprovalDecision`：Checkpoint、目标版本、决定、审批者、备注。
- `ArtifactDependency`：上游版本到下游版本的有向边及依赖原因。
- `StaleRecord`：受影响资产、源变更、原因、发现版本、处理状态。
- `DetectedGap`：缺失项、严重度、目标实体、建议和处理状态。

`ShortDramaProject.stage` 继续表示项目总体阶段，不再额外增加重复的 `current_step`。

### 5.5 Manifest 和审计

- `GenerationManifestVersion`：Manifest 头、来源快照、状态和审批。
- `GenerationManifestItem`：每个资产或镜头一行，使用真实外键和目标类型。
- `ManifestReference`：相关锚点、空间、色卡和 Resource 引用。
- `AuditRun`：审计范围、输入版本、模型、开始/完成状态。
- `AuditIssue`：严重度、维度、描述、建议、状态。
- `AuditIssueTarget`：受影响实体或 ManifestItem。

### 5.6 AI 对话与操作建议

- 复用 `CreativeJob`、`AIPromptTemplate` 和 `AIGenerationRecord`，不重复建设 AI 调用日志。
- 新增 `DirectorConversation`、`DirectorMessage`、`DirectorActionProposal`。
- ActionProposal 只保存经过 schema 校验的建议命令和预期 diff。
- 用户确认后由应用服务重新校验权限、版本和门禁，再执行为新候选版本。

## 6. AI 导演服务边界

### 6.1 上下文构建

`ContextSelector` 根据操作生成带版本的 ContextSnapshot：

```text
project constraints + global summary
+ current source/story/ledger/style versions
+ target entity and direct dependencies
+ relevant downstream dependants
+ recent approved decisions
+ token budget / truncation notes / content hash
```

禁止默认把全部原文、全部消息和所有高分辨率参考塞入每次调用。请求快照记录版本 ID、hash 和必要内容；长原文使用范围引用或受控摘要。

### 6.2 结构化输出

- 每类操作有独立 Pydantic schema，不使用无限制的通用 JSON。
- 校验失败可复用现有 JSON repair，但必须限制重试次数。
- 保存 prompt 模板版本、模型、token、耗时、来源版本和响应。
- AI 结果落入 candidate；禁止直接覆盖用户当前草稿或已批准资产。

### 6.3 变更影响

确定性依赖图先计算哪些资产必须 stale；AI 只补充语义风险和修复建议。

- 相同项目和 revision 的分析任务合并。
- 高频修改 debounce/coalesce。
- 新 revision 出现时，旧结果标记 superseded，禁止回写当前状态。
- 支持取消、幂等、重试、速率限制和项目级调用预算。

### 6.4 工作流推进

规则引擎判断 `ready_to_request_approval`；用户审批决定是否通过门禁。AI 的 review 仅作为审批材料。

### 6.5 WebSocket 与权限

- WebSocket 连接绑定 user_id，并按 project/channel 订阅。
- 所有推送验证 owner_id，禁止广播其他用户的剧情和素材数据。
- API、ContextSelector、ActionProposal 执行端都必须进行资源归属校验。

## 7. 与现有 V2.1 的集成

### 7.1 复用能力

- SourceDocument/SourceChapter/SourceParagraph：源材料。
- NovelAnalysisVersion/StoryVersion：分析与剧本版本来源。
- CreativeJob/AIGenerationRecord：异步任务、幂等和 AI 审计。
- Character/CharacterVariant/Location/Prop：规范世界实体；新版本表扩展其前期资产能力。
- Scene/Shot/ShotTaskLink/Task/Resource/Take：现有生产链路。
- WorkflowVersion.param_schema/build_prompt：动态工作流参数和节点映射。

### 7.2 Manifest 编译规则

ManifestItem 不直接提交 ComfyUI：

1. 转换为 `ProductionIntent`；
2. 选择用户有权使用的生成类型和 WorkflowVersion；
3. 依据 `param_schema` 映射 prompt、negative prompt、素材、尺寸、时长等；
4. 执行现有必填、媒体类型、节点路径和资源权限校验；
5. 创建现有 Task 与 ShotTaskLink；
6. 输出回写 Resource/Take，并更新 ManifestItem 状态。

没有 Manifest 的 V2.1 项目继续使用现有 `_prompt` 逻辑。V3 稳定后也只把 `_prompt` 降为 fallback，不绕过参数编译器。

## 8. 前端信息架构

新增“导演前期”工作台，保留现有导入、剧本、世界、分镜和生产页面：

- 左侧：步骤、门禁、过期状态和完成度。
- 中间：当前步骤产物；情感曲线是完成源分析后的默认首屏内容。
- 右侧：AI 建议、缺失项、影响和连续性问题。
- 底部：对话；任何数据修改建议显示 diff 和“应用/忽略”，不提供无确认的一键执行。
- 移动端使用单栏和页签，不保留压缩后的三栏布局。

步骤页面：

1. 源材料与故事台账；
2. 剧本台账与决策；
3. 风格圣经与色卡；
4. 角色/服装/道具锚点；
5. 空间资产；
6. Manifest 与连续性审计。

## 9. 兼容、迁移和回退

- 使用 `VITE_V3_DIRECTOR_ENABLED` 与后端 `v3_director_enabled` 双端开关。
- 迁移拆分为多个小 revision，不在单个迁移中同时修改所有领域表。
- 新字段/表先 nullable 或无当前版本；旧数据按需初始化，不自动伪造“已批准”状态。
- 稳定键回填只针对已有实体生成初始注册记录，并记录 backfill provenance。
- 所有新 API 位于现有 `/api/v2/short-drama/projects/{id}/director/...` 命名空间。
- 关闭功能开关时，V2.1 路由、页面和任务链路不受影响。
- 回退只停止新模块写入，不删除已经生成的版本数据。

## 10. 验收标准

### 10.1 领域正确性

- 稳定键跨 StoryVersion 保持不变，退役后不复用。
- 所有事实区分 explicit/inferred/assumed 并保留来源定位。
- 已批准资产不可被原地覆盖。
- 服装、道具、空间和时间连续性可按场景追踪。
- 上游新版本只将真实依赖的下游标记 stale。

### 10.2 业务门禁

- 情感曲线是内容分析完成后的第一个实质结果。
- Checkpoint A/B/C 必须由用户确认。
- 无批准风格不能批量创建后续实际资产任务。
- 无批准锚点不能创建身份变体。

### 10.3 生产兼容

- Manifest 编译仍经过 WorkflowVersion.param_schema 和 build_prompt。
- 工作流、资源和媒体类型权限校验继续生效。
- Task 输出可正常回写 Resource、Take 和 ManifestItem。
- 无 V3 数据的旧项目行为保持不变。

### 10.4 安全与可靠性

- 不同 owner 之间 API、AI 上下文和 WebSocket 事件完全隔离。
- 旧 AI 结果不能覆盖较新 revision。
- 高频编辑不会为每个按键创建一次 AI 调用。
- AI 建议操作必须经过预览、确认、权限和乐观锁校验。

## 11. 实施优先顺序

1. 领域模型对齐、稳定键、版本和依赖基础。
2. 故事台账、情感曲线首反馈和 Checkpoint A。
3. StoryVersion 场景台账与稳定键对齐。
4. 风格圣经、色卡和 Checkpoint B。
5. 角色/服装/道具版本化锚点和 Checkpoint C。
6. 空间拓扑、平面图与关键视图。
7. Manifest、连续性审计和 stale 传播。
8. Manifest 到现有生产链路的编译和回写。
9. 最后增加 AI 对话、主动建议和变更影响增强。

详细开发轮次、迁移拆分和每轮验收见 `docs/v3-implementation-plan.md`。
