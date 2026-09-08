<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { shortDramaApi } from '@/api/modules'
import GlassPanel from '@/v2/components/GlassPanel.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'

const props = defineProps<{ projectId: number }>()

const records = ref<any[]>([])
const loading = ref(false)
const error = ref('')
const expandedId = ref<number | null>(null)

const OPERATION_LABELS: Record<string, string> = {
  novel_chunk_analysis: '小说分块分析',
  novel_analysis_merge: '分析合并',
  novel_adaptation: '改编生成',
  episode_screenplay: '单集剧本生成',
  script_manifest: '拍摄清单生成',
  script_manifest_repair: '拍摄清单修复',
  director_story_ledger: '故事台账生成',
  director_guidance: '导演建议',
  director_chat: '导演对话',
  director_proposal: '提案生成',
  director_llm_audit: '连续性审计',
  json_repair: 'JSON 修复',
}

const STATUS_FILTERS = [
  { value: '', label: '全部' },
  { value: 'failed', label: '失败' },
  { value: 'succeeded', label: '成功' },
  { value: 'invalid_json', label: 'JSON异常' },
]
const statusFilter = ref('')
const operationFilter = ref('')

function opLabel(op: string): string {
  // 去掉 .repair 后缀
  const base = op.replace(/\.repair$/, '')
  return OPERATION_LABELS[base] || OPERATION_LABELS[op] || op
}

const statusTone = (s: string) => s === 'succeeded' ? 'success' : s === 'failed' ? 'danger' : s === 'invalid_json' ? 'warning' : 'info'
const statusLabel = (s: string) => s === 'succeeded' ? '成功' : s === 'failed' ? '失败' : s === 'invalid_json' ? 'JSON异常' : s

function formatCost(c: number): string {
  if (!c) return '—'
  return `$${c.toFixed(4)}`
}

function formatDuration(ms: number): string {
  if (!ms) return '—'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function formatTime(iso: string): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString('zh-CN', { hour12: false })
}

/** 从 request_snapshot 提取 messages 数组（system/user/assistant） */
function requestMessages(r: any): Array<{ role: string; content: string }> {
  const snap = r.request_snapshot
  if (!snap || typeof snap !== 'object') return []
  const messages = (snap as any).messages
  if (!Array.isArray(messages)) return []
  return messages
    .filter((m: any) => m && typeof m.content === 'string')
    .map((m: any) => ({ role: m.role || '?', content: m.content }))
}

/** 从 response_snapshot 提取响应文本 */
function responseText(r: any): string {
  const snap = r.response_snapshot
  if (!snap || typeof snap !== 'object') return ''
  if ((snap as any).content !== undefined) {
    const c = (snap as any).content
    return typeof c === 'string' ? c : JSON.stringify(c, null, 2)
  }
  if ((snap as any).invalid_content !== undefined) {
    return String((snap as any).invalid_content)
  }
  if ((snap as any).issue_count !== undefined) {
    return `生成审计问题 ${(snap as any).issue_count} 条`
  }
  return JSON.stringify(snap, null, 2)
}

async function load() {
  loading.value = true; error.value = ''
  try {
    const params: Record<string, unknown> = { limit: 100 }
    if (statusFilter.value) params.status = statusFilter.value
    if (operationFilter.value) params.operation = operationFilter.value
    records.value = await shortDramaApi.aiRecords(props.projectId, params)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载日志失败'
  } finally { loading.value = false }
}

function toggle(id: number) {
  expandedId.value = expandedId.value === id ? null : id
}

onMounted(() => void load())
watch(() => props.projectId, () => void load())
</script>

