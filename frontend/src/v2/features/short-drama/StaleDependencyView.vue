<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { shortDramaApi } from '@/api/modules'
import GlassPanel from '@/v2/components/GlassPanel.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'

const props = defineProps<{ projectId: number }>()

const dependencies = ref<any[]>([])
const staleRecords = ref<any[]>([])
const building = ref(false)
const resolvingId = ref<number | null>(null)
const error = ref('')

async function load() {
  error.value = ''
  try {
    const [deps, stale] = await Promise.all([
      shortDramaApi.directorDependencies(props.projectId),
      shortDramaApi.directorStaleRecords(props.projectId),
    ])
    dependencies.value = deps
    staleRecords.value = stale as any[]
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载依赖图失败'
  }
}

async function buildGraph() {
  building.value = true; error.value = ''
  try {
    await shortDramaApi.directorBuildDependencyGraph(props.projectId)
    await load()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '构建依赖图失败'
  } finally { building.value = false }
}

async function resolveStale(id: number) {
  const resolution = prompt('输入处理方式') || ''
  resolvingId.value = id; error.value = ''
  try {
    await shortDramaApi.directorResolveStale(props.projectId, id, { resolution })
    await load()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '处理失败'
  } finally { resolvingId.value = null }
}

const depTypeLabel: Record<string, string> = {
  style: '风格依赖',
  wardrobe: '服装依赖',
  spatial: '空间依赖',
  identity: '身份依赖',
}

const staleReasonLabel: Record<string, string> = {
  source_story_changed: '源故事变更',
  ledger_changed: '台账变更',
  style_changed: '风格变更',
  anchor_changed: '锚点变更',
  spatial_changed: '空间变更',
  manual: '手动标记',
}

// 构建上游 → 下游的树形结构
const depTree = computed(() => {
  const tree: Record<string, any[]> = {}
  for (const dep of dependencies.value) {
    const upstreamKey = `${dep.upstream_type}:${dep.upstream_ref}`
    ;(tree[upstreamKey] ??= []).push(dep)
  }
  return tree
})

onMounted(load)
watch(() => props.projectId, load)
</script>

<template>
  <GlassPanel title="依赖图与过期传播" description="确定性规则建立依赖边，上游变更自动标记下游资产过期。">
    <template #actions>
      <V2Button variant="primary" :disabled="building" @click="buildGraph">{{ building ? '构建中…' : '构建依赖图' }}</V2Button>
    </template>

    <div v-if="error" class="wb-error">{{ error }}</div>

    <!-- 依赖边 -->
    <div class="dep-section">
      <h4 class="section-title">依赖边（{{ dependencies.length }}）</h4>
      <div v-if="!dependencies.length" class="empty-tip">暂无依赖边。点击「构建依赖图」从已批准资产建立。</div>
      <div v-else class="dep-tree">
        <div v-for="(downstreams, upstreamKey) in depTree" :key="upstreamKey" class="dep-node">
          <div class="dep-upstream">
            <code>{{ upstreamKey }}</code>
          </div>
          <div class="dep-downstreams">
            <div v-for="d in downstreams" :key="d.id" class="dep-edge">
              <span class="dep-arrow">→</span>
              <code>{{ d.downstream_type }}:{{ d.downstream_ref }}</code>
              <small class="dep-type">{{ depTypeLabel[d.dependency_type] || d.dependency_type }}</small>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Stale 记录 -->
    <div class="stale-section">
      <h4 class="section-title">过期记录（{{ staleRecords.length }}）</h4>
      <div v-if="!staleRecords.length" class="empty-tip">暂无过期记录。上游资产变更后将自动标记下游过期。</div>
      <div v-else class="stale-list">
        <div v-for="r in staleRecords" :key="r.id" class="stale-card" :class="'stale-' + r.status">
          <header>
            <code>{{ r.asset_type }}:{{ r.asset_ref }}</code>
            <StatusBadge :tone="r.status === 'open' ? 'warning' : 'success'">
              {{ r.status === 'open' ? '待处理' : '已解决' }}
            </StatusBadge>
          </header>
          <div class="stale-meta">
            <small>原因: {{ staleReasonLabel[r.stale_reason] || r.stale_reason }}</small>
            <small>{{ r.detail }}</small>
          </div>
          <div v-if="r.resolution" class="stale-resolution">处理: {{ r.resolution }}</div>
          <div v-if="r.status === 'open'" class="stale-actions">
            <V2Button variant="ghost" size="sm" :disabled="resolvingId === r.id" @click="resolveStale(r.id)">
              {{ resolvingId === r.id ? '处理中…' : '标记解决' }}
            </V2Button>
          </div>
        </div>
      </div>
    </div>
  </GlassPanel>
</template>

<style scoped>
.wb-error{padding:10px;color:#ffdce1;background:rgba(255,127,145,.1);border-radius:10px;font-size:12px;margin-bottom:10px}
.empty-tip{color:var(--v2-text-subtle);font-size:12px;padding:12px 0}
.section-title{margin:0 0 10px;font-size:13px;color:#e8edff}
.dep-section{margin-bottom:20px}
.dep-tree{display:grid;gap:10px}
.dep-node{display:grid;gap:6px}
.dep-upstream{padding:8px 12px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:8px}
.dep-upstream code{color:var(--v2-primary);font-size:11px}
.dep-downstreams{padding-left:20px;display:grid;gap:4px}
.dep-edge{display:flex;align-items:center;gap:8px;font-size:11px;color:var(--v2-text-muted)}
.dep-edge code{color:var(--v2-primary);font-size:10px}
.dep-arrow{color:var(--v2-text-subtle)}
.dep-type{padding:1px 6px;background:rgba(130,149,255,.1);border-radius:4px;font-size:9px;color:var(--v2-primary)}
.stale-section{margin-top:16px;border-top:1px solid var(--v2-border);padding-top:16px}
.stale-list{display:grid;gap:8px}
.stale-card{padding:12px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:10px;display:grid;gap:8px}
.stale-card.stale-open{border-color:rgba(255,183,77,.3)}
.stale-card header{display:flex;align-items:center;justify-content:space-between;gap:8px}
.stale-card header code{color:var(--v2-primary);font-size:11px}
.stale-meta{display:flex;gap:12px;flex-wrap:wrap}
.stale-meta small{color:var(--v2-text-subtle);font-size:10px}
.stale-resolution{font-size:11px;color:var(--v2-success);padding:4px 8px;background:rgba(79,209,165,.06);border-radius:6px}
.stale-actions{display:flex;justify-content:flex-end}
</style>