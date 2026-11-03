<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { batchApi, generationTypeConfigApi, imageProviderApi, settingsApi, type ImageProvider } from '@/api/modules'
import GlassCard from '@/v2/components/GlassCard.vue'
import V2Button from '@/v2/components/V2Button.vue'
import V2Field from '@/v2/components/V2Field.vue'
import WorkflowParameterFields from '@/v2/features/generate/WorkflowParameterFields.vue'
import { workflowDefaults, workflowPayload, workflowValidation, type SelectSettings } from '@/v2/features/generate/workflowParameters'
import type { RuntimeWorkflow } from '@/v2/features/generation-config/model'
import type { GenerationTypeItem } from '@/v2/features/tasks/model'

const props = defineProps<{
  open: boolean
  generationType: GenerationTypeItem | null
  resourceIds: number[]
}>()
const emit = defineEmits<{
  close: []
  created: [{ batchId: number; enqueued: number; invalid: number }]
}>()

const loading = ref(false)
const submitting = ref(false)
const error = ref('')
const workflows = ref<RuntimeWorkflow[]>([])
const imageProviders = ref<ImageProvider[]>([])
const settings = ref<SelectSettings>({})
const workflowVersionId = ref<number | null>(null)
const executionTarget = ref('comfyui')
const params = ref<Record<string, any>>({})
const apiPrompt = ref('')
const apiSize = ref('')
const batchName = ref('')

function imageParameters(workflow: RuntimeWorkflow) {
  return workflow.parameters.filter(parameter => parameter.type === 'image')
}

const compatibleWorkflows = computed(() => workflows.value.filter(workflow => {
  return imageParameters(workflow).some(parameter => !parameter.multiple)
}))
const currentWorkflow = computed(() => compatibleWorkflows.value.find(workflow => workflow.workflow_version_id === workflowVersionId.value) || null)
const imageParameter = computed(() => currentWorkflow.value ? imageParameters(currentWorkflow.value).find(parameter => !parameter.multiple) || null : null)
const visibleParameters = computed(() => currentWorkflow.value?.parameters.filter(parameter => parameter.key !== imageParameter.value?.key) || [])
const outputSizeKey = computed(() => props.generationType?.media_type === 'video' ? 'video_size' : 'image_size')
const usingApi = computed(() => props.generationType?.code === 'mixed' && executionTarget.value.startsWith('gemini:'))
const apiProviderId = computed(() => usingApi.value ? Number(executionTarget.value.split(':')[1]) : null)
const imageSizeSetting = computed(() => settings.value.image_size)
const canConfigure = computed(() => usingApi.value ? !!apiProviderId.value : !!currentWorkflow.value)

function errorText(event: any) {
  return event?.response?.data?.detail || event?.response?.data?.message || event?.message || '操作失败'
}

function selectWorkflow(value?: number | null) {
  const nextId = Number(value || workflowVersionId.value) || null
  const workflow = compatibleWorkflows.value.find(item => item.workflow_version_id === nextId)
  workflowVersionId.value = workflow?.workflow_version_id || null
  params.value = workflow ? workflowDefaults(workflow, settings.value, outputSizeKey.value) : {}
}

function switchExecutionTarget() {
  error.value = ''
  if (!usingApi.value && !currentWorkflow.value) {
    const first = compatibleWorkflows.value.find(item => item.is_default) || compatibleWorkflows.value[0]
    if (first) selectWorkflow(first.workflow_version_id)
  }
}

