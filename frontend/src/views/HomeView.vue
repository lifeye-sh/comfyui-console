<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NCard, NProgress, NSpin, NTag, useMessage, type TagProps } from 'naive-ui'
import { dashboardApi, genTypeApi } from '@/api/modules'
import { connectWs, onWsEvent } from '@/ws/client'
import { getAccessToken } from '@/api/client'

const router = useRouter()
const message = useMessage()
const loading = ref(false)
const summary = ref<any>(null)
const generationMenu = ref<Record<string, any[]>>({})
let off: (() => void) | null = null
let reloadTimer: ReturnType<typeof setTimeout> | null = null

const emptySummary = {
  generated_at: '',
  tasks: { total: 0, today: 0, active: 0, success: 0, failed: 0, success_rate: 0, status_counts: {} },
  nodes: { total: 0, online: 0, capacity: 0, items: [] },
  resources: { total: 0, image: 0, video: 0, audio: 0 },
  workflows: { total: 0, generation_types: 0, configured_types: 0 },
  trend: [],
  recent_tasks: [],
}

const data = computed(() => summary.value || emptySummary)
const trendMax = computed(() => Math.max(1, ...data.value.trend.map((item: any) => item.total)))
const configuredPercent = computed(() => data.value.workflows.generation_types
  ? Math.round(data.value.workflows.configured_types * 100 / data.value.workflows.generation_types)
  : 0)
const quickTypes = computed(() => [
  ...(generationMenu.value.image || []),
  ...(generationMenu.value.video || []),
  ...(generationMenu.value.audio || []),
].slice(0, 8))

const statusMeta: Record<string, { label: string; color: string; type: TagProps['type'] }> = {
  DRAFT: { label: '草稿', color: '#94a3b8', type: 'default' },
  PENDING: { label: '等待', color: '#f59e0b', type: 'warning' },
  DISPATCHING: { label: '分配', color: '#8b5cf6', type: 'info' },
  QUEUED: { label: '排队', color: '#6366f1', type: 'info' },
  RUNNING: { label: '运行', color: '#2563eb', type: 'info' },
  FINALIZING: { label: '回收', color: '#06b6d4', type: 'info' },
  SUCCESS: { label: '成功', color: '#16a34a', type: 'success' },
  FAILED: { label: '失败', color: '#ef4444', type: 'error' },
  CANCELLED: { label: '取消', color: '#64748b', type: 'default' },
}

async function load(showSpinner = true) {
  if (showSpinner) loading.value = true
  try {
    const [dashboard, menu] = await Promise.all([
      dashboardApi.summary(),
      genTypeApi.menu(),
    ])
    summary.value = dashboard
    generationMenu.value = menu
  } catch {
    message.error('Dashboard 数据加载失败')
  } finally {
    loading.value = false
  }
}

function scheduleReload() {
  if (reloadTimer) clearTimeout(reloadTimer)
  reloadTimer = setTimeout(() => void load(false), 500)
}

function statusCount(status: string) {
  return Number(data.value.tasks.status_counts?.[status] || 0)
}

function statusPercent(status: string) {
  return data.value.tasks.today ? Math.round(statusCount(status) * 100 / data.value.tasks.today) : 0
}

