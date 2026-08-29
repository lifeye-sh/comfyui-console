# 漫剧制作模块第一阶段开发计划

> 依据：[第一阶段功能规格](./bigbanana-phase1-functional-spec.md)  
> 估算方式：人日，不等同于自然日；完成技术设计后再锁定排期  
> 当前目标：项目创建到角色、场景与道具确认

## 1. 当前代码基线

### 1.1 可直接复用

| 能力 | 现有位置 | 复用方式 |
| --- | --- | --- |
| 项目、Episode、Scene、Shot | `backend/app/models/short_drama.py` | 保留模型，调整服务和页面入口 |
| Character、CharacterVariant、Location、Prop | 同上 | 扩展状态与版本字段，不重建同义表 |
| 项目 CRUD、概览、软删除 | `project_service.py`、`api/v2/short_drama.py` | 增加快速创建和新概览聚合 |
| 文档导入、CreativeJob | `document_service.py`、`ai_service.py`、`worker.py` | 复用任务生命周期、幂等、取消与重试 |
| AI Provider、Prompt Template、Generation Record | 现有 AI 服务 | 增加 Phase 1 模板与结构化输出契约 |
| GenerationType、WorkflowVersion、Task、Resource | 现有生产底座 | 角色/场景/道具图片全部走现有链路 |
| 素材库 | `Resource`、`ResourceFolder`、`AssetLibraryView.vue` | 只增加领域元数据和选择器能力 |
| V3 版本/审批/依赖实现经验 | `short_drama/v3_director/` | 抽取模式；不继续暴露旧 V3 产品流程 |

### 1.2 需要重做或停止扩展

- `ShortDramaProjectListView.vue`：当前是通用卡片网格，不符合项目库首屏层级。
- `ShortDramaProjectCreateView.vue`：前置表单废弃，改为快速创建动作。
- `ShortDramaProjectOverviewView.vue`：改为“先剧本、后素材”的项目总览。
- `ShortDramaScreenplayView.vue`：旧多栏剧本工作台不满足双模式输入与固定配置栏。
- `ShortDramaWorldView.vue`、`ShortDramaStoryboardView.vue`：不作为第一阶段新 UI。
- `DirectorWorkbench.vue`：旧 V3 实验入口停止扩展；可复用服务，不复用产品页面。
- `V3GenerationManifest`：不用于 Script Manifest；两者生命周期和含义不同。

### 1.3 关键缺口

1. 一键创建项目、默认 Brief 和第 1 集的事务接口。
2. 项目库所需角色/场景/道具统计和最近项目聚合。
3. Episode 级剧本文本、输入模式、生成配置和自动保存版本。
4. 版本化 `ScriptManifestVersion` 与确认物化流程。
5. 角色/场景/道具图片版本与明确采用动作。
6. `ShotCharacterBinding` 服装绑定契约。
7. 新五页 UI、统一集内 Shell 和状态恢复。
8. 前端组件测试/E2E 基础设施目前缺失。

## 2. 技术决策

### 2.1 保留一个业务模块

- 继续使用 `/api/v2/short-drama` 与现有短剧功能开关。
- 产品名称改为“漫剧制作”，不引入第三套 API 根路径。
- 不要求 `VITE_V3_DIRECTOR_ENABLED` 才能使用第一阶段页面。
- 如需灰度，增加一个临时 UI 切换项，而不是复制整套数据。

### 2.2 Script Manifest 单独建模

拍摄清单是剧本分析产物；现有 V3 Manifest 是后期任务编译清单。计划新增：

- `ScriptManifestVersion`：project、episode、version、status、source_script_revision、mode、summary、duration、lock_version、confirmed_at。
- `ScriptManifestScene`：manifest、stable_key、order、heading、location、time、mood、pace。
- `ScriptManifestShot`：manifest scene、stable_key、order、镜头属性、内容、提示词分段、引用临时键和用户修改记录。

草稿可编辑；确认后不可原地修改。确认服务在一个事务内同步当前 Episode/Scene/Shot，并创建或合并项目素材草稿。

### 2.3 素材媒体版本

新增通用 `ProjectAssetVersion`：

- `entity_type`：character_base、character_variant、location、prop。
- `entity_id`、version、resource_id、source_task_id、status、is_current。
- `generation_snapshot`、prompt_snapshot、created_by。

不使用 `Take`，因为 `Take` 是 Shot 的输出版本。

### 2.4 任务系统

