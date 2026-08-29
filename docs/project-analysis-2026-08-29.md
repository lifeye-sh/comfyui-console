# comfyui-console 项目全面体检报告

> 生成日期：2026-08-29
> 分析方式：读取仓库 + 文档，在隔离 Linux 环境复现后端测试、前端类型检查/构建、Alembic 迁移。
> 结论口径：本报告基于「当前工作目录的真实状态」（含未提交改动），非仅基于 git 提交历史。

---

## 一、结论摘要

**总体判断：代码体量大、架构分层清晰、功能迭代激进，但当前处于「多线并行 + 大量未提交 + 测试红灯 + 迁移链断裂」的高风险中间态。**

| 维度 | 状态 | 一句话结论 |
|---|---|---|
| 代码规模 | 🟢 中大型 | 后端 2.1 万行 / 前端 1.5 万行，模块划分规范 |
| 前端类型检查 | 🟢 通过 | `vue-tsc --noEmit` 零错误 |
| 前端构建 | 🟡 本机可构建 | 用户机器有 8/29 的 `dist/` 产物；本分析环境因缺 Linux 版 rollup 二进制无法复现 |
| 后端测试 | 🔴 红灯 | 159 用例：124 通过 / 22 失败 / 13 错误（约 22% 失败率） |
| Alembic 迁移 | 🔴 断裂 | 全新库 `upgrade head` 在 0018 处报 `table already exists` |
| 版本控制 | 🟠 高风险 | 仅 6 个提交；53 个已跟踪文件被改 + 67 个未跟踪项未提交 |
| 文档一致性 | 🟠 严重漂移 | 核心四文档仍停在 v0.2/v0.3/v1.0，落后代码约 2 个世代 |

**最需要立即处理的三件事（P0）：**
1. 修复 Alembic 迁移链（`0001` 用了 `Base.metadata.create_all`，导致新库 `alembic upgrade head` 必然失败）。
2. 修复 35 个红测试（V3 manifest 审计/编译集群 + 若干疑似回归）。
3. 清理 `.git/index.lock` 残留 + 梳理 120 处未提交/未跟踪改动（否则无法提交、且工作随时可能丢失）。

---

## 二、项目概览与版本线

项目是面向本地/远程 ComfyUI 的统一管理平台。当前实际承载了 **六条并行的产品线**，远超 `CLAUDE.md` 所描述的「V1/V2/V2.1」三套界面：

| 产品线 | 状态 | 说明 |
|---|---|---|
| V1 基线 | ✅ 已提交 | 原始稳定界面，路由 `/v1` 等，回退保障 |
| V2 Glassmorphism | ✅ 已提交 | 新界面 `/v2`，8 轮迭代 |
| V2.1 AI 短剧工作台 | ✅ 已提交 | 双开关控制，0~9 轮 |
| V3 AI 导演前期制作 | 🟠 完成未提交 | 10 轮（0~9）代码已写完，迁移 0017–0027，全部未提交 |
| BigBanana 漫剧复刻（Phase 1） | 🟠 早期未提交 | 文档 + 后端基础 + 4 个前端骨架视图 + 迁移 0028，WP0–WP6 计划里 WP0 尚未做 |
| Gemini 图片供应商 | 🟠 中期未提交 | 配置/网关/调度器按模型并发通道，迁移 0029–0032，含前端设置页 |

时间线推断：最后一个提交是 2026-08-22（V2 媒体编辑/资产生产工具）。此后 8/23–8/29 的 V3、BigBanana、Gemini 工作全部堆在工作区未提交。

---

## 三、代码规模与结构

### 3.1 规模

| 指标 | 数值 |
|---|---|
| 后端 Python 文件 | 104 个（`backend/app/`），共 20,933 行 |
| 前端 Vue + TS | 78 个 `.vue` + 18 个 `.ts`，共 14,713 行 |
| Alembic 迁移 | 32 个（0001–0032） |
| 测试文件 | 31 个，159 个用例 |
| git 跟踪文件 | 335 个；6 个提交 |

### 3.2 后端模块结构（`backend/app/`）