async function load() {
  if (!props.open || !props.generationType) return
  loading.value = true
  error.value = ''
  workflows.value = []
  imageProviders.value = []
  workflowVersionId.value = null
  executionTarget.value = 'comfyui'
  params.value = {}
  apiPrompt.value = ''
  apiSize.value = ''
  batchName.value = `${props.generationType.name}-批量单图-${new Date().toLocaleString()}`
  try {
    const mixed = props.generationType.code === 'mixed'
    const [active, selectOptions, providers] = await Promise.all([
      generationTypeConfigApi.active(props.generationType.id).catch(event => {
        if (mixed) return {workflows: []}
        throw event
      }),
      settingsApi.getSelectOptions(),
      mixed ? imageProviderApi.list() : Promise.resolve([] as ImageProvider[]),
    ])
    settings.value = selectOptions || {}
    workflows.value = (active.workflows || []) as RuntimeWorkflow[]
    imageProviders.value = providers.filter(provider => provider.enabled)
    const sizeSetting = settings.value.image_size
    apiSize.value = String(sizeSetting?.default_value || sizeSetting?.options?.[0]?.value || '')
    const first = compatibleWorkflows.value.find(item => item.is_default) || compatibleWorkflows.value[0]
    if (first) selectWorkflow(first.workflow_version_id)
    if (mixed && imageProviders.value.length) {
      const provider = imageProviders.value.find(item => item.is_default) || imageProviders.value[0]
      executionTarget.value = `gemini:${provider.id}`
    } else if (!first) {
      error.value = mixed ? '混合生图没有可用的 API 图片提供方或单图输入工作流' : '该任务类型没有包含单图输入的可用工作流'
    }
  } catch (event: any) {
    error.value = errorText(event)
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (!props.generationType || !props.resourceIds.length) return
  const workflow = currentWorkflow.value
  const input = imageParameter.value
  if (usingApi.value) {
    if (!apiProviderId.value) { error.value = '请选择 API 图片提供方'; return }
    if (!apiPrompt.value.trim()) { error.value = '请填写图片编辑提示词'; return }
    if (!imageSizeSetting.value?.options?.some(option => String(option.value) === apiSize.value)) { error.value = '请选择维护项中的图片尺寸'; return }
  } else {
    if (!workflow || !input) return
    const validationError = workflowValidation(workflow.parameters, {...params.value, [input.key]: props.resourceIds[0]})
    if (validationError) { error.value = validationError; return }
  }
  submitting.value = true
  error.value = ''
  try {
    const rows = props.resourceIds.map((resourceId, index) => {
      const rowParams = usingApi.value
        ? {
            prompt: apiPrompt.value.trim(),
            reference_resource_ids: [resourceId],
            size: apiSize.value,
            __execution_provider: 'gemini_image',
            __provider_config_id: apiProviderId.value,
          }
        : workflowPayload(workflow!.parameters, {...params.value, [input!.key]: resourceId})
      return {
        row_no: index,
        generation_type_id: props.generationType!.id,
        workflow_version_id: usingApi.value ? null : workflow!.workflow_version_id,
        params: rowParams,
      }
    })
    const batch = await batchApi.create({
      name: batchName.value.trim() || `${props.generationType.name}-批量单图`,
      generation_type_id: props.generationType.id,
      workflow_version_id: usingApi.value ? null : workflow!.workflow_version_id,
      rows,
    })
    const result = await batchApi.submit(batch.id)
    emit('created', {batchId: batch.id, enqueued: result.enqueued || 0, invalid: result.invalid || 0})
  } catch (event: any) {
    error.value = errorText(event)
  } finally {
    submitting.value = false
  }
}

watch(() => [props.open, props.generationType?.id, props.resourceIds.join(',')], () => void load())
</script>

<template>
  <div v-if="open" class="batch-task-layer" role="dialog" aria-modal="true" aria-label="批量单图任务" @click.self="emit('close')">
    <GlassCard class="batch-task-modal" padding="sm">
      <header>
        <div><small>BATCH SINGLE-IMAGE TASK</small><h2>批量单图任务</h2><p>{{ generationType?.name }} · 已选 {{ resourceIds.length }} 张图片，每张图片生成一个独立任务</p></div>
        <button class="close" :disabled="submitting" @click="emit('close')" aria-label="关闭"><StudioIcon name="close"/></button>
      </header>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div v-if="loading" class="loading">正在读取工作流参数…</div>
      <div v-else-if="canConfigure" class="form">
        <V2Field label="批次名称"><input v-model="batchName" /></V2Field>
        <V2Field v-if="generationType?.code==='mixed'" label="执行提供方" required>
          <select v-model="executionTarget" @change="switchExecutionTarget">
            <option v-for="provider in imageProviders" :key="provider.id" :value="`gemini:${provider.id}`">API · {{ provider.name }} · {{ provider.model }}</option>
            <option v-if="compatibleWorkflows.length" value="comfyui">ComfyUI 单图工作流</option>
          </select>
        </V2Field>
        <V2Field v-if="!usingApi" label="工作流" required>
          <select :value="workflowVersionId" @change="selectWorkflow(Number(($event.target as HTMLSelectElement).value))">
            <option v-for="workflow in compatibleWorkflows" :key="workflow.workflow_version_id" :value="workflow.workflow_version_id">{{ workflow.name }} · v{{ workflow.version }}</option>
          </select>
        </V2Field>
        <div class="input-summary"><span>自动输入</span><b>{{ usingApi?'API 参考图片':(imageParameter?.label || imageParameter?.key) }}</b><em>{{ resourceIds.length===1?'单图输入：创建 1 个任务':`批量输入：${resourceIds.length} 张图片分别创建 ${resourceIds.length} 个任务` }}</em></div>
        <div v-if="usingApi" class="parameter-grid">
          <V2Field label="图片尺寸" required>
            <select v-model="apiSize">
              <option v-if="!imageSizeSetting?.options?.length" value="">未维护图片尺寸</option>
              <option v-for="option in imageSizeSetting?.options||[]" :key="String(option.value)" :value="String(option.value)">{{ option.label }}</option>
            </select>
          </V2Field>
          <V2Field label="图片编辑提示词" required class="wide-field">
            <textarea v-model="apiPrompt" rows="5" placeholder="描述每张原图需要进行的修改；同一提示词将分别应用到所有图片"/>
          </V2Field>
        </div>
        <div v-else class="parameter-grid">
          <WorkflowParameterFields v-model="params" :parameters="visibleParameters" :settings="settings" :size-key="outputSizeKey" :disabled="submitting" />
        </div>
      </div>
      <footer>
        <V2Button variant="ghost" :disabled="submitting" @click="emit('close')">取消</V2Button>
        <V2Button variant="primary" :disabled="loading||submitting||!canConfigure||!resourceIds.length" @click="submit">{{ submitting?'创建中…':`创建并提交 ${resourceIds.length} 个任务` }}</V2Button>
      </footer>
    </GlassCard>
  </div>
</template>

<style scoped>
.batch-task-layer{position:fixed;inset:0;z-index:10020;display:grid;place-items:center;padding:20px;background:rgba(0,0,0,.68);backdrop-filter:blur(5px)}
.batch-task-modal{width:min(860px,96vw);max-height:88vh;overflow:auto}
header{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding-bottom:14px;border-bottom:1px solid var(--v2-border)}
header small{color:var(--v2-primary);font-size:10px;letter-spacing:.12em}h2{margin:5px 0 4px}header p{margin:0;color:var(--v2-text-muted);font-size:12px}.close{padding:6px;color:var(--v2-text-muted);background:transparent;border:0;cursor:pointer}.error{padding:10px 12px;color:var(--ws-danger);background:color-mix(in srgb, var(--ws-danger) 10%, transparent);border:1px solid color-mix(in srgb, var(--ws-danger) 25%, transparent);border-radius:9px}.loading{padding:60px;text-align:center;color:var(--v2-text-muted)}
.form{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding:18px 0}.input-summary{grid-column:1/-1;display:grid;grid-template-columns:auto auto 1fr;align-items:center;gap:9px;padding:11px 13px;color:var(--v2-text-muted);background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:10px;font-size:12px}.input-summary span{color:var(--v2-primary)}.input-summary b{color:var(--v2-text)}.input-summary em{justify-self:end;font-style:normal}.parameter-grid{grid-column:1/-1;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.parameter-grid :deep(.wide-field){grid-column:1/-1}.parameter-grid textarea{box-sizing:border-box;width:100%;resize:vertical}footer{display:flex;justify-content:flex-end;gap:9px;padding-top:14px;border-top:1px solid var(--v2-border)}
@media(max-width:700px){.batch-task-layer{padding:8px}.batch-task-modal{width:100%;max-height:94vh}.form,.parameter-grid{grid-template-columns:1fr}.input-summary{grid-template-columns:1fr}.input-summary em{justify-self:start}footer{position:sticky;bottom:0;padding:12px 0;background:var(--v2-surface)}}
</style>
