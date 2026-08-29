<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { genTypeApi, shortDramaApi, workflowApi } from '@/api/modules'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'

const props = defineProps<{ projectId: number; manifestId: number; manifestStatus: string }>()

/** 生成类型与工作流选择（配置驱动，不硬编码生成类型） */
const generationTypes = ref<any[]>([])
const workflows = ref<any[]>([])
const selectedGenTypeId = ref<number | null>(null)
const selectedWorkflowVersionId = ref<number | null>(null)

const preview = ref<any>(null)
const links = ref<any[]>([])
const loadingPreview = ref(false)
const creating = ref(false)
const refreshing = ref(false)
const error = ref('')
const idempotencyKey = ref('')

const approved = computed(() => props.manifestStatus === 'approved')

async function loadGenerationTypes() {
  try {
    generationTypes.value = (await genTypeApi.list()) as any[]
  } catch { generationTypes.value = [] }
}

async function loadWorkflows(genTypeId: number) {
  try {
    const list = (await workflowApi.list()) as any[]
    workflows.value = list.filter((w: any) => w.generation_type_id === genTypeId && w.status === 'active')
  } catch { workflows.value = [] }
}

function onGenTypeChange() {
  selectedWorkflowVersionId.value = null
  preview.value = null
  if (selectedGenTypeId.value) void loadWorkflows(selectedGenTypeId.value)
  else workflows.value = []
}

async function runPreview() {
  if (!selectedGenTypeId.value) { error.value = '请选择生成类型'; return }
  loadingPreview.value = true; error.value = ''
  try {
    preview.value = await shortDramaApi.directorCompileManifestPreview(props.projectId, props.manifestId, {
      generation_type_id: selectedGenTypeId.value,
      workflow_version_id: selectedWorkflowVersionId.value,
    })
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '编译预览失败'
  } finally { loadingPreview.value = false }
}

async function createTasks() {
  if (!idempotencyKey.value.trim()) {
    idempotencyKey.value = crypto.randomUUID()
  }
  creating.value = true; error.value = ''
  try {
    const result = await shortDramaApi.directorCreateTasksFromManifest(props.projectId, props.manifestId, {
      generation_type_id: selectedGenTypeId.value,
      workflow_version_id: selectedWorkflowVersionId.value,
      idempotency_key: idempotencyKey.value,
      submit: true,
    })
    preview.value = null
    await loadLinks()
    emit('tasks-created', result)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '创建任务失败'
  } finally { creating.value = false }
}

async function loadLinks() {
  try {
    links.value = await shortDramaApi.directorManifestTaskLinks(props.projectId, props.manifestId)
  } catch { links.value = [] }
}

async function refreshStatus() {
  refreshing.value = true; error.value = ''
  try {
    const result = await shortDramaApi.directorRefreshManifestStatus(props.projectId, props.manifestId)
    await loadLinks()
    emit('status-refreshed', result)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '刷新状态失败'
  } finally { refreshing.value = false }
}

const emit = defineEmits<{ (e: 'tasks-created', result: any): void; (e: 'status-refreshed', result: any): void }>()

const linkStatusTone = (s: string | null) =>
  s === 'synced' ? 'success' : s === 'failed' ? 'danger' : s === 'collecting' ? 'info' : 'neutral'
const taskStatusTone = (s: string | null) =>
  s === 'SUCCESS' ? 'success' : s === 'FAILED' ? 'danger' : s === 'PENDING' || s === 'RUNNING' ? 'info' : 'neutral'

onMounted(() => {
  void loadGenerationTypes()
  void loadLinks()
})
watch(() => props.manifestId, () => {
  preview.value = null
  void loadLinks()
})
</script>