- `api/v1`（17 个模块）：auth / users / nodes / workflows / generation_types / batches / tasks / resources / resource_folders / settings / prompts / shares / audit_logs / dashboard / runtime
- `api/v2`（4 个模块）：generation_type_configs / short_drama / short_drama_director / image_providers
- `models`（8 个文件）：core / ai / production / prompt / short_drama / share_audit / **v3_director**（新增）
- `schemas`：schemas / short_drama / prompts / generation_type_config / **v3_director**（新增）
- `services`（14 个）：auth / batch / task / resource / workflow / node / prompt / share / audit / dashboard / generation_type* / **image_provider_service**（新增）
- `short_drama/`（业务域）：ai / document / project / screenplay / storyboard / world / production / phase1 / worker / parsers
- `short_drama/v3_director/`（**新增 17 个服务文件**）：anchor / artifact_approval / context_selector / continuity / director_ai / director_workflow / director_ws_publish / ledger / manifest_compiler / manifest / production_intent / scene_ledger / spatial_asset / stable_identity / style_bible / action_proposal
- `comfy/`、`queue/`、`storage/`、`ws/`、`core/`

分层清晰，符合 `CLAUDE.md` 约定的「服务层注入依赖 / 异步优先 / 类型注解」规范。

### 3.3 前端结构（`frontend/src/`）

- `v2/features/` 按功能域划分：generate（生成）、assets（素材）、generation-config、short-drama、tasks、settings
- 新增 BigBanana 视图：`DramaProjectShell.vue`、`DramaEpisodeScriptView.vue`（剧本策划）、`DramaScriptManifestView.vue`（拍摄清单）、`DramaAssetsCastingView.vue`（角色与场景）——目前均为骨架（90–179 行）
- 新增 V3 视图：`DirectorWorkbench.vue`
- 新增设置视图：`ImageProviderSettingsView.vue`

---

## 四、构建与测试状态

### 4.1 前端

| 检查项 | 结果 |
|---|---|
| `vue-tsc --noEmit`（类型检查） | ✅ 通过，零错误（此前记忆里的 `DynamicGenerateView.vue TS2367` 遗留错误已修复） |
| `npm run build`（含 vite build） | 🟡 本分析环境无法复现：`node_modules` 为 Windows 平台安装，缺 `@rollup/rollup-linux-x64-gnu`；但仓库存在 8/29 生成的 `frontend/dist/`，证明**用户本机 build 是通的** |

### 4.2 后端

**应用可启动**：`from app.main import app` 导入成功，`/health`、`/` 及全部 v1/v2 路由均已挂载。

**测试结果（pytest，全量 159 用例，耗时 57.5s）：**

```
124 passed / 22 failed / 13 errors
```

失败与错误分布：

| 文件 | 数量 | 根因 |
|---|---|---|
| `test_v3_manifest_audit.py` | 13 errors | `sqlite3.IntegrityError: NOT NULL constraint failed: v3_palette_versions.version`（fixture 建 StyleBible 时未给 Palette 的 version 赋值，且该列无 server_default） |
| `test_v3_manifest_compile.py` | 12 failed | `ManifestCompileError: 清单 v1 尚未审批，不能编译`（编译器审批门禁已生效，但测试 fixture 未先审批清单）；另有 asyncio 超时 |
| `test_generation_type_config_versions.py` | 4 failed | `asyncio.TimeoutError`（TestClient 调异步端点超时） |
| `test_runtime_monitoring.py` | 2 failed | `asyncio.TimeoutError` |
| `test_generation_type_deletion.py` | 1 failed | `asyncio.TimeoutError` |
| `test_resource_folders.py` | 1 failed | `assert archive_existing(db) == 1` 实得 0（`resource_folder_service.py` 有未提交改动，疑似回归） |
| `test_short_drama_ai.py` | 1 failed | `IndexError: list index out of range`（`ai_service.py` 有 +285 行未提交改动，疑似回归） |
| `test_v3_director_ai.py` | 1 failed | `ProposalError: 目标资产不存在：prop_anchor:CH-001`（fixture 数据与提案目标不符） |

**需要甄别的一类失败**：`asyncio.TimeoutError` 类（约 7 个）出现在 `generation_type_config_versions` / `generation_type_deletion` / `runtime_monitoring` 这些**已提交**的旧测试里。本分析环境使用的是较新的 `fastapi 0.141 + httpx`（项目未设上限版本），而 starlette 的 TestClient 与 httpx 存在弃用警告（`install httpx2 instead`）。因此这些超时**可能是依赖版本漂移所致，而非代码回归**，建议在用户本机（锁定依赖版本）复核后再定性。

**结论**：测试套件整体红灯。其中 **V3 manifest 审计/编译集群（25 项）与 resource_folders / short_drama_ai（各 1 项）基本可判定为真实代码或 fixture 问题**，与「V3 第 7/8 轮 16/14 个服务级测试通过」的历史记录形成反差——那些是通过独立脚本（`run_r8_tests.py` / `run_r9_tests.py`）在内存库单测的，未纳入 pytest 套件回归。

