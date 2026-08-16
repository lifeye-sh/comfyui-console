<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { shortDramaApi, type ShortDramaProjectSummary } from '@/api/modules'
import GlassCard from '@/v2/components/GlassCard.vue'
import GlassPanel from '@/v2/components/GlassPanel.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'

const router = useRouter()
const items = ref<ShortDramaProjectSummary[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 12
const keyword = ref('')
const appliedKeyword = ref('')
const showDeleted = ref(false)
const loading = ref(false)
const error = ref('')
const moduleEnabled = ref(true)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const activeCount = computed(() => items.value.filter((item) => !item.deleted_at).length)

function formatDate(value: string) {
  return value ? new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '-'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const status = await shortDramaApi.status()
    moduleEnabled.value = status.enabled
    if (!status.enabled) { items.value = []; total.value = 0; return }
    const result = await shortDramaApi.projects({
      page: page.value,
      page_size: pageSize,
      keyword: appliedKeyword.value || undefined,
      include_deleted: showDeleted.value,
    })
    items.value = result.items
    total.value = result.total
  } catch (event: any) {
    error.value = event.response?.data?.message || '项目列表加载失败'
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  appliedKeyword.value = keyword.value.trim()
  void load()
}

async function remove(item: ShortDramaProjectSummary) {
  if (!window.confirm(`确定删除“${item.name}”吗？项目可以从已删除列表恢复。`)) return
  try { await shortDramaApi.deleteProject(item.id); await load() }
  catch (event: any) { error.value = event.response?.data?.message || '删除失败' }
}

async function restore(item: ShortDramaProjectSummary) {
  try { await shortDramaApi.restoreProject(item.id); await load() }
  catch (event: any) { error.value = event.response?.data?.message || '恢复失败' }
}

watch([page, showDeleted], () => void load())
onMounted(load)
</script>

<template>
  <div class="v2-page drama-page">
    <div class="v2-page-heading heading-row">
      <div><StatusBadge :tone="moduleEnabled ? 'success' : 'warning'">{{ moduleEnabled ? 'V2.1 项目工作台' : '模块已关闭' }}</StatusBadge><h1>短剧项目</h1><p>从创意、小说或剧本开始，统一管理角色、场景、分镜和生成结果。</p></div>
      <V2Button variant="primary" :disabled="!moduleEnabled" @click="router.push('/v2/drama/new')">新建短剧</V2Button>
    </div>

    <div class="metric-grid"><GlassCard><span>当前结果</span><strong>{{ total }}</strong><small>{{ showDeleted ? '已删除项目' : '符合查询条件' }}</small></GlassCard><GlassCard><span>当前页可用</span><strong>{{ activeCount }}</strong><small>共 {{ totalPages }} 页</small></GlassCard><GlassCard><span>制作入口</span><strong>4</strong><small>创意、大纲、剧本、小说</small></GlassCard></div>

    <GlassPanel title="全部项目" :description="showDeleted ? '可以恢复已删除项目' : '最近更新的项目优先'" class="project-panel">
      <template #actions><div class="filters"><input v-model="keyword" placeholder="搜索项目名称或简介" @keyup.enter="search"><V2Button variant="ghost" @click="search">查询</V2Button><button class="mode" :class="{active:showDeleted}" @click="showDeleted=!showDeleted;page=1">{{ showDeleted ? '返回项目' : '已删除' }}</button></div></template>
      <p v-if="error" class="error">{{ error }}</p>
      <div v-if="loading" class="state-box">正在加载项目…</div>
      <div v-else-if="!moduleEnabled" class="state-box"><strong>短剧模块当前已关闭</strong><p>设置前后端短剧功能开关后重新启动服务。</p></div>
      <div v-else-if="!items.length" class="state-box"><div class="empty-mark">▤</div><strong>{{ showDeleted ? '没有已删除项目' : '还没有短剧项目' }}</strong><p>{{ appliedKeyword ? '没有找到符合条件的项目。' : '创建项目后即可维护创作简报和进入后续剧本生产。' }}</p><V2Button v-if="!showDeleted&&!appliedKeyword" variant="primary" @click="router.push('/v2/drama/new')">创建第一个项目</V2Button></div>
      <div v-else class="project-grid"><article v-for="item in items" :key="item.id" class="project-card" @click="!item.deleted_at&&router.push(`/v2/drama/projects/${item.id}`)"><div class="cover">{{ item.name.slice(0,1) }}</div><div class="project-copy"><div class="project-title"><h3>{{ item.name }}</h3><StatusBadge :tone="item.deleted_at?'danger':item.status==='completed'?'success':'info'">{{ item.deleted_at?'已删除':item.status==='draft'?'草稿':item.status }}</StatusBadge></div><p>{{ item.synopsis || '暂无故事简介' }}</p><div class="stats"><span>{{ item.episode_count }} 集</span><span>{{ item.scene_count }} 场</span><span>{{ item.shot_count }} 镜头</span></div><footer><small>更新于 {{ formatDate(item.updated_at) }}</small><V2Button v-if="item.deleted_at" variant="ghost" @click.stop="restore(item)">恢复</V2Button><V2Button v-else variant="danger" @click.stop="remove(item)">删除</V2Button></footer></div></article></div>
      <div v-if="totalPages>1" class="pager"><V2Button variant="ghost" :disabled="page<=1" @click="page--">上一页</V2Button><span>第 {{ page }} / {{ totalPages }} 页</span><V2Button variant="ghost" :disabled="page>=totalPages" @click="page++">下一页</V2Button></div>
    </GlassPanel>
  </div>
</template>

<style scoped>
.heading-row{display:flex;align-items:flex-end;justify-content:space-between;gap:20px}.heading-row h1{margin-top:14px}.metric-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.metric-grid .glass-card{display:grid;gap:8px}.metric-grid span,.metric-grid small,.state-box p{color:var(--v2-text-muted)}.metric-grid strong{font-size:30px}.project-panel{margin-top:16px}.filters{display:flex;gap:8px}.filters input{width:240px;padding:0 12px;color:var(--v2-text);background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:10px}.mode{padding:0 12px;color:var(--v2-text-muted);background:transparent;border:1px solid var(--v2-border);border-radius:10px;cursor:pointer}.mode.active{color:var(--v2-danger);border-color:rgba(255,127,145,.4)}.error{padding:10px 12px;color:var(--v2-danger);background:rgba(255,127,145,.08);border-radius:10px}.state-box{min-height:280px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;text-align:center}.state-box p{max-width:520px;margin:0;line-height:1.7}.empty-mark{width:68px;height:68px;display:grid;place-items:center;border:1px solid var(--v2-border);border-radius:22px;background:var(--v2-surface-soft);font-size:30px}.project-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.project-card{padding:16px;display:grid;grid-template-columns:82px 1fr;gap:16px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:16px;cursor:pointer;transition:.2s}.project-card:hover{border-color:var(--v2-border-strong);transform:translateY(-2px)}.cover{height:108px;display:grid;place-items:center;border-radius:13px;background:linear-gradient(145deg,#566ff0,#895ee8);font-size:32px;font-weight:800}.project-copy{min-width:0;display:grid;gap:8px}.project-title{display:flex;align-items:center;justify-content:space-between;gap:8px}.project-title h3,.project-copy p{margin:0}.project-copy p{overflow:hidden;white-space:nowrap;text-overflow:ellipsis;color:var(--v2-text-muted)}.stats{display:flex;gap:8px}.stats span{padding:4px 8px;color:var(--v2-text-muted);background:rgba(255,255,255,.04);border-radius:8px;font-size:12px}.project-copy footer{display:flex;align-items:center;justify-content:space-between}.project-copy footer small{color:var(--v2-text-subtle)}.project-copy footer .v2-button{min-height:30px;padding:0 10px}.pager{padding-top:18px;display:flex;justify-content:center;align-items:center;gap:12px}.pager span{color:var(--v2-text-muted)}@media(max-width:900px){.project-grid{grid-template-columns:1fr}}@media(max-width:700px){.heading-row{align-items:flex-start;flex-direction:column}.heading-row>.v2-button{width:100%}.metric-grid{grid-template-columns:1fr}.filters{width:100%;flex-wrap:wrap}.filters input{width:100%;height:40px}.project-card{grid-template-columns:58px 1fr}.cover{height:76px}.project-panel :deep(.panel-head){align-items:flex-start;flex-direction:column}.project-panel :deep(.panel-actions){width:100%}}
</style>
