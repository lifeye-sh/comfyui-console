import { createRouter, createWebHistory } from 'vue-router'
import { getAccessToken } from '@/api/client'

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
        { path: '', name: 'home', component: () => import('@/views/HomeView.vue') },
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
  ],
})

router.beforeEach((to) => {
  if (to.name === 'login') return true
  if (!getAccessToken()) return { name: 'login' }
  return true
})

export default router
