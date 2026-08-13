import type { RouteRecordRaw } from 'vue-router'

export const v2Routes: RouteRecordRaw = {
  path: '/v2',
  component: () => import('@/v2/app/V2AppShell.vue'),
  meta: { requiresV2: true },
  children: [
    { path: '', name: 'v2-home', component: () => import('@/v2/features/dashboard/DashboardView.vue'), meta: { title: '系统概览' } },
    { path: 'design-system', name: 'v2-design-system', component: () => import('@/v2/features/design-system/DesignSystemView.vue'), meta: { title: '组件规范' } },
    { path: 'generate/:code', name: 'v2-generate', component: () => import('@/v2/features/generate/DynamicGenerateView.vue'), meta: { title: '创作生成' } },
    { path: 'tasks', name: 'v2-tasks', component: () => import('@/v2/features/tasks/TaskListView.vue'), meta: { title: '任务管理' } },
    { path: 'batches', name: 'v2-batches', component: () => import('@/v2/features/batches/BatchListView.vue'), meta: { title: '批次任务' } },
    { path: 'assets', name: 'v2-assets', component: () => import('@/v2/features/assets/AssetLibraryView.vue'), meta: { title: '素材库' } },
    { path: 'assets/picker', name: 'v2-asset-picker', component: () => import('@/v2/features/assets/AssetPickerDemoView.vue'), meta: { title: '素材选择器' } },
    { path: 'reference-videos', name: 'v2-reference-videos', component: () => import('@/v2/features/assets/ReferenceVideoView.vue'), meta: { title: '参考视频' } },
    { path: 'prompts', name: 'v2-prompts', component: () => import('@/v2/features/prompts/PromptLibraryView.vue'), meta: { title: '提示词库' } },
    { path: 'recycle-bin', name: 'v2-recycle', component: () => import('@/v2/features/assets/RecycleBinView.vue'), meta: { title: '回收站' } },
    { path: 'workflows', name: 'v2-workflows', component: () => import('@/views/WorkflowManageView.vue'), meta: { title: '工作流管理' } },
    { path: 'parameter-schemes', name: 'v2-schemes', component: () => import('@/v2/features/settings/ParameterSchemeView.vue'), meta: { title: '参数方案' } },
    { path: 'settings/generation-types', name: 'v2-generation-types', component: () => import('@/v2/features/generation-config/GenerationTypeListView.vue'), meta: { title: '生成类型配置', adminOnly: true } },
    { path: 'settings/generation-types/:id', name: 'v2-generation-type-editor', component: () => import('@/v2/features/generation-config/GenerationTypeConfigEditorView.vue'), meta: { title: '编辑生成类型', adminOnly: true } },
    { path: 'settings/nodes', name: 'v2-nodes', component: () => import('@/v2/features/runtime/RuntimeMonitorView.vue'), meta: { title: '运行监控', adminOnly: true } },
    { path: 'settings/users', name: 'v2-users', component: () => import('@/v2/features/settings/UserManagementView.vue'), meta: { title: '用户与权限', adminOnly: true } },
    { path: 'settings/system', name: 'v2-system-settings', component: () => import('@/views/SettingsView.vue'), meta: { title: '系统设置', adminOnly: true } },
    { path: 'settings/audit', name: 'v2-audit', component: () => import('@/v2/features/settings/AuditLogView.vue'), meta: { title: '审计日志', adminOnly: true } },
  ],
}
