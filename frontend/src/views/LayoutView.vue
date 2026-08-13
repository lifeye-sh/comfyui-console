<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter, RouterView } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { disconnectWs } from '@/ws/client'
import { genTypeApi } from '@/api/modules'
import { isV2Enabled } from '@/v2/app/featureFlags'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const v2Enabled = isV2Enabled()

const menuTree = ref<Record<string, any[]>>({})
const expanded = ref<Record<string, boolean>>({ image: true, video: true, audio: true })

onMounted(async () => {
  try {
    menuTree.value = await genTypeApi.menu()
  } catch {
    /* 菜单加载失败时只显示静态菜单 */
  }
})

const mediaLabel: Record<string, string> = { image: '图片生成', video: '视频生成', audio: '音频生成' }

const staticMenus = [
  { label: '任务管理', key: 'tasks' },
  { label: '素材库', key: 'resources' },
  { label: '提示词库', key: 'prompts' },
  { label: '参考视频', key: 'videos' },
  { label: '节点管理', key: 'nodes' },
  { label: '操作记录', key: 'audit' },
  { label: '回收站', key: 'recycle' },
  { label: '平台设置', key: 'settings' },
]

const activeKey = computed(() => {
  if (route.name === 'generate') return `gen-${route.params.code}`
  if (route.name === 'workflow-by-type') return `wf-${route.params.code}`
  return (route.name as string) || 'home'
})

const activeLabel = computed(() => {
  if (route.name === 'generate') {
    const code = route.params.code as string
    for (const arr of Object.values(menuTree.value)) {
      const t = arr.find((x) => x.code === code)
      if (t) return t.name
    }
    return '生成'
  }
  return staticMenus.find((m) => m.key === route.name)?.label || '首页'
})

function go(key: string) {
  if (key === 'home') router.push('/')
  else if (key.startsWith('gen-')) router.push(`/gen/${key.slice(4)}`)
  else if (key.startsWith('wf-')) router.push(`/wf/${key.slice(3)}`)
  else router.push({ name: key })
}

function toggle(media: string) {
  expanded.value[media] = !expanded.value[media]
}

function logout() {
  disconnectWs()
  auth.logout()
  router.push('/login')
}

const mobileTabs = [
  { label: '首页', key: 'home' },
  { label: '发布', key: 'publish' },
  { label: '任务', key: 'tasks' },
  { label: '素材', key: 'resources' },
  { label: '我的', key: 'mine' },
]

function goMobile(key: string) {
  if (key === 'home') router.push('/')
  else if (key === 'tasks') router.push('/tasks')
  else if (key === 'resources') router.push('/resources')
  else if (key === 'mine') router.push('/nodes')
  else if (key === 'publish') {
    const first =
      menuTree.value.image?.[0] || menuTree.value.video?.[0] || menuTree.value.audio?.[0]
    if (first) router.push(`/gen/${first.code}`)
    else router.push('/workflows')
  }
}
</script>