---

## 五、版本控制状态（未提交改动盘点）

**风险等级：高。** 6 个提交对应到 8/22，之后约一周的高强度开发全部未提交。

| 类别 | 数量 |
|---|---|
| 已跟踪文件被修改 | 53 个（+2033 / -225 行） |
| 未跟踪文件/目录 | 67 个 |
| 未跟踪迁移 | 16 个（0017–0032） |
| 未跟踪新增测试 | 5 个 |

未提交工作按主题分三块：

1. **V3 AI 导演**（最大块）：`models/v3_director.py`、`schemas/v3_director.py`、`api/v2/short_drama_director.py`、`short_drama/v3_director/`（17 个服务文件）、迁移 0017–0027、`DirectorWorkbench.vue`、`ws/gateway.py`（+126，用户隔离）、`queue/dispatcher.py`（+306，owner_id 透传）。
2. **BigBanana Phase 1**：迁移 0028（`script_manifest_versions` / `project_asset_versions` / `shot_character_bindings` + 集字段）、`short_drama/phase1_service.py`、4 个 Drama 前端骨架视图、`test_short_drama_phase1.py`（仅 1 个用例）。
3. **Gemini 图片供应商**：`services/image_provider_service.py`、`api/v2/image_providers.py`、迁移 0029–0032（含 0031 加 size 列、0032 又移除——有反复）、`ImageProviderSettingsView.vue`、调度器新增按模型并发通道（`_gemini_jobs` / 恢复排队逻辑）、`test_gemini_image_provider.py`。

**两个应立即处理的仓库卫生问题：**

- **`.git/index.lock` 残留**（0 字节，8/29 18:17）：会阻塞 `git add` / `git commit`。本分析环境因权限无法删除；需在用户本机 `rm .git/index.lock`（确认无 git 进程后）。
- **根目录散落的 `小公主.txt`**（14.9 KB，未跟踪）：是一段同人小说文本（全职高手角色），应为小说导入功能的测试素材，误留在仓库根目录。建议移入测试夹具目录或删除，避免误提交。

---

## 六、文档与代码一致性

核心结论：**文档体系已经分裂为「旧基线四件套」与「新工作独立文档」两套，彼此未回写。**

| 文档 | 版本 | 覆盖范围 | 是否落后于代码 |
|---|---|---|---|
| `architecture.md` | v0.2 | 11 领域实体 / 12 API 组 | 🔴 落后：无 V3 director 模型、无 image_providers、无 ScriptManifestVersion |
| `feature-list.md` | v0.2 | 10 模块菜单 | 🔴 落后：无导演工作台、无图片模型配置、无 BigBanana |
| `feature-specification.md` | v0.3 | 12 章页面规格 | 🔴 落后：同上 |
| `development-plan.md` | v1.0 | 任务卡 CC-00 ~ CC-36 | 🔴 落后：只覆盖到已提交基线（V1/V2/V2.1），未纳入 V3 十轮、BigBanana WP0–6、Gemini |
| `v3-ai-director-replan.md` / `v3-implementation-plan.md` / `v3-director-rfc.md` | 2026-08-22~23 | V3 十轮 + RFC 契约 | 🟢 与 V3 代码基本对齐（细节有少量命名漂移） |
| `bigbanana-*.md`（4 份） | 2026-08-28 | BigBanana 复刻总纲/功能/计划/UI | 🟡 计划 WP0（前端测试基线）尚未落地，代码仅为 WP1 早期 |

**`CLAUDE.md` 本身已过时**：其「当前阶段」只写到 Phase 0~4（CC-00~36）与部署文档，完全没有提及 V3、BigBanana、Gemini 三条新线，也没有反映「大量未提交」的现实。

---

## 七、关键问题清单（按严重度）

### P0（阻塞交付，应立即处理）

1. **Alembic 迁移链在新库必然失败**。`0001_initial.py` 用 `Base.metadata.create_all(op.get_bind())` 一次性建了「当前全部模型的表」（含 V3/BigBanana），导致后续 `0018` 用 `op.create_table("v3_stable_identities")` 时表已存在而报错。`0002/0003` 等用 `checkfirst=True` 才侥幸躲过。后果：`docs/deployment.md` 与 `CLAUDE.md` 文档化的 `alembic upgrade head` 部署路径在全新环境跑不通；开发态靠 `init_db()` 的 create_all 才没暴露。
2. **测试套件红灯（35 项）**，其中 V3 manifest 审计/编译集群（25 项）与 resource_folders / short_drama_ai 回归（各 1 项）为真实问题。
3. **约 120 处改动未提交 + `.git/index.lock` 残留**，当前无法正常提交，工作成果面临丢失风险。

