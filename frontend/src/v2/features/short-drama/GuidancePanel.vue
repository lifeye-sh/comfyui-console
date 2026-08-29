<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { shortDramaApi } from '@/api/modules'
import GlassPanel from '@/v2/components/GlassPanel.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'

const props = defineProps<{ projectId: number }>()
const emit = defineEmits<{ (e: 'edit-prompt', code: string, title: string): void; (e: 'open-chat'): void }>()

const suggestions = ref<any[]>([])
const loading = ref(false)
const error = ref('')
const revisionHash = ref('')

const KIND_LABELS: Record<string, string> = {
  gap: '缺失项',
  audit: '审计问题',
  stale: '过期资产',
  style: '风格',
}

const SEVERITY_TONES: Record<string, 'danger' | 'warning' | 'info'> = {
  blocker: 'danger',
  risk: 'warning',
  info: 'info',
}

async function load() {
  loading.value = true; error.value = ''
  try {
    const result = await shortDramaApi.directorGuidance(props.projectId)
    suggestions.value = result.suggestions || []
    revisionHash.value = result.revision_hash || ''
  } catch (e: any) {
    const detail = e?.response?.data?.detail || ''
    error.value = detail || '生成建议失败'
  } finally { loading.value = false }
}

onMounted(() => {
  // 先展示已有建议占位（guidance 为 AI 生成，需要手动触发或进入时自动一次）
  void load()
})
watch(() => props.projectId, load)
</script>

<template>
  <GlassPanel
    title="AI 导演建议"
    description="基于项目上下文生成的缺失项、审计问题与过期风险。建议不可直接执行。"
  >
    <template #actions>
      <div class="gp-actions-row">
        <V2Button variant="ghost" size="sm" :disabled="loading" @click="load">
          {{ loading ? '分析中…' : '刷新建议' }}
        </V2Button>
        <V2Button variant="ghost" size="sm" @click="emit('edit-prompt', 'guidance', 'AI 导演建议')">📝</V2Button>
      </div>
    </template>

    <div v-if="error" class="gp-error">
      {{ error }}
      <span v-if="error.includes('限额')" class="gp-hint">（项目每小时有 AI 调用限额）</span>
    </div>

    <div v-if="!suggestions.length && !loading && !error" class="empty-tip">
      暂无建议。点击「刷新建议」让 AI 分析当前项目状态。
    </div>

    <div v-else class="suggestion-list">
      <div v-for="(s, i) in suggestions" :key="i" class="suggestion-card" :class="'sev-' + s.severity">
        <header>
          <StatusBadge :tone="SEVERITY_TONES[s.severity] || 'info'">
            {{ KIND_LABELS[s.kind] || s.kind }}
          </StatusBadge>
          <b class="suggestion-title">{{ s.title }}</b>
        </header>
        <p v-if="s.detail" class="suggestion-detail">{{ s.detail }}</p>
      </div>
    </div>

    <div v-if="revisionHash" class="revision-note">
      <small>分析版本：{{ revisionHash.slice(0, 12) }}…（项目变更后建议自动过期）</small>
    </div>
  </GlassPanel>
</template>

<style scoped>
.gp-error{padding:10px;color:#ffdce1;background:rgba(255,127,145,.1);border-radius:10px;font-size:12px;margin-bottom:8px}
.gp-hint{color:var(--v2-text-subtle)}
.gp-actions-row{display:flex;gap:6px;align-items:center}
.empty-tip{color:var(--v2-text-subtle);font-size:12px;padding:12px 0}
.suggestion-list{display:grid;gap:8px}
.suggestion-card{padding:11px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:10px;display:grid;gap:6px}
.suggestion-card.sev-blocker{border-color:rgba(255,127,145,.3)}
.suggestion-card.sev-risk{border-color:rgba(255,183,77,.25)}
.suggestion-card header{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.suggestion-title{font-size:12px;color:var(--v2-text)}
.suggestion-detail{margin:0;font-size:11px;color:var(--v2-text-muted);line-height:1.6}
.revision-note{margin-top:10px;padding-top:8px;border-top:1px solid var(--v2-border)}
.revision-note small{color:var(--v2-text-subtle);font-size:10px}
</style>