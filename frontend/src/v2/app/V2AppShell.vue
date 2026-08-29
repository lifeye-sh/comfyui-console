<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import { genTypeApi } from '@/api/modules'
import { useAuthStore } from '@/stores/auth'
import { disconnectWs } from '@/ws/client'
import GlassDrawer from '@/v2/components/GlassDrawer.vue'
import V2Button from '@/v2/components/V2Button.vue'
import { buildV2Menu, filterV2Menu, type GenerationMenu, type V2MenuItem } from '@/v2/app/menu'
import { setUiPreference } from '@/v2/app/featureFlags'
import '@/v2/styles/base.css'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const collapsed = ref(localStorage.getItem('v2-sidebar-collapsed') === 'true')
const expanded = ref(new Set(['drama', 'creation', 'creation-image', 'tasks', 'assets']))
const generationMenu = ref<Partial<GenerationMenu>>({})
const mobileGenerationOpen = ref(false)
const profileOpen = ref(false)
const dramaWorkspace = computed(() =>
  /^\/v2\/drama\/projects\/\d+\/episodes\/\d+\/(script|manifest)$/.test(route.path)
  || /^\/v2\/drama\/projects\/\d+\/(assets|storyboard|production)$/.test(route.path),
)

const menu = computed(() => filterV2Menu(buildV2Menu(generationMenu.value), auth.user?.role))
const generationItems = computed(() => menu.value.find((item) => item.key === 'creation')?.children || [])
const currentLabel = computed(() => {
  for (const item of menu.value) {
    if (item.to === route.path) return item.label
    const child = item.children?.find((entry) => entry.to === route.path || (entry.to && route.path.startsWith(entry.to)))
    if (child) return child.label
    for (const group of item.children || []) { const nested=group.children?.find(entry=>entry.to===route.path||(entry.to&&route.path.startsWith(entry.to)));if(nested)return nested.label }
  }
  return String(route.meta.title || '系统概览')
})

onMounted(async () => {
  try { generationMenu.value = await genTypeApi.menu() } catch { generationMenu.value = {} }
})

function toggleSidebar() {
  collapsed.value = !collapsed.value
  localStorage.setItem('v2-sidebar-collapsed', String(collapsed.value))
}
function toggleGroup(key: string) {
  const next = new Set(expanded.value)
  next.has(key) ? next.delete(key) : next.add(key)
  expanded.value = next
}
function navigate(item: V2MenuItem) {
  if (item.to) router.push(item.to)
  else if (item.children?.length) toggleGroup(item.key)
}
function backToV1() { setUiPreference('v1'); router.push('/v1') }
function logout() { disconnectWs(); auth.logout(); router.push('/login') }
</script>

<template>
  <div class="v2-app v2-theme" :class="{ 'sidebar-collapsed': collapsed, 'drama-workspace': dramaWorkspace }">
    <div class="ambient ambient-one" /><div class="ambient ambient-two" />
    <aside class="desktop-sidebar" aria-label="V2 主导航">
      <div class="brand"><span class="brand-mark">C</span><div class="brand-copy"><strong>Comfy Console</strong><small>CREATIVE OS · V2</small></div></div>
      <nav class="side-nav">
        <div v-for="item in menu" :key="item.key" class="nav-section">
          <button class="nav-item" :class="{ active: item.to === route.path }" :title="collapsed ? item.label : undefined" @click="navigate(item)">
            <span class="nav-icon">{{ item.icon }}</span><span class="nav-label">{{ item.label }}</span><span v-if="item.children" class="nav-caret" :class="{ open: expanded.has(item.key) }">⌄</span>
          </button>
          <div v-if="item.children && expanded.has(item.key) && !collapsed" class="nav-children">
            <template v-for="child in item.children" :key="child.key"><button :disabled="!child.to&&!child.children" :class="{ active: child.to === route.path, 'category-button': child.children }" @click="navigate(child)"><span>{{ child.icon }}</span>{{ child.label }}<i v-if="child.children">⌄</i></button><div v-if="child.children&&expanded.has(child.key)" class="nav-grandchildren"><button v-for="entry in child.children" :key="entry.key" :class="{active:entry.to===route.path}" @click="navigate(entry)">{{ entry.label }}</button></div></template>
          </div>
        </div>
      </nav>
      <div class="sidebar-foot"><button class="nav-item" title="折叠侧栏" @click="toggleSidebar"><span class="nav-icon">⇤</span><span class="nav-label">折叠侧栏</span></button></div>
    </aside>

    <section class="app-stage">
      <header class="topbar">
        <div><small>COMFYUI CONSOLE / V2</small><strong>{{ currentLabel }}</strong></div>
        <div class="top-actions">
          <V2Button variant="ghost" @click="router.push('/v2/design-system')">组件规范</V2Button>
          <V2Button variant="ghost" @click="backToV1">切换旧版</V2Button>
          <button class="avatar-button" :aria-expanded="profileOpen" aria-label="打开用户菜单" @click="profileOpen = !profileOpen">{{ auth.user?.username?.slice(0, 1)?.toUpperCase() || 'U' }}</button>
          <div v-if="profileOpen" class="profile-menu"><strong>{{ auth.user?.username }}</strong><small>{{ auth.user?.role === 'admin' ? '管理员' : '普通用户' }}</small><button @click="logout">退出登录</button></div>
        </div>
      </header>
      <main class="content"><RouterView /></main>
    </section>

    <header class="mobile-header"><div><small>COMFY CONSOLE V2</small><strong>{{ currentLabel }}</strong></div><button class="avatar-button" @click="profileOpen = !profileOpen">{{ auth.user?.username?.slice(0, 1)?.toUpperCase() || 'U' }}</button></header>
    <nav class="mobile-tabs" aria-label="移动端主导航">
      <button :class="{ active: route.path === '/v2' }" @click="router.push('/v2')"><span>⌂</span>概览</button>
      <button @click="mobileGenerationOpen = true"><span>✦</span>生成</button>
      <button :class="{ active: route.path.startsWith('/v2/tasks') }" @click="router.push('/v2/tasks')"><span>☷</span>任务</button>
      <button :class="{ active: route.path.startsWith('/v2/assets') }" @click="router.push('/v2/assets')"><span>◇</span>素材</button>
      <button :class="{ active: profileOpen }" @click="profileOpen = !profileOpen"><span>○</span>我的</button>
    </nav>
    <div v-if="profileOpen" class="mobile-profile"><strong>{{ auth.user?.username }}</strong><span>{{ auth.user?.role === 'admin' ? '管理员' : '普通用户' }}</span><button @click="router.push('/v2/design-system'); profileOpen = false">组件规范</button><button @click="backToV1">切换旧版</button><button @click="logout">退出登录</button></div>
    <GlassDrawer :open="mobileGenerationOpen" title="选择生成类型" @close="mobileGenerationOpen = false">
      <div class="generation-list"><section v-for="group in generationItems" :key="group.key"><h3>{{ group.label }}</h3><button v-for="item in group.children||[]" :key="item.key" :disabled="!item.to" @click="item.to && router.push(item.to); mobileGenerationOpen = false"><span>{{ group.icon }}</span><div><strong>{{ item.label }}</strong><small>创建新的生成任务</small></div><b>›</b></button></section></div>
    </GlassDrawer>
  </div>