- 文本分析：`CreativeJob`。
- 图片生成：`GenerationType + WorkflowVersion + Task`。
- 媒体结果：`Resource`，再由 `ProjectAssetVersion` 采用。
- 所有创建任务接口需要 idempotency key 和 owner 校验。

## 3. 数据库迁移计划

以当前工作区迁移序列为基准，实施前再次确认 Alembic head：

| 迁移 | 内容 | 回填 |
| --- | --- | --- |
| `0028_phase1_episode_scripts` | Episode 剧本模式、文本、配置、revision；必要的自动保存版本表 | 从现有 Episode/StoryVersion 生成 legacy 当前版本，不修改正文 |
| `0029_phase1_script_manifests` | Manifest 版本、场次、镜头、引用与索引 | 旧项目不自动生成；用户下次生成时创建 |
| `0030_phase1_asset_versions` | ProjectAssetVersion；扩展 CharacterVariant、Location、Prop 状态/提示词/分类 | 现有 primary resource 记为 imported v1，但不自动确认 |
| `0031_phase1_shot_character_bindings` | ShotCharacterBinding 和唯一约束 | 从 Shot.character_ids 生成基础造型继承绑定 |

迁移要求：

- SQLite 与目标 PostgreSQL 均可 upgrade/downgrade。
- 新表带 owner/project 或可通过强外键唯一推导归属。
- 所有外键删除策略明确。
- 回填不伪造“已确认”；最多标记为 imported/pending_review。

## 4. API 计划

### 4.1 项目库与总览

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/projects/hub` | 最近项目、统计、搜索结果摘要 |
| POST | `/projects/quick-create` | 原子创建项目、Brief、第 1 集 |
| GET | `/projects/{id}/overview` | 新总览、素材计数、剧集和推荐下一步 |
| POST | `/projects/{id}/episodes` | 添加新集 |

保留现有项目 CRUD；`quick-create` 是新产品默认入口。

### 4.2 Episode 剧本

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/projects/{p}/episodes/{e}/script` | 剧本、配置、revision、当前 Job |
| PATCH | `/projects/{p}/episodes/{e}/script` | 自动保存，要求 lock_version |
| POST | `/projects/{p}/episodes/{e}/script/ai-candidates` | 续写/改写/选段改写 |
| POST | `/projects/{p}/episodes/{e}/script/ai-candidates/{id}/apply` | 应用候选并产生新版本 |
| POST | `/projects/{p}/episodes/{e}/manifest-jobs` | 创建拍摄清单任务 |

### 4.3 拍摄清单

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/projects/{p}/episodes/{e}/manifests` | 版本列表 |
| GET | `/projects/{p}/episodes/{e}/manifests/{id}` | 清单完整结构 |
| PATCH | `/projects/{p}/episodes/{e}/manifests/{id}` | 保存草稿差异 |
| POST | `/projects/{p}/episodes/{e}/manifests/{id}/confirm` | 校验、确认、物化并提取素材草稿 |
| POST | `/projects/{p}/episodes/{e}/manifests/{id}/derive` | 从已确认版派生新草稿 |

### 4.4 角色、场景和道具

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/projects/{p}/episodes/{e}/casting` | 分组数据、待确认计数、任务状态 |
| PATCH | `/projects/{p}/characters/{id}` | 编辑角色与提示词 |
| POST | `/projects/{p}/characters/{id}/variants` | 新增服装变体 |
| PATCH | `/projects/{p}/characters/{id}/variants/{v}` | 编辑变体 |
| POST | `/projects/{p}/assets/{type}/{id}/generation-tasks` | 编译并创建图片 Task |
| POST | `/projects/{p}/assets/{type}/{id}/upload` | 上传为候选版本 |
| POST | `/projects/{p}/assets/{type}/{id}/adopt/{version}` | 采用素材版本 |
| POST | `/projects/{p}/assets/{type}/{id}/replace-from-library` | 绑定素材库 Resource |

现有 Character/Variant/Location/Prop 创建删除接口继续保留，逐步补 PATCH、归属校验和引用保护。

## 5. 前端结构计划

### 5.1 页面

| 新页面/重构页面 | 目标文件 |
| --- | --- |
| 项目库 | 重构 `ShortDramaProjectListView.vue` |
| 项目总览 | 重构 `ShortDramaProjectOverviewView.vue` |
| 剧本策划 | 新建 `DramaEpisodeScriptView.vue` |
| 拍摄清单 | 新建 `DramaScriptManifestView.vue` |
| 角色与场景 | 新建 `DramaAssetsCastingView.vue` |