function formatTime(value: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function copyPrompt(text: string, e: Event) {
  const target = e.currentTarget as HTMLElement
  navigator.clipboard?.writeText(text).then(() => {
    const original = target.textContent
    target.textContent = '✓'
    setTimeout(() => { target.textContent = original }, 1500)
  }).catch(() => {})
}

function shortDay(value: string) {
  const date = new Date(`${value}T00:00:00`)
  return `${date.getMonth() + 1}/${date.getDate()}`
}

onMounted(async () => {
  await load()
  if (getAccessToken()) connectWs()
  off = onWsEvent(scheduleReload)
})

onUnmounted(() => {
  off?.()
  if (reloadTimer) clearTimeout(reloadTimer)
})
</script>

<template>
  <NSpin :show="loading">
    <div class="dashboard space-y-5">
      <section class="hero">
        <div>
          <div class="eyebrow">SYSTEM OVERVIEW</div>
          <h1>系统 Dashboard</h1>
          <p>任务调度、节点容量、工作流与素材资产的实时概览</p>
        </div>
        <div class="hero-actions">
          <span class="updated">更新于 {{ formatTime(data.generated_at) }}</span>
          <NButton type="primary" :loading="loading" @click="load()">刷新数据</NButton>
        </div>
      </section>

      <section class="metric-grid">
        <button class="metric-card green" @click="router.push('/tasks')">
          <span class="metric-icon">今</span>
          <span class="metric-content"><b>{{ data.tasks.today }}</b><small>今日任务</small></span>
          <span class="metric-foot">累计 {{ data.tasks.total }} 项</span>
        </button>
        <button class="metric-card blue" @click="router.push('/tasks')">
          <span class="metric-icon">队</span>
          <span class="metric-content"><b>{{ data.tasks.active }}</b><small>正在处理</small></span>
          <span class="metric-foot">实时任务队列</span>
        </button>
        <button class="metric-card violet" @click="router.push('/nodes')">
          <span class="metric-icon">点</span>
          <span class="metric-content"><b>{{ data.nodes.online }}/{{ data.nodes.total }}</b><small>在线节点</small></span>
          <span class="metric-foot">并发容量 {{ data.nodes.capacity }}</span>
        </button>
        <button class="metric-card amber" @click="router.push('/resources')">
          <span class="metric-icon">材</span>
          <span class="metric-content"><b>{{ data.resources.total }}</b><small>素材资产</small></span>
          <span class="metric-foot">图 {{ data.resources.image }} · 视频 {{ data.resources.video }} · 音频 {{ data.resources.audio }}</span>
        </button>
      </section>

      <section class="dashboard-grid">
        <NCard title="近 7 日任务趋势" size="small" class="trend-card">
          <template #header-extra>
            <span class="success-rate">今日成功率 {{ data.tasks.success_rate }}%</span>
          </template>
          <div class="trend-chart">
            <div v-for="item in data.trend" :key="item.date" class="trend-column">
              <div class="trend-value">{{ item.total }}</div>
              <div class="bar-track">
                <div class="bar-success" :style="{ height: `${item.success / trendMax * 128}px` }" />
                <div class="bar-failed" :style="{ height: `${item.failed / trendMax * 128}px` }" />
                <div class="bar-total" :style="{ height: `${Math.max(3, (item.total - item.success - item.failed) / trendMax * 128)}px` }" />
              </div>
              <span>{{ shortDay(item.date) }}</span>
            </div>
          </div>
          <div class="legend"><span class="success-dot" />成功 <span class="failed-dot" />失败 <span class="other-dot" />处理中/其他</div>
        </NCard>

        <NCard title="今日任务状态" size="small">
          <div class="status-list">
            <div v-for="status in ['SUCCESS', 'RUNNING', 'PENDING', 'QUEUED', 'FAILED']" :key="status" class="status-row">
              <div class="status-label"><span :style="{ background: statusMeta[status].color }" />{{ statusMeta[status].label }}</div>
              <div class="status-bar"><i :style="{ width: `${statusPercent(status)}%`, background: statusMeta[status].color }" /></div>
              <b>{{ statusCount(status) }}</b>
            </div>
          </div>
          <div class="status-summary">
            <div><b>{{ data.tasks.success }}</b><span>成功</span></div>
            <div><b>{{ data.tasks.failed }}</b><span>失败</span></div>
            <div><b>{{ data.tasks.active }}</b><span>处理中</span></div>
          </div>
        </NCard>
      </section>

      <section class="dashboard-grid lower">
        <NCard title="计算节点" size="small">
          <template #header-extra><NButton text type="primary" @click="router.push('/nodes')">管理节点 →</NButton></template>
          <div v-if="data.nodes.items.length" class="node-list">
            <div v-for="node in data.nodes.items" :key="node.id" class="node-row">
              <span class="node-light" :class="node.status === 'online' ? 'online' : 'offline'" />
              <div><b>{{ node.name }}</b><small>最近在线 {{ formatTime(node.last_seen_at) }}</small></div>
              <NTag size="small" :type="node.status === 'online' ? 'success' : 'default'">{{ node.status === 'online' ? '在线' : '离线' }}</NTag>
              <span class="capacity">并发 {{ node.max_concurrent }}</span>
            </div>
          </div>
          <div v-else class="empty-state">尚未配置 ComfyUI 节点</div>
        </NCard>

        <NCard title="工作流就绪度" size="small">
          <div class="readiness">
            <NProgress type="circle" :percentage="configuredPercent" :stroke-width="10" />
            <div><b>{{ data.workflows.configured_types }}/{{ data.workflows.generation_types }}</b><span>生成类型已配置默认工作流</span></div>
          </div>
          <div class="workflow-stats">
            <div><span>有效工作流</span><b>{{ data.workflows.total }}</b></div>
            <div><span>生成类型</span><b>{{ data.workflows.generation_types }}</b></div>
          </div>
          <NButton block @click="router.push('/workflows')">查看工作流管理</NButton>
        </NCard>
      </section>

      <section class="dashboard-grid lower">
        <NCard title="最近任务" size="small">
          <template #header-extra><NButton text type="primary" @click="router.push('/tasks')">全部任务 →</NButton></template>
          <div class="recent-list">
            <div v-for="task in data.recent_tasks" :key="task.id" class="recent-row" @click="router.push('/tasks')">
              <NTag size="small" :type="statusMeta[task.status]?.type || 'default'">{{ statusMeta[task.status]?.label || task.status }}</NTag>
              <b>#{{ task.id }}</b>
              <span class="type-name">{{ task.generation_type_name }}</span>
              <span class="prompt">{{ task.prompt || '无提示词' }}</span>
              <button v-if="task.prompt" type="button" class="copy-btn-v1" @click.stop="copyPrompt(task.prompt, $event)">复制</button>
              <time>{{ formatTime(task.created_at) }}</time>
            </div>
            <div v-if="!data.recent_tasks.length" class="empty-state">暂无任务记录</div>
          </div>
        </NCard>

        <NCard title="快捷生成" size="small">
          <div class="quick-grid">
            <button v-for="item in quickTypes" :key="item.code" @click="router.push(`/gen/${item.code}`)">
              <span>{{ item.media_type === 'image' ? '图' : item.media_type === 'video' ? '视' : '音' }}</span>
              <b>{{ item.name }}</b>
              <small>{{ item.default_workflow_id ? '工作流已就绪' : '待配置工作流' }}</small>
            </button>
          </div>
          <div v-if="!quickTypes.length" class="empty-state">暂无启用的生成类型</div>
        </NCard>
      </section>
    </div>
  </NSpin>
</template>

<style scoped>
.dashboard { max-width: 1500px; margin: 0 auto; color: #172033; }
.hero { display: flex; justify-content: space-between; align-items: flex-end; gap: 24px; padding: 20px 24px; color: white; border-radius: 16px; background: radial-gradient(circle at 80% 0%, rgba(45,212,191,.3), transparent 30%), linear-gradient(120deg, #111827, #173b3a); box-shadow: 0 12px 30px rgba(15,23,42,.15); }
.eyebrow { font-size: 11px; letter-spacing: .18em; color: #5eead4; font-weight: 700; }
.hero h1 { margin: 4px 0; font-size: 28px; line-height: 1.2; }
.hero p { margin: 0; color: #cbd5e1; }
.hero-actions { display: flex; align-items: center; gap: 14px; }
.updated { color: #94a3b8; font-size: 12px; }
.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.metric-card { border: 1px solid #e5e7eb; border-radius: 14px; background: white; padding: 16px; display: grid; grid-template-columns: 48px 1fr; gap: 4px 13px; text-align: left; cursor: pointer; transition: .2s ease; }
.metric-card:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(15,23,42,.08); }
.metric-icon { grid-row: 1 / 3; width: 48px; height: 48px; display: grid; place-items: center; border-radius: 13px; font-weight: 800; }
.metric-content { display: flex; align-items: baseline; gap: 9px; }
.metric-content b { font-size: 25px; line-height: 1; }
.metric-content small, .metric-foot { color: #64748b; }
.metric-foot { font-size: 11px; }
.green .metric-icon { background: #dcfce7; color: #15803d; }.blue .metric-icon { background: #dbeafe; color: #1d4ed8; }.violet .metric-icon { background: #ede9fe; color: #6d28d9; }.amber .metric-icon { background: #fef3c7; color: #b45309; }
.dashboard-grid { display: grid; grid-template-columns: minmax(0, 1.65fr) minmax(300px, .85fr); gap: 14px; }
.dashboard-grid.lower { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.success-rate { color: #15803d; font-size: 12px; font-weight: 600; }
.trend-chart { height: 190px; display: grid; grid-template-columns: repeat(7, 1fr); align-items: end; gap: 12px; padding: 12px 8px 0; border-bottom: 1px solid #e5e7eb; background: repeating-linear-gradient(to bottom, transparent 0, transparent 44px, #f1f5f9 45px); }
.trend-column { height: 178px; display: flex; flex-direction: column; justify-content: flex-end; align-items: center; gap: 5px; color: #64748b; font-size: 11px; }
.trend-value { color: #334155; font-weight: 700; }
.bar-track { height: 128px; width: min(38px, 70%); display: flex; flex-direction: column-reverse; border-radius: 6px 6px 0 0; overflow: hidden; background: #f1f5f9; }
.bar-track > div { min-height: 0; }.bar-success { background: #22c55e; }.bar-failed { background: #ef4444; }.bar-total { background: #93c5fd; }
.legend { display: flex; align-items: center; justify-content: center; gap: 6px; margin-top: 12px; color: #64748b; font-size: 11px; }
.legend span { width: 8px; height: 8px; border-radius: 50%; margin-left: 8px; }.success-dot { background: #22c55e; }.failed-dot { background: #ef4444; }.other-dot { background: #93c5fd; }
.status-list { display: grid; gap: 14px; padding-top: 8px; }.status-row { display: grid; grid-template-columns: 62px 1fr 30px; align-items: center; gap: 10px; }.status-label { display: flex; align-items: center; gap: 7px; font-size: 12px; }.status-label span { width: 8px; height: 8px; border-radius: 50%; }.status-bar { height: 7px; background: #f1f5f9; border-radius: 9px; overflow: hidden; }.status-bar i { display: block; height: 100%; border-radius: inherit; transition: width .3s; }.status-row b { text-align: right; }
.status-summary { display: grid; grid-template-columns: repeat(3, 1fr); margin-top: 22px; padding-top: 18px; border-top: 1px solid #eef2f7; }.status-summary div { display: flex; flex-direction: column; align-items: center; }.status-summary b { font-size: 20px; }.status-summary span { font-size: 11px; color: #64748b; }
.node-list, .recent-list { display: grid; gap: 3px; }.node-row { display: grid; grid-template-columns: 10px 1fr auto auto; gap: 10px; align-items: center; padding: 10px 4px; border-bottom: 1px solid #f1f5f9; }.node-light { width: 9px; height: 9px; border-radius: 50%; }.node-light.online { background: #22c55e; box-shadow: 0 0 0 4px #dcfce7; }.node-light.offline { background: #94a3b8; }.node-row div { display: flex; flex-direction: column; }.node-row small, .capacity { color: #64748b; font-size: 11px; }
.readiness { display: flex; align-items: center; justify-content: center; gap: 24px; padding: 10px; }.readiness div { display: flex; flex-direction: column; }.readiness b { font-size: 24px; }.readiness span { max-width: 170px; color: #64748b; font-size: 12px; }.workflow-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 8px 0 14px; }.workflow-stats div { padding: 10px; background: #f8fafc; border-radius: 8px; display: flex; justify-content: space-between; }
.recent-row { display: grid; grid-template-columns: 55px 48px 100px minmax(80px, 1fr) auto 145px; align-items: center; gap: 8px; padding: 9px 3px; border-bottom: 1px solid #f1f5f9; cursor: pointer; }.recent-row:hover { background: #f8fafc; }.type-name, .recent-row time { color: #64748b; font-size: 12px; }.prompt { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }.recent-row time { text-align: right; }.copy-btn-v1 { flex-shrink: 0; padding: 1px 6px; font-size: 11px; color: #94a3b8; background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 4px; cursor: pointer; white-space: nowrap; }.copy-btn-v1:hover { color: #475569; border-color: #cbd5e1; }
.quick-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 9px; }.quick-grid button { display: grid; grid-template-columns: 34px 1fr; grid-template-rows: auto auto; gap: 1px 9px; text-align: left; border: 1px solid #e5e7eb; border-radius: 10px; padding: 10px; background: #fff; cursor: pointer; }.quick-grid button:hover { border-color: #14b8a6; background: #f0fdfa; }.quick-grid button > span { grid-row: 1 / 3; width: 34px; height: 34px; display: grid; place-items: center; border-radius: 9px; background: #ecfdf5; color: #047857; font-weight: 700; }.quick-grid small { color: #64748b; }.empty-state { padding: 32px; text-align: center; color: #94a3b8; }
@media (max-width: 1100px) { .metric-grid { grid-template-columns: repeat(2, 1fr); }.dashboard-grid, .dashboard-grid.lower { grid-template-columns: 1fr; } }
@media (max-width: 640px) { .hero { align-items: flex-start; flex-direction: column; padding: 17px; }.hero h1 { font-size: 23px; }.hero-actions { width: 100%; justify-content: space-between; }.metric-grid { grid-template-columns: 1fr; }.trend-chart { gap: 5px; }.recent-row { grid-template-columns: 55px 45px 1fr; }.recent-row .prompt, .recent-row time, .recent-row .copy-btn-v1 { display: none; }.quick-grid { grid-template-columns: 1fr; } }
</style>
