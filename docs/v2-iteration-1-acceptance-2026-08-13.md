# V2 Iteration 1 验收记录（2026-08-13）

## 交付范围

- V2 独立设计令牌：颜色、间距、圆角、边框、阴影、模糊和布局尺寸。
- GlassCard、GlassPanel、GlassDrawer 玻璃容器组件。
- V2Button、V2Field、StatusBadge 通用控件。
- 桌面端可折叠侧栏、顶栏、用户菜单和稳定版返回入口。
- 移动端顶部栏、五项底部导航、生成类型抽屉和用户菜单。
- 动态生成类型菜单和 `admin/user` 角色权限裁剪。
- `/v2/design-system` 组件演示页。
- 业务页面占位路由；本轮没有迁移或修改 V1 业务数据。

## 响应式与可访问性

- `<= 760px` 切换为移动应用壳，覆盖 360px 手机宽度。
- 768px 及以上使用桌面应用壳；内容网格在 820px 以下降为单列。
- 内容区使用流式宽度和最大宽度，适配 1366px 与 1920px。
- 所有按钮、链接和表单提供 `:focus-visible` 焦点样式。
- 支持 `prefers-reduced-motion`，自动缩短动画。
- 支持 `prefers-reduced-transparency`，自动改为不透明表面并关闭模糊。

## 自动化验收

| 检查项 | 结果 |
| --- | --- |
| `npm run typecheck` | 通过 |
| V2 默认关闭的 `npm run build` | 通过 |
| `VITE_UI_V2_ENABLED=true` 的 `npm run build` | 通过 |
| 后端 `pytest -q` | 45 passed，1 个第三方弃用警告 |

## 权限与隔离结论

- `admin` 可以看到并访问“系统配置”菜单及路由。
- `user` 不显示系统配置；直接访问管理员 V2 路由会返回 V2 首页。
- V2 关闭时不显示入口，访问 `/v2` 返回 V1 首页。
- 本轮未修改后端接口、数据库结构和 V1 业务组件。
