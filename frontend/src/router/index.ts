import { createRouter, createWebHistory } from 'vue-router'
import { getAccessToken } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { isV2Enabled, preferV2 } from '@/v2/app/featureFlags'
import { v2Routes } from '@/v2/routes'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
    },
    {
      path: '/',
      component: () => import('@/views/LayoutView.vue'),
      children: [
        { path: '', redirect: () => (preferV2() ? { name: 'v2-home' } : { name: 'home' }) },
        { path: 'v1', name: 'home', component: () => import('@/views/HomeView.vue') },
        { path: 'gen/:code', name: 'generate', component: () => import('@/views/GenerateView.vue') },
        { path: 'wf/:code', name: 'workflow-by-type', component: () => import('@/views/WorkflowManageView.vue') },
        { path: 'tasks', name: 'tasks', component: () => import('@/views/TaskBoardView.vue') },
        { path: 'resources', name: 'resources', component: () => import('@/views/ResourceLibraryView.vue') },
        { path: 'workflows', name: 'workflows', component: () => import('@/views/WorkflowManageView.vue') },
        { path: 'prompts', name: 'prompts', component: () => import('@/views/PromptLibraryView.vue') },
        { path: 'nodes', name: 'nodes', component: () => import('@/views/NodeManageView.vue') },
        { path: 'audit', name: 'audit', component: () => import('@/views/AuditLogView.vue') },
        { path: 'recycle', name: 'recycle', component: () => import('@/views/RecycleBinView.vue') },
        { path: 'settings', name: 'settings', component: () => import('@/views/SettingsView.vue') },
        { path: 'videos', name: 'videos', component: () => import('@/views/VideoReferenceView.vue') },
      ],
    },
    {
      path: '/s/:token',
      name: 'share',
      component: () => import('@/views/ShareView.vue'),
    },
    v2Routes,
  ],
})

router.beforeEach(async (to) => {
  if (to.name === 'login') return true
  if (!getAccessToken()) return { name: 'login' }
  if (to.matched.some((record) => record.meta.requiresV2) && !isV2Enabled()) {
    return { name: 'home' }
  }
  if (to.matched.some((record) => record.meta.adminOnly) && getAccessToken()) {
    const auth = useAuthStore()
    if (!auth.user) await auth.fetchMe()
    if (auth.user?.role !== 'admin') return { name: 'v2-home' }
  }
  return true
})

export default router
