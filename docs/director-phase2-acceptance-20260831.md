# 导演工作台第二阶段开发与验收

日期：2026-08-31。

## 本次交付

入口：项目壳 → 导演工作台，路由 `/v2/drama/projects/:projectId/episodes/:episodeId/director`。角色与场景页的继续入口同步指向新工作台，保留所选分集。

- **镜头总览**：场次/状态筛选、镜头卡片、首尾帧采用状态、视频采用状态、依赖更新提醒、选中镜头的批量视频预检与提交。
- **镜头制作**：视频预览与关键帧输入在同一页面。首帧、尾帧及中间规划帧分别编辑、生成、从素材库选择；候选可放大、并排对比和人工采用。
- 图片与视频分别选择 ComfyUI 生成类型、工作流版本，并复用外层动态参数组件和素材选择器。切换工作流保留当前页面的各自参数；切换镜头/帧不串用表单。
- 通过明确的参数用途绑定填写提示词、首尾帧、角色造型、场景、道具、时长与画幅。绑定保存到项目设置，不改写公共工作流。刷新用途参数会重新填写已绑定字段，其他手动参数保留。
- 保存服务端草稿，使用版本号检测并发修改；离开页面时保存，未保存内容关闭页面时提示。候选和任务保存在数据库，刷新可恢复。
- 任务复用平台 Batch / Task / ShotTaskLink / Take 链路，支持预检、幂等提交、状态查看、取消、原参数重试及产物补偿同步。
- 候选不会自动采用。首帧、尾帧、中间帧与视频各有独立采用位置；采用新首帧不清除尾帧或已采用视频。
- 原对白保持只读，不自动删改。对白时长超预算和未确认音频能力只给出提示，不把通用镜头固定限制为 15 秒。

## 修复的阻塞问题

1. 新工作台路由仍被旧分镜入口绕过：统一项目壳及资产页的分集导演入口。
2. 旧 Take 唯一约束限制每镜只能采用一个产物：增加 `scope` 与分位置唯一索引。
3. 重复采用同一候选可能被批量清空：采用变为幂等操作，增加镜头版本保护；旧取消采用接口同步清除帧引用。
4. 动态表单的 `__size` 等 UI 字段混入 API：复用公共参数清理，只提交选中工作流的可见字段。
5. 多参考图到共享队列时按单个 ID 转换而失败：明确列表输入按选择顺序上传；单图节点、隐式字符串编码或多图单遮罩不被当作已支持能力。
6. 多个角色参考遇到单图参数时静默丢失：预检要求明确选择图片或使用多图工作流。
7. 预检后镜头、资产或工作流绑定变化：预检指纹覆盖来源、工作流契约和最终参数，过期提交返回冲突。
8. 工作流切换与连续保存可能丢失输入：增加分工作流参数缓存、帧组件隔离和保存请求合并。

## 实际验证

### 自动回归