### P1（质量与技术债）

4. **Schema 管理与数据迁移双轨**：`init_db()` 里既有 create_all 兜底，又有对 `resources.folder_id` 的手写 `ALTER TABLE` 补丁，与 Alembic 迁移并存，容易漂移（`scripts/reconcile_sqlite_alembic.py` 的存在本身就是这一问题的佐证）。
5. **V3 测试依赖独立脚本而非 pytest 套件**：`run_r8_tests.py` / `run_r9_tests.py` 留在仓库里，用内存库绕开迁移与 conftest，导致「脚本绿、套件红」的假象。
6. **依赖无上限版本约束**：`fastapi>=0.115`、`httpx>=0.28` 等未设上限，已在本分析环境触发 TestClient/httpx 弃用与疑似超时。
7. **前端零自动化测试**：`package.json` 无 Vitest/Playwright；BigBanana 计划的 WP0 就要求补测试基线，目前未做。
8. **`datetime.UTC` 等 3.11 语法**需靠 `datetime.now(timezone.utc)` 兜底才能跑在 3.10（项目声明 `>=3.11`，但仓库里多处加了 3.10 兼容），版本边界不清晰。

### P2（文档与仓库卫生）

9. 核心四文档（architecture/feature-list/feature-spec/development-plan）与 `CLAUDE.md` 长期未随代码更新。
10. `backend/.pytest_cache`、`.test-tmp`、`__pycache__`、`frontend/dist`、`node_modules` 等应在 `.gitignore` 中显式排除（`.pytest_cache` 在本环境有权限异常）。
11. `小公主.txt` 测试素材散落根目录。

---

## 八、建议行动项（按顺序）

1. 本机删除 `.git/index.lock` → `git add` 分主题提交（建议：① V3 AI 导演、② BigBanana Phase 1、③ Gemini 图片供应商，分三个提交，符合「一卡一提交」约定）。
2. 修复 `0001_initial.py`：改为显式 `op.create_table` 清单（或至少让后续迁移全部 `checkfirst=True` 且修正 0018+ 的重复建表），并在全新库跑通 `alembic upgrade head` 作为回归门禁。
3. 修复 35 个红测试：优先修 `v3_palette_versions.version` 的 NOT NULL/默认值问题与 manifest_compile fixture 的审批门禁；对 7 个超时类失败在用户本机复核是否是依赖版本问题。
4. 将 `run_r8_tests.py`/`run_r9_tests.py` 的用例合并进 pytest 套件，删除独立脚本。
5. 给 `fastapi`/`httpx`/`starlette` 加 `<=` 上限或 lock 文件，复现稳定测试环境。
6. 更新 `CLAUDE.md` 与核心四文档，纳入 V3/BigBanana/Gemini 三条线的现状。

---

## 九、附录

### 9.1 迁移链一览（0001–0032）

- 已提交（0001–0016）：M1 初始 / prompts / shares_audit / workflow_generation_type / resource_folders / generation_type_config / runtime / 短剧 foundation~soft_delete
- 未提交（0017–0032）：text_output_config / v3_director_workflow / v3_story_ledger / v3_scene_ledger / v3_style_bible / v3_anchors / v3_spatial_plans / v3_manifest_audit / v3_manifest_refs / v3_manifest_task_links / v3_director_chat_proposals / bigbanana_phase1 / gemini_image_provider / gemini_concurrency / gemini_size / remove_gemini_model_size

### 9.2 验证方法说明

- 后端测试：将 `backend/` 复制到 Linux 原生文件系统（避开挂载盘 sqlite I/O 问题），新建 Python 3.10 venv 安装依赖后运行 `pytest`。
- 迁移验证：在全新 sqlite 上执行 `alembic upgrade head`。
- 前端：`vue-tsc --noEmit` 通过；`vite build` 因缺 Linux 版 rollup 二进制未能在本环境完成，以 8/29 的 `dist/` 产物佐证本机可构建。
- 版本控制：`git status` / `git diff --stat` / `git log`。

> 注：本报告为 2026-08-29 时间点快照。由于工作区存在大量未提交改动，具体行号与状态可能随后续提交变化。