<template>
  <div class="compile-panel">
    <div v-if="error" class="wb-error">{{ error }}</div>

    <template v-if="approved">
      <h4 class="section-title">🚀 编译为生产任务</h4>
      <p class="compile-hint">选择生成类型与工作流后预览编译。校验失败的任务不会创建。</p>

      <div class="compile-form">
        <select v-model="selectedGenTypeId" class="compile-select" @change="onGenTypeChange">
          <option :value="null" disabled>选择生成类型</option>
          <option v-for="gt in generationTypes" :key="gt.id" :value="gt.id">
            {{ gt.name }}（{{ gt.media_type }}）
          </option>
        </select>
        <select v-model="selectedWorkflowVersionId" class="compile-select" :disabled="!workflows.length">
          <option :value="null">默认工作流版本</option>
          <option v-for="w in workflows" :key="w.id" :value="w.current_version_id ?? w.id">
            {{ w.name }}
          </option>
        </select>
        <V2Button variant="ghost" :disabled="loadingPreview || !selectedGenTypeId" @click="runPreview">
          {{ loadingPreview ? '编译中…' : '编译预览' }}
        </V2Button>
      </div>

      <!-- 编译预览结果 -->
      <div v-if="preview" class="preview-box">
        <div class="preview-summary">
          <span>共 {{ preview.total }} 项</span>
          <StatusBadge :tone="preview.error_count ? 'warning' : 'success'">
            {{ preview.ok_count }} 可编译 / {{ preview.error_count }} 有错误
          </StatusBadge>
          <V2Button
            variant="primary" size="sm"
            :disabled="creating || !preview.ok_count"
            @click="createTasks"
          >
            {{ creating ? '创建中…' : `创建任务（${preview.ok_count}）` }}
          </V2Button>
        </div>
        <div class="intent-list">
          <div v-for="intent in preview.intents" :key="intent.manifest_item_id" class="intent-card"
            :class="{ 'has-error': intent.validation_errors?.length }">
            <header>
              <code>{{ intent.asset_stable_key }}</code>
              <small>{{ intent.required_view }}</small>
              <StatusBadge v-if="intent.validation_errors?.length" tone="danger">
                {{ intent.validation_errors.length }} 个错误
              </StatusBadge>
              <StatusBadge v-else tone="success">可编译</StatusBadge>
            </header>
            <div v-if="intent.validation_errors?.length" class="intent-errors">
              <small v-for="(err, i) in intent.validation_errors" :key="i">⚠ {{ err.message }}</small>
            </div>
            <details>
              <summary>参数预览</summary>
              <pre>{{ JSON.stringify(intent.params, null, 2) }}</pre>
            </details>
          </div>
        </div>
      </div>
    </template>
    <p v-else class="compile-hint">清单审批后可编译为生产任务。</p>

    <!-- 任务链接状态 -->
    <template v-if="links.length">
      <div class="links-head">
        <h4 class="section-title">🔗 任务链接（{{ links.length }}）</h4>
        <V2Button variant="ghost" size="sm" :disabled="refreshing" @click="refreshStatus">
          {{ refreshing ? '刷新中…' : '刷新状态' }}
        </V2Button>
      </div>
      <div class="links-list">
        <div v-for="link in links" :key="link.id" class="link-card">
          <code>{{ link.asset_stable_key }}</code>
          <span class="link-meta">任务 #{{ link.task_id }}</span>
          <StatusBadge :tone="taskStatusTone(link.task_status)">{{ link.task_status || '—' }}</StatusBadge>
          <StatusBadge :tone="linkStatusTone(link.link_status)">{{ link.link_status }}</StatusBadge>
          <small v-if="link.output_resource_id" class="take-tag">输出素材 #{{ link.output_resource_id }}</small>
          <small v-if="link.take_id" class="take-tag">Take #{{ link.take_id }}</small>
          <small v-if="link.sync_error" class="link-error">{{ link.sync_error }}</small>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.compile-panel{display:grid;gap:12px;border-top:1px solid var(--v2-border);margin-top:16px;padding-top:16px}
.wb-error{padding:10px;color:#ffdce1;background:rgba(255,127,145,.1);border-radius:10px;font-size:12px}
.section-title{margin:0;font-size:13px;color:#e8edff}
.compile-hint{margin:0;color:var(--v2-text-subtle);font-size:11px}
.compile-form{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.compile-select{min-height:34px;padding:6px 10px;color:var(--v2-text);background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:9px;font-size:12px}
.preview-box{display:grid;gap:10px;padding:12px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:10px}
.preview-summary{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.preview-summary span{font-size:12px;color:var(--v2-text-muted)}
.preview-summary button{margin-left:auto}
.intent-list{display:grid;gap:6px}
.intent-card{padding:10px;background:rgba(0,0,0,.15);border:1px solid var(--v2-border);border-radius:8px;display:grid;gap:6px}
.intent-card.has-error{border-color:rgba(255,127,145,.35)}
.intent-card header{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.intent-card header code{color:var(--v2-primary);font-size:11px}
.intent-errors{display:grid;gap:3px}
.intent-errors small{color:#ffb347;font-size:10px}
.intent-card details{font-size:11px;color:var(--v2-text-subtle)}
.intent-card details summary{cursor:pointer}
.intent-card details pre{margin-top:6px;max-height:140px;overflow:auto;font-size:10px;background:rgba(0,0,0,.3);padding:8px;border-radius:8px}
.links-head{display:flex;align-items:center;justify-content:space-between;margin-top:8px}
.links-list{display:grid;gap:6px}
.link-card{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:9px 11px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:9px;font-size:11px;color:var(--v2-text-muted)}
.link-card code{color:var(--v2-primary);font-size:10px}
.link-meta{color:var(--v2-text-subtle)}
.take-tag{color:var(--v2-success)}
.link-error{color:var(--v2-danger);flex-basis:100%}
</style>