<template>
  <!-- 桌面端：左侧栏 + 主内容（纯 flex，无定位依赖） -->
  <div class="desktop-layout">
    <aside class="sider">
      <div class="brand">comfyui-console</div>
      <nav class="nav">
        <div class="menu-item" :class="{ active: activeKey === 'home' }" @click="go('home')">首页</div>

        <template v-for="media in ['image', 'video', 'audio']" :key="media">
          <template v-if="menuTree[media]?.length">
            <div class="menu-group" @click="toggle(media)">
              <span>{{ mediaLabel[media] }}</span>
              <span class="arrow">{{ expanded[media] ? '▾' : '▸' }}</span>
            </div>
            <template v-if="expanded[media]">
              <div
                v-for="t in menuTree[media]"
                :key="t.code"
                class="menu-item sub"
                :class="{ active: activeKey === `gen-${t.code}` }"
                @click="go(`gen-${t.code}`)"
              >
                {{ t.name }}
              </div>
            </template>
          </template>
        </template>

        <div
          v-for="m in staticMenus"
          :key="m.key"
          class="menu-item"
          :class="{ active: activeKey === m.key }"
          @click="go(m.key)"
        >
          {{ m.label }}
        </div>
      </nav>
      <div class="sider-footer">
        <div>
          <span class="user">{{ auth.user?.username }}（{{ auth.user?.role }}）</span>
          <button v-if="v2Enabled" class="v2-entry" @click="router.push('/v2')">体验 V2</button>
        </div>
        <button class="logout" @click="logout">退出</button>
      </div>
    </aside>
    <main class="main">
      <RouterView />
    </main>
  </div>

  <!-- 移动端：顶部标题 + 底部 Tab -->
  <div class="mobile-layout">
    <div class="mobile-header">
      <span>{{ activeLabel }}</span>
      <button v-if="v2Enabled" class="v2-entry mobile" @click="router.push('/v2')">V2</button>
    </div>
    <div class="mobile-content">
      <RouterView />
    </div>
    <div class="mobile-tabbar">
      <button
        v-for="m in mobileTabs"
        :key="m.key"
        class="tab"
        :class="{ active: activeLabel === m.label }"
        @click="goMobile(m.key)"
      >
        {{ m.label }}
      </button>
    </div>
  </div>
</template>

<style scoped>
/* 桌面端 */
.desktop-layout {
  display: flex;
  height: 100vh;
  background: #f5f5f5;
}
.sider {
  width: 220px;
  flex-shrink: 0;
  background: #fff;
  border-right: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
}
.brand {
  padding: 16px;
  font-weight: 700;
  font-size: 17px;
  border-bottom: 1px solid #f0f0f0;
}
.nav {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}
.menu-group {
  padding: 9px 16px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  color: #374151;
  display: flex;
  justify-content: space-between;
  align-items: center;
  user-select: none;
}
.menu-group:hover {
  background: #f3f4f6;
}
.menu-item {
  padding: 9px 16px;
  cursor: pointer;
  font-size: 14px;
  color: #374151;
  user-select: none;
}
.menu-item.sub {
  padding-left: 32px;
}
.menu-item.sub2 {
  padding-left: 44px;
  font-size: 13px;
  color: #6b7280;
}
.menu-item:hover {
  background: #f3f4f6;
}
.menu-item.active {
  color: #16a34a;
  background: #f0fdf4;
  border-right: 2px solid #16a34a;
  font-weight: 500;
}
.arrow {
  font-size: 11px;
  color: #9ca3af;
}
.sider-footer {
  padding: 12px 16px;
  border-top: 1px solid #f0f0f0;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.user {
  display: block;
  font-size: 12px;
  color: #6b7280;
}
.v2-entry {
  display: block;
  margin-top: 5px;
  padding: 0;
  color: #4f46e5;
  background: none;
  border: none;
  font-size: 12px;
  cursor: pointer;
}
.v2-entry.mobile { margin: 0; padding: 4px 8px; border: 1px solid #c7d2fe; border-radius: 8px; }
.logout {
  font-size: 12px;
  color: #ef4444;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
}
.logout:hover {
  text-decoration: underline;
}
.main {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

/* 移动端 */
.mobile-layout {
  display: none;
}
@media (max-width: 767px) {
  .desktop-layout {
    display: none;
  }
  .mobile-layout {
    display: flex;
    flex-direction: column;
    height: 100vh;
  }
  .mobile-header {
    padding: 12px;
    border-bottom: 1px solid #e5e7eb;
    font-weight: 700;
    background: #fff;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .mobile-content {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
  }
  .mobile-tabbar {
    display: flex;
    border-top: 1px solid #e5e7eb;
    background: #fff;
  }
  .tab {
    flex: 1;
    padding: 10px 0;
    font-size: 12px;
    color: #6b7280;
    background: none;
    border: none;
    cursor: pointer;
  }
  .tab.active {
    color: #16a34a;
    font-weight: 700;
  }
}
</style>