从仓库根目录执行：

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_director_workspace.py backend/tests/test_short_drama_production.py backend/tests/test_short_drama_models.py backend/tests/test_dispatcher_responsiveness.py backend/tests/test_migration_acceptance.py backend/tests/test_phase1_director_contract.py -q
node.exe --test frontend/tests/*.test.mjs
npm.cmd --prefix frontend run build
```

结果：后端 **36 passed**；前端 **9 passed**；`vue-tsc --noEmit` 与 Vite production build 通过。`git diff --check` 通过（现有文件有 Git CRLF 提示）。

新增后端回归覆盖草稿并发冲突、首尾/视频独立采用、重复采用、预检和幂等提交、重复同步、多输出候选、资产访问权限、造型参考优先级、图片任务作用域、旧取消采用兼容、工作流绑定变化、依赖过期与真实上传函数的多图顺序。新增前端回归使用实际 Vue SFC，验证工作流切换后恢复手动提示词和参考图，不混入另一工作流字段。

迁移测试从全新 SQLite 开始，验证中间版本启动不越过 Alembic、升级至 `0034`、外键检查及现有数据保留；采用回归在迁移后的真实 SQLite 上验证多位置唯一约束。

### 浏览器验收

Playwright 操作独立前端 `127.0.0.1:14445` 与独立后端 `127.0.0.1:18081`。使用全新测试数据库与测试账户，关闭后台调度，不调用真实 GPU 或外部付费模型。

已实际操作并通过：

1. 登录 → 分集镜头总览 → 合并制作视图。
2. 分别选择图片/视频工作流与首尾帧模式。
3. 缺少首尾帧时显示两项错误，提交按钮不可用。
4. 从素材库上传两张不同图片，返回后候选预览立即显示；分别采用首尾帧。
5. 视频预检显示真实首尾素材 ID；确认后进入平台队列。
6. 刷新后，草稿工作流、输入模式、采用图片和待执行任务仍然存在。
7. 使用本地合成 MP4 模拟输出注册，浏览器成功解码并播放；人工采用后总览显示采用版本。
8. 首帧图片提交到平台队列；任务可取消、按原参数重试。
9. 模拟图片输出后增加新候选，原首帧仍被采用；并排对比显示两张不同图片。
10. 最终后端重启后重新预检和提交成功；浏览器后退恢复上一制作视图。

截图与可重放操作脚本位于 `frontend/output/playwright/director-*`：

- `director-overview-verified.png`：总览采用状态。
- `director-production-final.png`：完成视频采用与图片候选的合并制作视图。
- `director-compare-verified.png`：候选图片并排对比。

浏览器控制台发现已有 favicon 404 和登录页密码框表单提示；未发现工作台接口或渲染错误。

## 数据库升级与边界

新增迁移 `0034_director_take_scopes.py`，依赖现有 `0033`。历史 Take 默认属于 `video`，不删除旧资源或候选。降级遇到一个镜头多个位置同时采用时拒绝执行，避免任意丢弃采用状态。

**现有业务数据库没有被本次验收修改。** 部署本次代码时，应先备份业务数据库，再在对应配置下运行：

```powershell
cd backend
.venv\Scripts\python.exe -m alembic upgrade head
```

随后重启后端并使用新前端。工作流需要是当前可用版本；没有语义用途的老工作流可在制作页绑定一次，或手动填写参数。

尚未验证真实 ComfyUI 节点推理成功率、耗时、模型画面质量或真实工作流输出能力。此次验证到平台队列、真实上传函数、产物同步及播放器；模拟媒体不代表模型生成效果。

中间关键帧目前用于画面规划与独立图片制作，不自动拼入首尾帧工作流。未加入全片剪辑、配音、自动音画同步和专用多关键帧视频协议。没有明确尾帧描述时保留待填写状态，不臆造动作终态。依赖更新提示采用保守判断，保留旧产物，不自动重新生成。


## 业务库缺列修复（2026-08-31）

用户报告 `no such column: drama_takes.scope` 后，确认当前业务库 `backend/data/app.db` 仍为 `0032`。此次已实际升级该业务库至 `0034`，替代上文验收时“业务库未修改”的状态。

先使用 SQLite backup API 生成 `backend/data/backups/app-before-0034-20260831-110414.db`，在独立副本上试升级成功后，再对业务库运行 Alembic upgrade head。升级前后 79 张业务表记录数一致，4 个已有 Take 保留，scope 字段存在，integrity_check 为 ok；镜头 76 的导演工作台服务查询成功。

数据库原有 23 条外键违规，副本及正式升级后与升级前完全一致，未新增；本次未删除或修补这些历史记录。


## 图片双服务补充（2026-08-31）

镜头首帧、尾帧和中间关键帧均支持 Gemini Image / ComfyUI。视频生成仍只支持 ComfyUI，服务端拒绝 Gemini 视频请求。

Gemini 表单使用现有图片提供方、系统维护尺寸及多参考图选择器，可一键填入本镜角色/场景/道具素材。切换服务保留各自的参数，选择和参数保存到镜头 JSON 草稿，因此无需新增数据库迁移。ComfyUI 图片继续使用原有工作流和动态表单。

Gemini 请求不依赖 ComfyUI 工作流，进入现有独立图片队列；完成后自动登记到对应帧候选，保留已采用版本。候选同步失败仍保持任务 SUCCESS，并使用公共补偿机制重试。没有修改外层资产自动采用行为。

最终相关回归：后端 44 passed，前端 12 passed，Vue 类型检查与 Vite build 通过。新增测试覆盖 Gemini 图片入队/产物登记/不自动采用、禁止视频、无效服务商/尺寸/素材拒绝、同步失败补偿，以及前端图片服务参数隔离和视频固定 ComfyUI。

浏览器已验证图片双服务表单切换、刷新恢复、Gemini 预检及任务提交，视频工作流始终保留。截图：`frontend/output/playwright/director-gemini-verified.png`。使用隔离数据库且关闭调度，测试调用使用模拟图片回包，未请求真实 Gemini 或 ComfyUI 生图。


## 视频输入去重、综合提示词回填与对白恢复（2026-08-31）

- 视频工作流通用表单隐藏图片/音频/视频选择器，以同位置的「工作流输入 · 来自已勾选的视频资源」区域替代；帧图片制作继续使用原通用输入。
- 综合提示词优先写入工作流绑定为 prompt 用途的文本字段，兼容 prompt/positive_prompt；不覆盖 video_prompt（视频动作与运镜）、负面提示词和其他参数。无正向提示词字段时明确提示；异步期间切换镜头或工作流不会误写当前草稿。
- 老清单镜头若 Shot.dialogue 为空，则读取 production_settings.dialogue_lines，保留说话人、逐句顺序和重复台词；显式编辑过的 Shot.dialogue 仍优先。对白恢复用于综合提示词、只读对白展示、时长提醒及版本依赖快照。旁白不冒充角色对白。
- 浏览器在隔离数据库实测：只存在一处媒体输入区；点击 AI 按钮后，工作流提示词含林舟和阿宁两句原对白；动作原文不变；保存刷新恢复正确；生成预检实际参数仍包含对白。未执行最终生成。
- 最终验证：前端 15 项通过，后端 20 项通过（43 条既有依赖/测试密钥警告），vue-tsc 与 Vite 生产构建通过（Vite 22.02 秒）。
- 浏览器脚本：frontend/output/playwright/director-input-prompt-verify.cjs；截图：director-input-prompt-verified.png。未修改业务数据库或调用真实生成服务。


## 勾选资源未进入任务工作流修复

- 自动输入资源池统一包含已启用的采用帧、角色、场景、道具及库素材，按勾选顺序去重分配。
- 语义绑定已有值优先；空的绑定输入可由勾选素材补齐。手动指定资源先占用，剩余资源填入可见空输入，多选遵守 max_items。
- 视频媒体输入的空数组、空值及旧的 0 自动值不再覆盖服务端自动填充。前端输入选项展示全部已勾选资源，勾选编号包含帧顺序。
- 实际验证：干净 SQLite 迁移至 0034；后端 director 两个测试文件 23 passed（49 条既有依赖/JWT 警告）；前端请求/工作流表单测试 10 passed；vue-tsc 与 Vite 生产构建通过（Vite 31.86s）。
- 新增集成用例经过保存草稿、compile、generate 创建 Task、Dispatcher._upload_inputs；断言图片列表顺序、音频和视频的节点文件路径，以及 TaskResource 关联。上传使用模拟 ComfyUI 和存储，不消耗 GPU，不修改业务数据或既有任务。
- 日志：backend/.test-tmp/checked-workflow-verified.log、checked-workflow-build.log。


## 标准视频参数、镜头标题与提示词来源编辑

- 视频标准标识：prompt、duration、size。duration 默认采用镜头总时长（兼容旧版额外 reaction_pause 和 V2 已包含停顿规则）；不再把综合提示词时长截断到 4～15 秒。size 根据工作流选项匹配 16:9 / 16:9 (Widescreen)、9:16 / 9:16 (Portrait Widescreen)，保留既有像素尺寸选项兼容。
- 镜头列表显示标题，溢出省略并通过 title 提示完整内容；已采用视频显示绿色边框，不再显示列表状态文字。新确认清单保存 title，旧清单从已确认版本按场景/镜头顺序读取标题。
- 删除旧视频动作与运镜输入框，新增 12 个来源字段及已启用资产描述编辑；保存至制作草稿，不改原始剧本或公共资产。综合提示词实际使用这些编辑，支持清空对白，并保留原中文运镜细节。来源也进入预检依赖快照。
- 验证：干净 SQLite 升级至 0034；后端 25 passed（53 条既有依赖/JWT 警告，41.44s）；前端 11 passed；vue-tsc / Vite 构建通过（28.08s）。
- Playwright 隔离页面验证：12 项来源可见、旧输入框数量 0；已采用边框 rgb(38,150,94)、ellipsis/title 正确；编辑画面与对白→AI 综合→工作流 prompt→保存→刷新保留通过。未发起实际视频生成。
- 日志：backend/.test-tmp/prompt-sources-verified.log、prompt-sources-build.log；截图：frontend/output/playwright/prompt-sources-acceptance.png。


## 拍摄清单对白未进入镜头制作修复（2026-09-01）

- 根因：confirm_manifest 在 `_analyze_manifest` 之前缓存 `scenes`，清单随后完成对白重新派生/拆镜，但正式 Scene/Shot 仍按分析前列表落库，造成清单 `dialogue_lines` 有值而镜头为空。
- 新确认路径改为只使用分析后的场景图创建 Scene/Shot。
- 历史兼容：当正式镜头对白为空时，导演工作台按已确认清单的场景/镜头顺序恢复 `dialogue_lines`，并用于只读对白、提示词来源、AI 综合、预检快照与对白时长警告。未批量改写业务数据。
- 旧制作草稿中的无标记空对白视为历史空值并恢复；前端从现在起记录 `prompt_input_overrides`，用户明确清空对白时保持为空。
- 当前 SQLite 只读核验：19 个具有可解析对白的镜头均能在制作草稿显示，all_visible_in_draft=true。
- 验证：后端清单/导演工作台 30 passed（62 条既有依赖/JWT 警告，66.28s）；前端 11 passed；vue-tsc + Vite build 通过（41.03s）。
- 日志：backend/.test-tmp/dialogue-link-verified.log、dialogue-link-frontend.log、dialogue-link-build.log。
