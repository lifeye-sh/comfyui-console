# 漫剧第一阶段集成验收 — 2026-08-30

## 结论

指定黄金路径的迁移、接口集成和浏览器交互验收通过。最终定向回归 **38 passed, 48 warnings in 63.35s**。前端 `npm.cmd run build`（vue-tsc + Vite）通过。此结论不代表全仓测试通过。

所有测试使用独立 SQLite 数据库；没有升级或清空现有业务数据库，没有提交 Git 改动。

## 实际覆盖

- 测试会话从不存在的 SQLite 文件执行 Alembic `upgrade head`，不再通过 `create_all` 掩盖迁移问题。
- 独立迁移测试执行 empty → 0010 → 0032 → 0033；旧版本启动不会提前建表/加字段；重复升级及启动不改变结构；已有账本记录保留；`foreign_key_check` 无异常。
- 真实 FastAPI 生命周期启动、种子初始化、登录和关闭通过。
- quick-create 返回 201；overview/screenplay/script/casting 返回 200；自动建立 number=1 的首集；初始场景/镜头计数和资产集合为空。
- 保存剧本，生成、编辑、确认清单；确认后聚合到 1 个角色、1 个基础造型、1 个场景资产、1 个道具；镜头绑定去重，总览场景/镜头数量与分镜一致。
- 解锁 → 复核 → 再确认 → 重复确认均成功，角色 ID 保持、造型和资产不重复；资产候选插入具有时间戳。
- 表情、旁白、构图和提示词覆盖字段在保存及确认后保留。
- 剧本、世界设定、分镜、制作及模拟 AI 分析/改编/单集生成相关回归通过。没有调用真实付费 AI 服务。

## 本次修复

1. `0001_initial.py` 原来引用当前 ORM 的全部 metadata，提前创建未来表，空库在 0018 因重复建表失败。改为从仓库基线 84ebc43 冻结的固定建表定义。
2. 0011、0012、0021 的直接外键 ALTER 不受 SQLite 支持，改为 Alembic batch 操作，保留外键。
3. 新增 0033：补齐第一阶段三张表及关联 V3 表的 created_at/updated_at 服务端默认值，修复生成清单、资产/绑定及剧本账本插入失败。表名单固定，不依赖动态 ORM。
4. `init_db()` 对 Alembic 已管理的库直接返回，兼容建表/补列逻辑仅保留给未版本化开发库。
5. 清单归一化不再无条件清空 action/expression/dialogue/narration/inner_monologue，兼容历史数据和原有接口调用。
6. 增强迁移及第一阶段回归；修正旧 AI 测试对提示词句式的过期匹配，并增加任务成功断言。

## 复跑

在 backend 目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_migration_acceptance.py tests/test_phase1_director_contract.py tests/test_short_drama_phase1.py tests/test_short_drama_projects.py tests/test_short_drama_world.py tests/test_short_drama_screenplay.py tests/test_short_drama_storyboard.py tests/test_short_drama_production.py tests/test_short_drama_ai.py -q
```

在 frontend 目录执行：

```powershell
npm.cmd run build
```

现有已正确迁移的部署库需要先备份，再运行 `python -m alembic upgrade head`。本次没有处理曾被旧 create_all 提前建表、或中途失败留下部分 DDL 的业务库；不能直接假定其能自动修复。

## 验证边界及其他失败

- 初次 browser 连接工具不可用，后续通过本机缓存的 Playwright CLI 完成真实浏览器验收。临时前后端运行于 14444/18080，连接独立迁移数据库；完成登录→新建项目→总览→第1集→保存剧本→生成清单→拆镜预览→确认应用（1镜头变2镜头）→确认到资产页→解锁→编辑小说式同段双对白→保存后两句分别显示。过程中发现的预览状态误显示“已确认”已修复。
- 扩展全仓测试曾运行得到 **136 passed, 16 failed, 13 errors**。其中 AI 模拟响应匹配已修复并在最终定向验收通过；修复后未再跑全仓，因此该数字是前一次全仓结果。
- 其余失败包括 V3 palette 测试夹具缺少必填 version（13 个 setup errors）、V3 清单未确认即编译、proposal 目标不存在，以及素材归档/时长选项断言。本次未改动这些范围外行为，不能宣称全仓通过。
- 定向验收 warning 主要为短 JWT 测试密钥及 Starlette/httpx/422 弃用提示。
- 原始日志保留在 `backend/.test-tmp/final-acceptance.log` 和 `backend/.test-tmp/full-regression.log`（忽略目录，不作为源码提交）。


## 规则、提示词与对白专项修改

- AI 分析入队时冻结剧本修订、编号来源行、项目简报、既有资产及版本、上集已确认摘要与模板正文；执行前后检查剧本修订。模拟模型请求验证使用冻结内容，没有调用真实收费模型。
- 分析提示词按事实→因果节拍→镜头→视觉设计组织，记录 explicit/inferred/designed 证据；允许空镜头、无道具及静止关键帧，不再强迫复制镜头凑数量。
- 清单 content 为对白的唯一编辑源。提取器支持角色冒号、对白前缀、Markdown、@角色块、括号语气、画外音、多行引文及小说式同段多轮对白。利用角色名单和语法上下文判断说话人；不确定者显示“说话人待确认”。排除明确的旁白、内心独白、字幕和音效；仍需人工判断未明确归属的引文是否真为对白。
- 真实清单只读抽查定位到旧规则的行首锚定导致整段漏提取；匿名化保留同类句式作回归，防止将听者当说话人、将动作句拼入姓名。未直接改写用户业务数据库。
- dialogue_lines 每次保存/读取清单时重新从原文派生，不使用陈旧缓存；评分未评估时返回 null，不填固定分。前端移除独立对白编辑框，展示后端派生结果、时长预算及未确定说话人。
- duration v2 包含反应时间；历史清单维持 duration+reaction 的读取语义。生产编译向上取整，清单和场景总预算采用同一计算。最长句检查不再将多句台词合计当作一句。
- prompt.effective 由 original+override 重新计算；生产提示词使用有效覆盖，保留对白、旁白与关键帧。
- 拆镜由后端生成原文分段预览，显示前后时长；应用需匹配 lock_version 和预览摘要。保留原始字符/来源区间，插入的说话人及配对引号单独记录。清空失效的镜头任务、提示词和关键帧。无标点时只能按字符提供临时切点，必须人工复核语义边界。
- 草稿允许保存；结构不完整和可确定的来源对白不一致阻止确认，创作建议不阻断。既有角色、环境和道具复用，清单确认不再覆写已建立资产。
- 前端保存失败或保存期间仍有新编辑时，不继续确认、复核或生成；预览期间禁止编辑，避免预览与原文脱节。

新增自动回归位于 `backend/tests/test_phase1_director_contract.py`（22项参数化用例）。浏览器对白断言脚本与截图位于 `frontend/output/playwright/`。

这批完成确定性规则、输入快照、提示词传递和安全编辑。完整语义七维诊断、多模型能力配置、跨集全部资产锁审核仍属于后续工作；本次没有将技能全文作为系统提示词直接灌入。