<template>
  <GlassPanel title="AI 调用日志" description="所有 AI 调用的审计记录：类型、模型、耗时、token 与成本。">
    <template #actions>
      <select v-model="statusFilter" class="log-filter" @change="load">
        <option v-for="item in STATUS_FILTERS" :key="item.value" :value="item.value">{{ item.label }}</option>
      </select>
      <select v-model="operationFilter" class="log-filter" @change="load">
        <option value="">全部类型</option>
        <option v-for="(label, op) in OPERATION_LABELS" :key="op" :value="op">{{ label }}</option>
      </select>
      <V2Button variant="ghost" size="sm" :disabled="loading" @click="load">{{ loading ? '加载中…' : '刷新' }}</V2Button>
    </template>

    <div v-if="error" class="log-error">{{ error }}</div>

    <div v-if="!records.length && !loading" class="log-empty">暂无 AI 调用记录。</div>

    <div v-else class="log-list">
      <div v-for="r in records" :key="r.id" class="log-row" :class="{ 'log-failed': r.status === 'failed' || r.status === 'invalid_json' }">
        <div class="log-head" @click="toggle(r.id)">
          <div class="log-meta">
            <strong>{{ opLabel(r.operation) }}</strong>
            <small>{{ r.model }} · {{ formatTime(r.created_at) }}</small>
          </div>
          <StatusBadge :tone="statusTone(r.status)">{{ statusLabel(r.status) }}</StatusBadge>
          <button class="log-toggle">{{ expandedId === r.id ? '−' : '+' }}</button>
        </div>

        <!-- 折叠态摘要 -->
        <div v-if="expandedId !== r.id" class="log-summary">
          <span>{{ formatDuration(r.duration_ms) }}</span>
          <span>{{ r.total_tokens }} tokens</span>
          <span>{{ formatCost(r.estimated_cost) }}</span>
        </div>

        <!-- 展开态详情 -->
        <div v-else class="log-detail">
          <div class="log-stats">
            <span>耗时 <b>{{ formatDuration(r.duration_ms) }}</b></span>
            <span>输入 <b>{{ r.input_tokens }}</b> tokens</span>
            <span>输出 <b>{{ r.output_tokens }}</b> tokens</span>
            <span>总计 <b>{{ r.total_tokens }}</b> tokens</span>
            <span>成本 <b>{{ formatCost(r.estimated_cost) }}</b></span>
          </div>
          <div v-if="r.error" class="log-error-detail">
            <label>错误信息</label>
            <pre>{{ r.error }}</pre>
          </div>

          <!-- 输入内容 -->
          <div v-if="requestMessages(r).length" class="log-snap-block">
            <label class="log-snap-label">输入（Prompt）</label>
            <div v-for="(m, mi) in requestMessages(r)" :key="mi" class="log-msg">
              <div class="log-msg-role">{{ m.role === 'system' ? '系统' : m.role === 'user' ? '用户' : m.role }}</div>
              <pre class="log-msg-content">{{ m.content }}</pre>
            </div>
          </div>

          <!-- 输出内容 -->
          <div v-if="responseText(r)" class="log-snap-block">
            <label class="log-snap-label">输出（响应）</label>
            <pre class="log-snap-content">{{ responseText(r) }}</pre>
          </div>

          <small class="log-id">记录 #{{ r.id }} · {{ r.operation }}</small>
        </div>
      </div>
    </div>
  </GlassPanel>
</template>

<style scoped>
.log-filter{max-width:120px;padding:6px 8px;color:var(--v2-text);background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:7px;font-size:11px;outline:none}
.log-error{padding:10px;color:#ffdce1;background:rgba(255,127,145,.1);border-radius:10px;font-size:12px;margin-bottom:8px}
.log-empty{color:var(--v2-text-subtle);font-size:12px;padding:12px 0;text-align:center}
.log-list{display:grid;gap:8px}
.log-row{background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:10px;overflow:hidden}
.log-row.log-failed{border-color:rgba(255,127,145,.3)}
.log-head{display:flex;align-items:center;gap:10px;padding:10px 12px;cursor:pointer;user-select:none}
.log-head:hover{background:rgba(130,149,255,.05)}
.log-meta{flex:1;min-width:0;display:grid;gap:2px}
.log-meta strong{font-size:12px;color:var(--v2-text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.log-meta small{color:var(--v2-text-muted);font-size:10px}
.log-toggle{width:24px;height:24px;display:grid;place-items:center;color:var(--v2-text-muted);background:none;border:1px solid var(--v2-border);border-radius:6px;cursor:pointer;font-size:13px;flex-shrink:0}
.log-summary{display:flex;gap:14px;padding:0 12px 10px;font-size:10px;color:var(--v2-text-subtle)}
.log-detail{padding:0 12px 12px;display:grid;gap:10px}
.log-stats{display:flex;gap:12px;flex-wrap:wrap;font-size:11px;color:var(--v2-text-muted)}
.log-stats b{color:var(--v2-text);font-weight:600}
.log-error-detail label{display:block;font-size:10px;color:var(--v2-danger);margin-bottom:4px;text-transform:uppercase;letter-spacing:.5px}
.log-error-detail pre{margin:0;padding:8px 10px;background:rgba(0,0,0,.25);border-radius:8px;font-size:11px;color:#ffb3bd;white-space:pre-wrap;word-break:break-word;max-height:120px;overflow:auto;line-height:1.5}
.log-id{color:var(--v2-text-subtle);font-size:9px}
.log-snap-block{display:grid;gap:6px}
.log-snap-label{font-size:10px;color:var(--v2-text-subtle);text-transform:uppercase;letter-spacing:.5px;font-weight:600}
.log-msg{display:grid;gap:3px}
.log-msg-role{font-size:10px;color:var(--v2-primary);font-weight:600}
.log-msg-content{margin:0;padding:8px 10px;background:rgba(0,0,0,.25);border-radius:8px;font-size:11px;color:var(--v2-text-muted);white-space:pre-wrap;word-break:break-word;max-height:200px;overflow:auto;line-height:1.6;font-family:inherit}
.log-snap-content{margin:0;padding:8px 10px;background:rgba(0,0,0,.25);border-radius:8px;font-size:11px;color:var(--v2-text-muted);white-space:pre-wrap;word-break:break-word;max-height:260px;overflow:auto;line-height:1.6;font-family:inherit}
</style>