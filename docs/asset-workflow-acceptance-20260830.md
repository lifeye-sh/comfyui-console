# 角色与场景工作流生图验收（2026-08-30）

## 修改

- 资产生成弹窗可选择 ComfyUI 生图类型及具体工作流版本，读取与外部生成页一致的 `/api/v2/generation-types/{id}/config`。
- 两个入口共用 `WorkflowParameterFields.vue`，按运行时参数定义呈现提示词、尺寸、单/多媒体、遮罩、选项、数值、种子及条件字段。
- 资产页支持参数方案、工作流参数缓存及兼容媒体迁移；只提交当前工作流可见参数，显式传递 `workflow_version_id`，保留角色/场景/道具/服装变体关联信息。
- 无可用工作流、加载失败及缺少必填输入时阻止提交；Gemini 保留独立输入和校验，不依赖 ComfyUI 工作流。
- 修复响应式数组默认值复制、媒体迁移重复占用和浅色弹窗字段对比度问题。
- 本次没有新增后端接口或数据库迁移，保留之前未提交的阶段一改动。

## 实际验证

1. `cd frontend; node --test tests/workflow-parameters.test.mjs`：6 项通过。
   覆盖响应式默认值、必填与条件字段、选中工作流参数过滤、遮罩、媒体迁移、数字选项、参考图数量上限及正向提示词识别。
2. `cd backend; .venv/Scripts/python -m pytest tests/test_generation_type_config_versions.py tests/test_generation_type_param_template_compat.py -q`：7 项通过，9 条既有依赖/测试密钥警告。
3. `cd frontend; npm run build`：vue-tsc 和 Vite 生产构建通过，最终 Vite 构建 20.07 秒。
4. Playwright 实际浏览器（隔离 SQLite、后端 18080、前端 14444）：
   - 角色弹窗：默认工作流、动态字段切换、提示词迁移、参数缓存、参数方案、条件必填、空多图输入拦截通过。
   - 捕获角色与场景提交：明确工作流版本 9001、对应 character/location 关联、数字选项保留为 number、隐藏及其他工作流字段不混入。
   - 切换生成类型到无工作流配置：禁止提交；切回 Gemini 保留提示词且可继续操作。
   - 外部生图页面：共享控件显示、条件必填校验、提交版本/选项和工作流切换通过。
   - 截图检查后修正字段标签和种子按钮在浅色弹窗中的对比度。

浏览器使用两套受控工作流配置，并在创建批次请求处拦截执行；验证了真实页面交互和请求内容，没有调用真实 ComfyUI/Gemini，没有验证 GPU 运行或最终图片质量，也没有修改用户业务数据库。

浏览器脚本及截图位于 `frontend/output/playwright/`：`setup-workflow.cjs`、`check-workflow.cjs`、`check-workflow-scene.cjs`、`check-workflow-external.cjs`；场景最终截图为 `asset-workflow-scene.png`。这些脚本依赖已登录的隔离验收页和对应角色/场景测试数据。

## 参考图选择返回不显示：补充修复

根因：共享参数表单连续接收图片 ID 更新和清空遮罩事件时，两次都从尚未刷新的 props 复制参数，第二次更新覆盖了新图片 ID。改为累计合并本轮已发出的参数，并在父级切换工作流/参数时同步基准值。

- 新增 `frontend/tests/workflow-fields.test.mjs`，编译实际 Vue 组件，以真实 Vue 父子更新周期验证单图、多图选择和清除。修复前 2 项均因图片 ID 被恢复为旧值而失败；修复后通过。连同参数测试共 8 项通过。
- 浏览器实际操作素材选择器：单张图返回显示缩略图；按 B、A 顺序选择两图后均显示，提交 `[9102,9101]`；移除一图、清除全部和场景参考图选择/提交均通过。缩略图还执行了 decode 和 naturalWidth 检查。
- 最终 `npm run build` 通过（含 vue-tsc；Vite 17.99 秒）。
- 使用隔离数据库和受控素材/工作流响应，批次提交被拦截，未触发实际生图。脚本 `frontend/output/playwright/check-reference-selection.cjs`；截图 `reference-selection-fixed.png`。