`ShortDramaProjectCreateView.vue` 从路由移除；可暂时保留源码用于迁移对照。

### 5.2 公共组件

- `DramaEpisodeShell.vue`：项目、集数和阶段导航。
- `DramaSaveStatus.vue`：dirty/saving/saved/conflict。
- `DramaJobProgress.vue`：CreativeJob 恢复、取消、重试。
- `ScriptConfigPanel.vue`、`ScriptEditorToolbar.vue`。
- `ManifestSceneSection.vue`、`ManifestShotRow.vue`、`PromptSegmentsEditor.vue`。
- `ProjectAssetCard.vue`：角色/场景/道具共享卡骨架。
- `CharacterCard.vue`、`WardrobeVariationsModal.vue`。
- `AssetVersionPicker.vue`、`LibraryResourcePicker.vue`。

### 5.3 状态管理

- 页面 URL 持有 projectId、episodeId、manifestId。
- 服务端数据是唯一事实源；Pinia 只保存会话缓存和未提交编辑。
- 自动保存 composable 统一处理防抖、取消旧请求、lock_version 和冲突。
- Job composable 先轮询现有接口，WebSocket 作为增强，不形成第二套状态。

### 5.4 视觉实现

- 为漫剧模块建立局部 Design Tokens，不修改平台全局变量。
- 宽屏优先；最小支持 1280 px。低于阈值时配置栏/摘要栏可折叠。
- 图片稿只做布局参考；所有文字和状态来自规格与真实数据。

## 6. 开发工作包

### WP0：契约与测试基线（2–3 人日）

工作项：

- 冻结 API DTO、状态枚举、路由和迁移命名。
- 记录当前后端 pytest、前端 typecheck/build 基线。
- 增加 Vitest + Vue Test Utils；准备 Playwright 黄金路径骨架。
- 明确旧路由跳转和数据兼容策略。

完成标准：契约评审通过；旧测试不因空壳迁移失败。

### WP1：数据与服务基础（5–7 人日）

工作项：

- 实施 0028–0031 迁移及模型/schema。
- 快速创建事务服务。
- Episode 自动保存与版本服务。
- Script Manifest 版本、确认和物化服务。
- ProjectAssetVersion 与 ShotCharacterBinding 服务。

完成标准：模型、owner 隔离、并发、幂等和迁移测试通过。

### WP2：项目库与项目总览（4–6 人日）

后端：hub 聚合、quick-create、overview 完整度和计数。  
前端：项目库、最近项目、搜索、全部项目、项目总览、剧集管理和导入入口。

完成标准：空库一键创建后直接进入带第 1 集的总览；刷新一致。

### WP3：剧本策划（6–8 人日）

后端：Episode script GET/PATCH、AI 候选、模式校验、生成前检查。  
前端：Episode Shell、配置栏、双模式空态、编辑器、AI 工具、自动保存和冲突处理。

完成标准：小说/分镜两种模式可独立保存、改写和创建生成任务。

### WP4：拍摄清单（7–10 人日）

后端：新 Job 类型、结构化解析/修复、Manifest CRUD、版本、确认物化、角色/场景/道具提取。  
前端：Job 进度、清单摘要、场次和三列镜头编辑、校验、版本和确认。

完成标准：生成任务可恢复；清单确认后生成稳定项目素材草稿且不重复。

### WP5：角色、场景、道具与素材（8–11 人日）

后端：casting 聚合、实体 PATCH、图片 Task 编译、上传、素材库替换、版本采用、引用保护。  
前端：三列角色卡、ProjectAssetCard、场景/道具卡、服装弹窗、版本选择和素材库选择器。

完成标准：角色/场景/道具均能生成、上传、替换、采用和回退；服装变体数据可供第二阶段镜头选择。

### WP6：集成、门禁与质量（4–6 人日）

- 串联项目创建到视觉设定确认的黄金路径。
- 补齐 stale、引用影响、任务失败恢复和权限错误。
- 性能：项目 hub 聚合避免 N+1；大 Manifest 分页/虚拟滚动评估。
- 无障碍：键盘焦点、按钮名称、错误与颜色非唯一表达。
- 更新 OpenAPI、开发文档和操作手册。

完成标准：验收矩阵、后端全量测试、前端 typecheck/build、组件测试和 E2E 全部通过。

## 7. 估算与并行策略