</template>

<style scoped>
.v2-app { min-height:100vh; position:relative; overflow-x:hidden; background:var(--v2-bg); }
.ambient { position:fixed; width:520px; height:520px; border-radius:50%; filter:blur(15px); pointer-events:none; opacity:.22; }.ambient-one { left:-180px; bottom:-220px; background:#5368ff; }.ambient-two { right:-180px; top:-220px; background:#814fe7; }
.desktop-sidebar { position:fixed; inset:0 auto 0 0; z-index:20; width:var(--v2-sidebar-width); display:flex; flex-direction:column; background:rgba(11,25,48,.76); border-right:1px solid var(--v2-border); backdrop-filter:blur(var(--v2-blur)); transition:width .2s ease; }
.brand { height:var(--v2-topbar-height); padding:0 20px; display:flex; align-items:center; gap:12px; border-bottom:1px solid var(--v2-border); overflow:hidden; }.brand-mark { width:38px; min-width:38px; height:38px; display:grid; place-items:center; font-weight:800; background:linear-gradient(135deg,#8196ff,#965ee8); border-radius:12px; box-shadow:0 8px 22px rgba(101,119,245,.35); }.brand-copy { display:grid; white-space:nowrap; }.brand-copy strong { font-size:14px; }.brand-copy small,.topbar small,.mobile-header small { color:var(--v2-text-subtle); font-size:10px; letter-spacing:.1em; }
.side-nav { flex:1; overflow:auto; padding:14px 10px; }.nav-section { margin-bottom:3px; }.nav-item { width:100%; min-height:44px; padding:0 12px; display:flex; align-items:center; gap:12px; color:var(--v2-text-muted); background:transparent; border:1px solid transparent; border-radius:12px; cursor:pointer; text-align:left; }.nav-item:hover,.nav-item.active { color:var(--v2-text); background:var(--v2-surface-soft); border-color:var(--v2-border); }.nav-icon { width:24px; min-width:24px; text-align:center; font-size:18px; }.nav-label { flex:1; white-space:nowrap; }.nav-caret { transition:transform .2s; }.nav-caret.open { transform:rotate(180deg); }.nav-children { margin:3px 0 8px 48px; display:grid; gap:2px; }.nav-children button { min-height:34px; padding:0 10px; color:var(--v2-text-subtle); background:transparent; border:0; border-radius:8px; cursor:pointer; text-align:left; }.nav-children button:hover,.nav-children button.active { color:var(--v2-text); background:var(--v2-surface-soft); }.nav-children button:disabled { cursor:default; }.sidebar-foot { padding:10px; border-top:1px solid var(--v2-border); }
.app-stage { min-height:100vh; margin-left:var(--v2-sidebar-width); position:relative; transition:margin .2s ease; }.topbar { height:var(--v2-topbar-height); padding:0 24px; display:flex; align-items:center; justify-content:space-between; gap:16px; background:rgba(7,17,31,.58); border-bottom:1px solid var(--v2-border); backdrop-filter:blur(var(--v2-blur)); position:sticky; top:0; z-index:15; }.topbar > div:first-child { display:grid; gap:4px; }.top-actions { display:flex; align-items:center; gap:8px; position:relative; }.avatar-button { width:40px; height:40px; color:#fff; font-weight:700; background:linear-gradient(135deg,#6078f7,#895de8); border:1px solid rgba(255,255,255,.2); border-radius:12px; cursor:pointer; }.profile-menu { position:absolute; top:50px; right:0; width:190px; padding:16px; display:grid; gap:7px; background:var(--v2-surface-strong); border:1px solid var(--v2-border); border-radius:14px; box-shadow:var(--v2-shadow); backdrop-filter:blur(var(--v2-blur)); }.profile-menu small { color:var(--v2-text-muted); }.profile-menu button,.mobile-profile button { padding:9px 0; color:var(--v2-text-muted); background:transparent; border:0; border-top:1px solid var(--v2-border); cursor:pointer; text-align:left; }.content { padding:clamp(18px,3vw,36px); position:relative; z-index:1; }
.sidebar-collapsed .desktop-sidebar { width:var(--v2-sidebar-collapsed); }.sidebar-collapsed .app-stage { margin-left:var(--v2-sidebar-collapsed); }.sidebar-collapsed .brand-copy,.sidebar-collapsed .nav-label,.sidebar-collapsed .nav-caret { display:none; }.sidebar-collapsed .brand { padding:0 22px; }.sidebar-collapsed .nav-item { justify-content:center; padding:0; }.sidebar-collapsed .sidebar-foot .nav-icon { transform:rotate(180deg); }
.mobile-header,.mobile-tabs,.mobile-profile { display:none; }.category-button{display:flex!important;align-items:center;gap:7px!important;color:var(--v2-text-muted)!important}.category-button span{width:18px}.category-button i{margin-left:auto;font-style:normal}.nav-grandchildren{margin:0 0 5px 19px;padding-left:10px;display:grid;border-left:1px solid var(--v2-border)}.nav-grandchildren button{min-height:31px!important}.generation-list { display:grid; gap:16px; }.generation-list section{display:grid;gap:8px}.generation-list h3{margin:0;color:var(--v2-text-muted);font-size:13px}.generation-list button { min-height:68px; padding:12px 14px; display:flex; align-items:center; gap:14px; color:var(--v2-text); background:var(--v2-surface-soft); border:1px solid var(--v2-border); border-radius:14px; cursor:pointer; text-align:left; }.generation-list button > span { width:36px; height:36px; display:grid; place-items:center; background:rgba(130,149,255,.13); border-radius:10px; }.generation-list button div { flex:1; display:grid; gap:4px; }.generation-list small { color:var(--v2-text-muted); }
.drama-workspace>.desktop-sidebar,.drama-workspace>.app-stage>.topbar{display:none}.drama-workspace>.app-stage{margin-left:0}.drama-workspace>.app-stage>.content{padding:0}
@media (max-width: 760px) {
  .desktop-sidebar,.topbar { display:none; }.app-stage { margin:0; padding-top:64px; padding-bottom:76px; }.content { padding:16px 14px 24px; }.mobile-header { position:fixed; inset:0 0 auto 0; z-index:30; height:64px; padding:0 14px; display:flex; align-items:center; justify-content:space-between; background:rgba(7,17,31,.82); border-bottom:1px solid var(--v2-border); backdrop-filter:blur(var(--v2-blur)); }.mobile-header > div { display:grid; gap:3px; }.mobile-tabs { position:fixed; inset:auto 8px 8px; z-index:30; height:64px; padding:6px; display:grid; grid-template-columns:repeat(5,1fr); background:rgba(16,31,57,.9); border:1px solid var(--v2-border); border-radius:18px; box-shadow:var(--v2-shadow); backdrop-filter:blur(var(--v2-blur)); }.mobile-tabs button { display:grid; place-items:center; gap:1px; color:var(--v2-text-subtle); font-size:10px; background:transparent; border:0; border-radius:12px; cursor:pointer; }.mobile-tabs button span { font-size:18px; }.mobile-tabs button.active { color:var(--v2-text); background:rgba(130,149,255,.14); }.mobile-profile { position:fixed; right:14px; bottom:82px; z-index:35; width:210px; padding:16px; display:grid; gap:8px; background:var(--v2-surface-strong); border:1px solid var(--v2-border); border-radius:16px; box-shadow:var(--v2-shadow); backdrop-filter:blur(var(--v2-blur)); }.mobile-profile span { color:var(--v2-text-muted); font-size:12px; }
  .drama-workspace>.app-stage{padding:0}.drama-workspace>.mobile-header,.drama-workspace>.mobile-tabs{display:none}.drama-workspace>.app-stage>.content{padding:0}
}
</style>
