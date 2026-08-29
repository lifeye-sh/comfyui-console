<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { shortDramaApi } from '@/api/modules'
import GlassPanel from '@/v2/components/GlassPanel.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'

const props = defineProps<{ projectId: number }>()

const runs = ref<any[]>([])
const selectedRun = ref<any>(null)
const creating = ref(false)
const runningRules = ref(false)
const runningLLM = ref(false)
const finishing = ref(false)
const waivingId = ref<number | null>(null)
const error = ref('')

const SEVERITY_META: Record<string, { label: string; tone: 'danger'|'warning'|'info'|'neutral' }> = {
  blocker: { label: '阻塞', tone: 'danger' },
  conflict: { label: '冲突', tone: 'warning' },
  risk: { label: '风险', tone: 'warning' },
  optimization: { label: '优化', tone: 'info' },
}

const DIMENSION_LABELS: Record<string, string> = {
  identity: '身份',
  costume: '服装',
  prop: '道具',
  geography: '地理',
  screen_direction: '屏幕方向',
  lighting: '光照',
  color: '色彩',
  timeline: '时间线',
  causal: '因果',
}

async function load() {
  error.value = ''
  try {
    runs.value = await shortDramaApi.directorAuditRuns(props.projectId) as any[]
    if (runs.value.length && !selectedRun.value) {
      await openRun(runs.value[0].id)
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载审计运行失败'
  }
}

async function openRun(id: number) {
  try {
    selectedRun.value = await shortDramaApi.directorAuditRunDetail(props.projectId, id)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载审计运行详情失败'
  }
}

async function createRun() {
  creating.value = true; error.value = ''
  try {
    const run = await shortDramaApi.directorCreateAuditRun(props.projectId, { manifest_version_id: null })
    await load()
    await openRun(run.id)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '创建审计运行失败'
  } finally { creating.value = false }
}

async function runRules() {
  if (!selectedRun.value) return
  runningRules.value = true; error.value = ''
  try {
    const result = await shortDramaApi.directorRunRuleAudit(props.projectId, selectedRun.value.id)
    await openRun(selectedRun.value.id)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '规则审计失败'
  } finally { runningRules.value = false }
}

async function runLLM() {
  if (!selectedRun.value) return
  runningLLM.value = true; error.value = ''
  try {
    await shortDramaApi.directorRunLLMAudit(props.projectId, selectedRun.value.id)
    await openRun(selectedRun.value.id)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'AI 语义审计失败'
  } finally { runningLLM.value = false }
}

async function finish() {
  if (!selectedRun.value) return
  finishing.value = true; error.value = ''
  try {
    const result = await shortDramaApi.directorFinishAudit(props.projectId, selectedRun.value.id)
    selectedRun.value = result
    await load()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '结束审计失败'
  } finally { finishing.value = false }
}

async function waive(issueId: number) {
  const reason = prompt('请输入豁免原因') || ''
  if (!reason.trim()) return
  waivingId.value = issueId; error.value = ''
  try {
    await shortDramaApi.directorWaiveIssue(props.projectId, issueId, { reason })
    await openRun(selectedRun.value.id)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '豁免失败'
  } finally { waivingId.value = null }
}

const issuesBySeverity = computed(() => {
  if (!selectedRun.value?.issues) return {}
  const groups: Record<string, any[]> = { blocker: [], conflict: [], risk: [], optimization: [] }
  for (const issue of selectedRun.value.issues) {
    (groups[issue.severity] ??= []).push(issue)
  }
  return groups
})

const severityOrder = ['blocker', 'conflict', 'risk', 'optimization']

onMounted(load)
watch(() => props.projectId, load)
</script>

<template>
  <GlassPanel title="连续性审计" description="9 维规则审计 + AI 语义补充。blocker 与优化分开，豁免需记录原因。">
    <template #actions>
      <V2Button variant="primary" :disabled="creating" @click="createRun">{{ creating ? '创建中…' : '新建审计' }}</V2Button>
    </template>

    <div v-if="error" class="wb-error">{{ error }}</div>

    <div v-if="!runs.length" class="empty-tip">
      暂无审计运行。点击「新建审计」开始。
    </div>

    <div v-else class="audit-section">
      <!-- 审计运行列表 -->
      <div class="run-tabs">
        <button v-for="r in runs" :key="r.id" class="run-tab"
          :class="{ active: selectedRun?.id === r.id }" @click="openRun(r.id)">
          运行 #{{ r.id }}
          <StatusBadge :tone="r.status === 'completed' ? 'success' : 'info'">{{ r.status === 'completed' ? '已完成' : '运行中' }}</StatusBadge>
        </button>
      </div>

      <div v-if="selectedRun" class="run-detail">
        <!-- 汇总 -->
        <div v-if="selectedRun.summary && Object.keys(selectedRun.summary).length" class="summary-box">
          <div class="summary-item" v-for="sev in severityOrder" :key="sev">
            <StatusBadge :tone="SEVERITY_META[sev]?.tone || 'neutral'">{{ SEVERITY_META[sev]?.label || sev }}</StatusBadge>
            <b>{{ selectedRun.summary[sev + 's'] || 0 }}</b>
          </div>
          <div class="summary-item total">
            <span>总计</span><b>{{ selectedRun.summary.total_issues || 0 }}</b>
          </div>
          <div v-if="selectedRun.summary.conclusion" class="conclusion" :class="{ 'has-blocker': (selectedRun.summary.blockers || 0) > 0 }">
            {{ selectedRun.summary.conclusion }}
          </div>
        </div>

        <!-- 操作按钮 -->
        <div v-if="selectedRun.status === 'running'" class="action-row">
          <V2Button variant="primary" :disabled="runningRules" @click="runRules">{{ runningRules ? '规则审计中…' : '运行规则审计' }}</V2Button>
          <V2Button variant="ghost" :disabled="runningLLM" @click="runLLM">{{ runningLLM ? 'AI 审计中…' : 'AI 语义审计' }}</V2Button>
          <V2Button variant="ghost" :disabled="finishing" @click="finish">{{ finishing ? '结束中…' : '结束审计' }}</V2Button>
        </div>

        <!-- 问题分组展示 -->
        <div v-for="sev in severityOrder" :key="sev">
          <template v-if="issuesBySeverity[sev]?.length">
            <h4 class="severity-group-title">
              <StatusBadge :tone="SEVERITY_META[sev]?.tone || 'neutral'">{{ SEVERITY_META[sev]?.label || sev }}</StatusBadge>
              <span>{{ issuesBySeverity[sev].length }} 个</span>
            </h4>
            <div class="issue-list">
              <div v-for="issue in issuesBySeverity[sev]" :key="issue.id" class="issue-card" :class="'sev-' + sev">
                <header>
                  <small class="dim-badge">{{ DIMENSION_LABELS[issue.dimension] || issue.dimension }}</small>
                  <small v-if="issue.status === 'waived'" class="waived-tag">已豁免</small>
                </header>
                <p class="issue-desc">{{ issue.description }}</p>
                <div v-if="issue.targets?.length" class="issue-targets">
                  <small v-for="t in issue.targets" :key="t.id" class="target-tag">
                    {{ t.target_type }}:{{ t.target_ref }}
                  </small>
                </div>
                <div v-if="issue.waive_reason" class="waive-info">
                  豁免原因: {{ issue.waive_reason }}
                </div>
                <div v-if="issue.status === 'open'" class="issue-actions">
                  <V2Button variant="ghost" size="sm" :disabled="waivingId === issue.id" @click="waive(issue.id)">
                    {{ waivingId === issue.id ? '处理中…' : '豁免' }}
                  </V2Button>
                </div>
              </div>
            </div>
          </template>
        </div>
        <div v-if="!selectedRun.issues?.length" class="empty-tip">暂无审计问题。运行规则审计或 AI 语义审计来检测问题。</div>
      </div>
    </div>
  </GlassPanel>
</template>

<style scoped>
.wb-error{padding:10px;color:#ffdce1;background:rgba(255,127,145,.1);border-radius:10px;font-size:12px;margin-bottom:10px}
.empty-tip{color:var(--v2-text-subtle);font-size:12px;padding:20px 0}
.audit-section{display:grid;gap:14px}
.run-tabs{display:flex;gap:6px;flex-wrap:wrap}
.run-tab{display:flex;align-items:center;gap:6px;padding:7px 12px;color:var(--v2-text-muted);background:transparent;border:1px solid var(--v2-border);border-radius:9px;cursor:pointer;font-size:12px}
.run-tab.active{color:var(--v2-text);background:rgba(130,149,255,.1);border-color:rgba(130,149,255,.35)}
.run-detail{display:grid;gap:14px}
.summary-box{display:flex;gap:14px;flex-wrap:wrap;padding:14px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:10px;align-items:center}
.summary-item{display:flex;align-items:center;gap:6px;font-size:12px}
.summary-item b{color:var(--v2-text);font-size:14px}
.summary-item.total{margin-left:auto}
.conclusion{width:100%;font-size:12px;color:var(--v2-text-muted);padding-top:8px;border-top:1px solid var(--v2-border)}
.conclusion.has-blocker{color:var(--v2-danger)}
.action-row{display:flex;gap:8px;flex-wrap:wrap}
.severity-group-title{display:flex;align-items:center;gap:8px;margin:16px 0 8px;font-size:13px;color:#e8edff}
.severity-group-title span{color:var(--v2-text-subtle);font-size:11px}
.issue-list{display:grid;gap:8px}
.issue-card{padding:12px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:10px;display:grid;gap:8px}
.issue-card.sev-blocker{border-color:rgba(255,127,145,.3);background:rgba(255,127,145,.05)}
.issue-card.sev-conflict{border-color:rgba(255,183,77,.25)}
.issue-card.sev-risk{border-color:rgba(255,183,77,.15)}
.issue-card header{display:flex;align-items:center;gap:8px}
.dim-badge{padding:2px 8px;background:rgba(130,149,255,.12);border-radius:6px;font-size:10px;color:var(--v2-primary)}
.waived-tag{padding:2px 8px;background:rgba(255,183,77,.12);border-radius:6px;font-size:10px;color:#ffb347}
.issue-desc{margin:0;font-size:12px;color:var(--v2-text);line-height:1.5}
.issue-targets{display:flex;gap:6px;flex-wrap:wrap}
.target-tag{padding:2px 6px;background:rgba(0,0,0,.2);border-radius:4px;font-size:10px;color:var(--v2-text-muted)}
.waive-info{font-size:11px;color:var(--v2-text-subtle);padding-top:4px;border-top:1px solid var(--v2-border)}
.issue-actions{display:flex;justify-content:flex-end}
</style>