| 工作包 | 人日 | 依赖 | 可并行 |
| --- | ---: | --- | --- |
| WP0 | 2–3 | 无 | 否 |
| WP1 | 5–7 | WP0 | 部分 |
| WP2 | 4–6 | WP0、quick-create 契约 | 可与 WP1 后半并行 |
| WP3 | 6–8 | WP1 Episode 契约 | 与 WP2 并行 |
| WP4 | 7–10 | WP3、Manifest 模型 | 部分前后端并行 |
| WP5 | 8–11 | WP1 AssetVersion、WP4 提取契约 | 部分 UI 可提前 |
| WP6 | 4–6 | WP2–WP5 | 否 |
| 合计 | **36–51 人日** |  |  |

建议配置：1 名后端、1 名主要前端、1 名共享 QA/产品验收；可压缩为约 5–7 个自然周。单人串行开发按 8–11 周评估。估算不包含第二阶段镜头制作。

## 8. 测试计划

### 8.1 后端 pytest

新增测试文件建议：

- `test_drama_phase1_quick_create.py`
- `test_drama_phase1_episode_script.py`
- `test_drama_phase1_script_manifest.py`
- `test_drama_phase1_manifest_materialize.py`
- `test_drama_phase1_asset_versions.py`
- `test_drama_phase1_character_variants.py`
- `test_drama_phase1_permissions.py`

关键断言：

- owner 隔离和跨项目引用拒绝。
- quick-create 原子性与幂等。
- lock_version 冲突不覆盖。
- 旧 script revision 的 AI 结果不回写当前版本。
- 已确认 Manifest 不可原地修改。
- Manifest 重复确认不重复创建实体。
- 资源归属、版本采用唯一性和被引用删除保护。
- ComfyUI Task 失败可重试，Resource 回写幂等。

### 8.2 前端

- 组件测试：双模式、自动保存、Job 状态、Manifest 行编辑、ProjectAssetCard、Wardrobe Modal。
- 路由测试：刷新、直接链接、项目/集切换。
- E2E 黄金路径：创建项目 → 输入小说 → 生成并确认清单 → 生成/上传角色和场景 → 通过门禁。
- E2E 异常路径：AI 失败重试、图片工作流未绑定、保存冲突、素材引用删除。

### 8.3 发布门槛

```text
backend pytest 全量通过
frontend npm run typecheck
frontend npm run build
Phase 1 组件测试通过
黄金路径与四条异常路径通过
迁移 upgrade/downgrade 验证通过
```

## 9. 风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 将 V3 Generation Manifest 误当拍摄清单 | 数据语义冲突 | 独立 ScriptManifestVersion，服务模式可复用 |
| 旧 Scene 与 UI“场景”混淆 | API/数据错误 | UI 场景固定映射 Location；文档和 DTO 使用明确名称 |
| AI 输出不稳定 | 清单无法落库 | JSON Schema、修复重试、字段级 warning、禁止部分静默丢失 |
| 素材版本只存一个 Resource | 返工不可恢复 | ProjectAssetVersion + 明确 adopt |
| 自动保存覆盖多人修改 | 数据丢失 | lock_version、冲突对比、客户端草稿缓存 |
| 项目 hub 聚合慢 | 首屏性能差 | 单次聚合查询、索引、分页，禁止循环查询 |
| 旧页面长期双轨 | 维护成本 | 第一阶段完成后旧入口只跳转，不继续开发 |
| 前端无测试基础 | 回归风险 | WP0 引入最小 Vitest/Playwright 基线 |

## 10. 实施顺序与首个开发切片

第一批代码只做一个可验证的垂直切片：

1. 确认迁移 head 与数据兼容。
2. 实现 `/projects/quick-create`。
3. 一次事务创建项目、Brief、第 1 集。
4. 重构项目库“新建项目”按钮直接调用接口。
5. 项目总览显示真实第 1 集和零素材统计。
6. 加 owner、幂等、事务回滚和前端跳转测试。

该切片完成后再进入 Episode Script 数据模型，避免同时改动五个页面而没有可运行基线。

## 11. 里程碑验收

- M1：项目库与总览闭环。
- M2：双模式剧本策划与自动保存闭环。
- M3：AI 拍摄清单生成、编辑、版本和确认闭环。
- M4：角色、场景、道具提取与图片素材闭环。
- M5：第一阶段集成验收与旧入口收口。

每个里程碑必须同时包含迁移、API、前端、测试和文档，不接受只完成页面或只完成后端。

