<script setup lang="ts">
import { computed, h, onMounted, onUnmounted, ref } from 'vue'
import {
  NButton,
  NCard,
  NCheckbox,
  NDescriptions,
  NDescriptionsItem,
  NDataTable,
  NDatePicker,
  NH2,
  NInput,
  NInputNumber,
  NModal,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  NText,
  useMessage,
  type DataTableColumns,
  type TagProps,
} from 'naive-ui'
import { genTypeApi, resourceApi, taskApi } from '@/api/modules'
import { onWsEvent, connectWs } from '@/ws/client'
import { getAccessToken } from '@/api/client'

interface TaskItem {
  id: number
  batch_id: number
  row_no: number
  generation_type_id: number | null
  workflow_version_id: number | null
  params: Record<string, unknown>
  status: string
  priority: number
  node_id: number | null
  prompt_id: string | null
  retries: number
  error: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}

interface TaskOutput {
  id: number
  filename: string
  media_type: 'image' | 'video' | 'audio'
  mime: string
  url: string
  width?: number | null
  height?: number | null
}

interface TaskEvent {
  id: number
  type: string
  progress: number
  payload: Record<string, unknown>
  created_at: string
}

const message = useMessage()
const tasks = ref<TaskItem[]>([])
const loading = ref(false)
const actionTaskId = ref<number | null>(null)
const keyword = ref('')
const statusFilter = ref<string | null>(null)
const generationTypeFilter = ref<number | null>(null)
const generationTypes = ref<any[]>([])
const generationTypeNames = ref<Record<number, string>>({})
const taskOutputs = ref<Record<number, TaskOutput[]>>({})
const outputLoading = ref<Record<number, boolean>>({})
const previewOutput = ref<TaskOutput | null>(null)
const previewUrl = ref('')
const previewLoading = ref(false)
const imageScale = ref(1)
const imageOffsetX = ref(0)
const imageOffsetY = ref(0)
const imageDragging = ref(false)
let imageDragStartX = 0
let imageDragStartY = 0
let imageDragOriginX = 0
let imageDragOriginY = 0
const detailTask = ref<TaskItem | null>(null)
const detailEvents = ref<TaskEvent[]>([])
const detailLoading = ref(false)
const detailExecuting = ref(false)
const detailParamDraft = ref<Record<string, any>>({})
const detailParamObjectKeys = ref<Set<string>>(new Set())
const detailMediaPreviews = ref<Record<string, TaskOutput>>({})
const detailMediaLoading = ref<Record<string, boolean>>({})

function getTodayRange(): [number, number] {
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  const end = new Date(start)
  end.setDate(end.getDate() + 1)
  end.setMilliseconds(-1)
  return [start.getTime(), end.getTime()]
}

const dateRange = ref<[number, number] | null>(getTodayRange())
let off: (() => void) | null = null
let reloadTimer: ReturnType<typeof setTimeout> | null = null

const statusOptions = [
  { label: '全部状态', value: '' },
  { label: '草稿', value: 'DRAFT' },
  { label: '等待中', value: 'PENDING' },
  { label: '分配中', value: 'DISPATCHING' },
  { label: '已入队', value: 'QUEUED' },
  { label: '执行中', value: 'RUNNING' },
  { label: '处理中', value: 'FINALIZING' },
  { label: '成功', value: 'SUCCESS' },
  { label: '失败', value: 'FAILED' },
  { label: '已取消', value: 'CANCELLED' },
]

const statusLabels: Record<string, string> = {
  DRAFT: '草稿',
  PENDING: '等待中',
  DISPATCHING: '分配中',
  QUEUED: '已入队',
  RUNNING: '执行中',
  FINALIZING: '处理中',
  SUCCESS: '成功',
  FAILED: '失败',
  CANCELLED: '已取消',
}

function statusType(status: string): TagProps['type'] {
  if (status === 'SUCCESS') return 'success'
  if (status === 'FAILED') return 'error'
  if (status === 'CANCELLED') return 'default'
  if (['RUNNING', 'FINALIZING'].includes(status)) return 'info'
  return 'warning'
}

function formatDate(value: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function promptText(task: TaskItem) {
  const value = task.params?.prompt
  return typeof value === 'string' && value.trim() ? value : '—'
}

async function fetchResourceBlob(url: string) {
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${getAccessToken() || ''}` },
  })
  if (!response.ok) throw new Error('资源加载失败')
  return URL.createObjectURL(await response.blob())
}

function clearTaskOutputs(taskId: number) {
  for (const output of taskOutputs.value[taskId] || []) {
    if (output.url) URL.revokeObjectURL(output.url)
  }
  delete taskOutputs.value[taskId]
  delete outputLoading.value[taskId]
}

async function loadTaskOutputs(taskId: number) {
  if (taskId in taskOutputs.value || outputLoading.value[taskId]) return
  outputLoading.value[taskId] = true
  try {
    const outputs = await taskApi.outputs(taskId)
    taskOutputs.value[taskId] = await Promise.all(outputs.map(async (output: any) => {
      let url = ''
      if (['image', 'video'].includes(output.media_type) || String(output.mime || '').startsWith('image/')) {
        try {
          url = await fetchResourceBlob(resourceApi.thumbUrl(output.id))
        } catch {
          url = await fetchResourceBlob(resourceApi.fileUrl(output.id))
        }
      }
      return {
        id: output.id,
        filename: output.filename,
        media_type: output.media_type,
        mime: output.mime || '',
        url,
        width: output.width,
        height: output.height,
      } as TaskOutput
    }))
  } catch {
    taskOutputs.value[taskId] = []
  } finally {
    delete outputLoading.value[taskId]
  }
}

async function loadTaskPreviews(items: TaskItem[]) {
  const candidates = items.filter((task) => task.status === 'SUCCESS' && !(task.id in taskOutputs.value))
  let cursor = 0
  async function worker() {
    while (cursor < candidates.length) {
      const task = candidates[cursor++]
      await loadTaskOutputs(task.id)
    }
  }
  await Promise.all(Array.from({ length: Math.min(6, candidates.length) }, () => worker()))
}

async function openOutput(output: TaskOutput) {
  resetImageView()
  previewOutput.value = output
  previewLoading.value = true
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  try {
    previewUrl.value = await fetchResourceBlob(resourceApi.fileUrl(output.id))
  } catch {
    message.error('预览资源加载失败')
  } finally {
    previewLoading.value = false
  }
}

function closeOutputPreview() {
  resetImageView()
  previewOutput.value = null
  previewLoading.value = false
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
}

function resetImageView() {
  imageScale.value = 1
  imageOffsetX.value = 0
  imageOffsetY.value = 0
  imageDragging.value = false
}

function setImageScale(nextScale: number) {
  imageScale.value = Math.min(5, Math.max(0.25, Math.round(nextScale * 100) / 100))
  if (imageScale.value <= 1) {
    imageOffsetX.value = 0
    imageOffsetY.value = 0
  }
}

function zoomImage(delta: number) {
  setImageScale(imageScale.value + delta)
}

function onImageWheel(event: WheelEvent) {
  event.preventDefault()
  setImageScale(imageScale.value * (event.deltaY < 0 ? 1.12 : 0.88))
}

function startImageDrag(event: PointerEvent) {
  if (imageScale.value <= 1) return
  imageDragging.value = true
  imageDragStartX = event.clientX
  imageDragStartY = event.clientY
  imageDragOriginX = imageOffsetX.value
  imageDragOriginY = imageOffsetY.value
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}

function moveImageDrag(event: PointerEvent) {
  if (!imageDragging.value) return
  imageOffsetX.value = imageDragOriginX + event.clientX - imageDragStartX
  imageOffsetY.value = imageDragOriginY + event.clientY - imageDragStartY
}

function endImageDrag(event?: PointerEvent) {
  imageDragging.value = false
  if (event && (event.currentTarget as HTMLElement).hasPointerCapture(event.pointerId)) {
    ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
  }
}

function durationText(task: TaskItem) {
  if (!task.started_at) return '—'
  const end = task.finished_at ? new Date(task.finished_at).getTime() : Date.now()
  const start = new Date(task.started_at).getTime()
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return '—'
  const seconds = Math.round((end - start) / 100) / 10
  return `${seconds} 秒`
}

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value)
}

function detailParamType(key: string): string | undefined {
  if (!detailTask.value?.generation_type_id) return undefined
  const generationType = generationTypes.value.find((item) => item.id === detailTask.value?.generation_type_id)
  const schema = Array.isArray(generationType?.param_template) ? generationType.param_template : []
  return schema.find((item: any) => item.key === key)?.type
}

function isReadonlyMediaParam(key: string): boolean {
  return ['image', 'video', 'audio'].includes(detailParamType(key) || '')
}

function mediaParamLabel(key: string): string {
  const labels: Record<string, string> = { image: '图片素材', video: '视频素材', audio: '音频素材' }
  return labels[detailParamType(key) || ''] || '多媒体素材'
}

function clearDetailMediaPreviews() {
  for (const preview of Object.values(detailMediaPreviews.value)) {
    if (preview.url) URL.revokeObjectURL(preview.url)
  }
  detailMediaPreviews.value = {}
  detailMediaLoading.value = {}
}

async function loadDetailMediaPreviews(params: Record<string, unknown>) {
  clearDetailMediaPreviews()
  await Promise.all(Object.entries(params).map(async ([key, value]) => {
    if (!isReadonlyMediaParam(key)) return
    const id = Number(value)
    const mediaType = detailParamType(key) as TaskOutput['media_type']
    if (!Number.isInteger(id) || id <= 0) return
    detailMediaLoading.value[key] = true
    try {
      const url = mediaType === 'audio'
        ? await fetchResourceBlob(resourceApi.fileUrl(id))
        : await fetchResourceBlob(resourceApi.thumbUrl(id)).catch(() => fetchResourceBlob(resourceApi.fileUrl(id)))
      detailMediaPreviews.value[key] = {
        id,
        filename: `${mediaParamLabel(key)} #${id}`,
        media_type: mediaType,
        mime: '',
        url,
      }
    } catch {
      // 单个素材预览失败时仍保留素材 ID，不影响详情中的其他参数。
    } finally {
      delete detailMediaLoading.value[key]
    }
  }))
}

async function openTaskDetail(row: TaskItem) {
  detailTask.value = row
  detailEvents.value = []
  detailLoading.value = true
  try {
    const [task, events] = await Promise.all([
      taskApi.get(row.id),
      taskApi.events(row.id),
      loadTaskOutputs(row.id),
    ])
    detailTask.value = task
    detailParamObjectKeys.value = new Set(
      Object.entries(task.params || {}).filter(([, value]) => typeof value === 'object' && value !== null).map(([key]) => key),
    )
    detailParamDraft.value = Object.fromEntries(
      Object.entries(task.params || {}).map(([key, value]) => [
        key,
        typeof value === 'object' && value !== null ? JSON.stringify(value, null, 2) : value,
      ]),
    )
    await loadDetailMediaPreviews(task.params || {})
    detailEvents.value = events
  } catch {
    message.error('加载任务详情失败')
  } finally {
    detailLoading.value = false
  }
}

function closeTaskDetail() {
  clearDetailMediaPreviews()
  detailTask.value = null
  detailEvents.value = []
  detailLoading.value = false
  detailExecuting.value = false
  detailParamDraft.value = {}
  detailParamObjectKeys.value = new Set()
}

async function executeDetailTask() {
  if (!detailTask.value) return
  const params: Record<string, unknown> = { ...detailParamDraft.value }
  try {
    for (const key of detailParamObjectKeys.value) {
      const value = params[key]
      params[key] = typeof value === 'string' ? JSON.parse(value) : value
    }
  } catch {
    message.error('JSON 参数格式不正确，请检查后再执行')
    return
  }
  detailExecuting.value = true
  try {
    const created = await taskApi.execute(detailTask.value.id, params)
    message.success(`已创建新任务 #${created.id}`)
    closeTaskDetail()
    await load()
  } catch (error: any) {
    message.error(error.response?.data?.detail || '创建执行任务失败')
  } finally {
    detailExecuting.value = false
  }
}

async function load() {
  loading.value = true
  try {
    const params: Record<string, unknown> = { limit: 500 }
    if (statusFilter.value) params.status = statusFilter.value
    if (generationTypeFilter.value) params.generation_type_id = generationTypeFilter.value
    if (dateRange.value) {
      params.created_from = new Date(dateRange.value[0]).toISOString()
      params.created_to = new Date(dateRange.value[1]).toISOString()
    }
    tasks.value = await taskApi.list(params)
    const currentIds = new Set(tasks.value.map((task) => task.id))
    for (const id of Object.keys(taskOutputs.value).map(Number)) {
      if (!currentIds.has(id)) clearTaskOutputs(id)
    }
    void loadTaskPreviews(tasks.value)
  } catch {
    message.error('加载任务失败')
  } finally {
    loading.value = false
  }
}

async function loadGenerationTypes() {
  try {
    generationTypes.value = await genTypeApi.list()
    generationTypeNames.value = Object.fromEntries(
      generationTypes.value.map((item) => [item.id, item.name]),
    )
  } catch {
    message.error('加载生成类型失败')
  }
}

const generationTypeOptions = computed(() => [
  { label: '全部类型', value: 0 },
  ...generationTypes.value.map((item) => ({ label: item.name, value: item.id })),
])

function scheduleReload() {
  if (reloadTimer) clearTimeout(reloadTimer)
  reloadTimer = setTimeout(() => void load(), 250)
}

onMounted(async () => {
  await Promise.all([loadGenerationTypes(), load()])
  if (getAccessToken()) connectWs()
  off = onWsEvent(scheduleReload)
})

onUnmounted(() => {
  off?.()
  if (reloadTimer) clearTimeout(reloadTimer)
  closeOutputPreview()
  for (const id of Object.keys(taskOutputs.value).map(Number)) clearTaskOutputs(id)
})

const filteredTasks = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  return tasks.value.filter((task) => {
    if (!query) return true
    return [
      task.id,
      task.batch_id,
      task.row_no,
      promptText(task),
      task.error || '',
    ].some((value) => String(value).toLowerCase().includes(query))
  })
})

async function cancel(id: number) {
  actionTaskId.value = id
  try {
    await taskApi.cancel(id)
    message.success(`任务 #${id} 已取消`)
    await load()
  } catch {
    message.error('取消任务失败')
  } finally {
    actionTaskId.value = null
  }
}

async function retry(id: number) {
  actionTaskId.value = id
  try {
    await taskApi.retry(id)
    message.success(`任务 #${id} 已重新排队`)
    await load()
  } catch {
    message.error('重试任务失败')
  } finally {
    actionTaskId.value = null
  }
}

async function regenerate(id: number) {
  actionTaskId.value = id
  try {
    const regenerated = await taskApi.regenerate(id)
    message.success(`已创建重新生成任务 #${regenerated.id}`)
    await load()
  } catch (error: any) {
    message.error(error.response?.data?.detail || '重新生成任务失败')
  } finally {
    actionTaskId.value = null
  }
}

async function removeDraft(id: number) {
  if (!globalThis.confirm(`确定删除草稿任务 #${id}？`)) return
  actionTaskId.value = id
  try {
    await taskApi.delete(id)
    message.success(`草稿任务 #${id} 已删除`)
    await load()
  } catch (error: any) {
    message.error(error.response?.data?.detail || '删除任务失败')
  } finally {
    actionTaskId.value = null
  }
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = null
  generationTypeFilter.value = null
  dateRange.value = getTodayRange()
  void load()
}

const columns: DataTableColumns<TaskItem> = [
  {
    title: '任务 ID',
    key: 'id',
    width: 90,
    sorter: (a, b) => a.id - b.id,
    render: (row) => h(NText, { strong: true }, { default: () => `#${row.id}` }),
  },
  {
    title: '状态',
    key: 'status',
    width: 100,
    render: (row) => h(NTag, { size: 'small', type: statusType(row.status) }, {
      default: () => statusLabels[row.status] || row.status,
    }),
  },
  {
    title: '提示词',
    key: 'prompt',
    minWidth: 240,
    ellipsis: { tooltip: true },
    render: (row) => promptText(row),
  },
  {
    title: '预览',
    key: 'preview',
    width: 190,
    render: (row) => {
      if (outputLoading.value[row.id]) return h(NSpin, { size: 'small' })
      const outputs = taskOutputs.value[row.id] || []
      if (!outputs.length) return '—'
      return h('div', { class: 'flex flex-wrap gap-1' }, [
        ...outputs.slice(0, 3).map((output) => {
          if (output.media_type === 'image' || output.mime.startsWith('image/')) {
            return h('img', { src: output.url, alt: output.filename, title: '点击放大', class: 'w-14 h-14 object-contain bg-gray-100 rounded cursor-pointer', onClick: () => void openOutput(output) })
          }
          if (output.media_type === 'video') {
            return h('button', {
              title: '点击播放',
              class: 'relative w-14 h-14 bg-gray-100 rounded overflow-hidden cursor-pointer',
              onClick: () => void openOutput(output),
            }, [
              h('img', { src: output.url, alt: output.filename, class: 'w-full h-full object-contain' }),
              h('span', { class: 'absolute inset-0 flex items-center justify-center text-white text-lg bg-black/20' }, '▶'),
            ])
          }
          return h(NButton, {
            size: 'tiny',
            onClick: () => void openOutput(output),
          }, { default: () => output.media_type === 'video' ? '视频' : '音频' })
        }),
        outputs.length > 3 ? h(NText, { depth: 3 }, { default: () => `+${outputs.length - 3}` }) : null,
      ])
    },
  },
  { title: '批次', key: 'batch_id', width: 80, sorter: (a, b) => a.batch_id - b.batch_id },
  { title: '行号', key: 'row_no', width: 75, sorter: (a, b) => a.row_no - b.row_no },
  {
    title: '生成类型',
    key: 'generation_type_id',
    width: 130,
    render: (row) => row.generation_type_id
      ? (generationTypeNames.value[row.generation_type_id] || `未知类型 #${row.generation_type_id}`)
      : '—',
  },
  { title: '节点', key: 'node_id', width: 75, render: (row) => row.node_id ?? '—' },
  { title: '重试', key: 'retries', width: 70, sorter: (a, b) => a.retries - b.retries },
  {
    title: '创建时间',
    key: 'created_at',
    width: 170,
    sorter: (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    render: (row) => formatDate(row.created_at),
  },
  {
    title: '开始时间',
    key: 'started_at',
    width: 170,
    render: (row) => formatDate(row.started_at),
  },
  {
    title: '完成时间',
    key: 'finished_at',
    width: 170,
    render: (row) => formatDate(row.finished_at),
  },
  {
    title: '错误信息',
    key: 'error',
    minWidth: 180,
    ellipsis: { tooltip: true },
    render: (row) => row.error || '—',
  },
  {
    title: '操作',
    key: 'actions',
    width: 180,
    fixed: 'right',
    render: (row) => h(NSpace, { size: 6 }, {
      default: () => [
        h(NButton, {
          size: 'tiny',
          onClick: () => void openTaskDetail(row),
        }, { default: () => '详情' }),
        ['PENDING', 'DISPATCHING', 'QUEUED', 'RUNNING'].includes(row.status)
          ? h(NButton, {
              size: 'tiny',
              loading: actionTaskId.value === row.id,
              onClick: () => void cancel(row.id),
            }, { default: () => '取消' })
          : null,
        row.status === 'CANCELLED'
          ? h(NButton, {
              size: 'tiny',
              type: 'warning',
              loading: actionTaskId.value === row.id,
              onClick: () => void retry(row.id),
            }, { default: () => '重试' })
          : null,
        ['SUCCESS', 'FAILED'].includes(row.status)
          ? h(NButton, {
              size: 'tiny',
              type: 'primary',
              loading: actionTaskId.value === row.id,
              onClick: () => void regenerate(row.id),
            }, { default: () => '重新生成' })
          : null,
        row.status === 'DRAFT'
          ? h(NButton, {
              size: 'tiny',
              type: 'error',
              loading: actionTaskId.value === row.id,
              onClick: () => void removeDraft(row.id),
            }, { default: () => '删除' })
          : null,
      ],
    }),
  },
]

const pagination = {
  pageSize: 20,
  showSizePicker: true,
  pageSizes: [20, 50, 100],
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <NH2 style="margin: 0">任务管理</NH2>
        <NText depth="3">共 {{ filteredTasks.length }} 条任务</NText>
      </div>
      <NButton :loading="loading" @click="load">刷新</NButton>
    </div>

    <NCard size="small">
      <div class="flex flex-wrap gap-3 mb-4">
        <NInput
          v-model:value="keyword"
          clearable
          placeholder="搜索任务 ID、批次、提示词或错误"
          style="width: min(100%, 320px)"
        />
        <NSelect
          v-model:value="statusFilter"
          clearable
          :options="statusOptions"
          placeholder="全部状态"
          style="width: 160px"
        />
        <NSelect
          v-model:value="generationTypeFilter"
          clearable
          :options="generationTypeOptions"
          placeholder="全部生成类型"
          style="width: 180px"
        />
        <NDatePicker
          v-model:value="dateRange"
          type="daterange"
          clearable
          style="width: 270px"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
        />
        <NButton type="primary" :loading="loading" @click="load">查询</NButton>
        <NButton @click="resetFilters">重置</NButton>
      </div>

      <NDataTable
        :columns="columns"
        :data="filteredTasks"
        :loading="loading"
        :pagination="pagination"
        :row-key="(row: TaskItem) => row.id"
        :scroll-x="2020"
        striped
      />
    </NCard>

    <NModal
      :show="!!detailTask"
      @update:show="closeTaskDetail"
      preset="card"
      :title="`任务详情 #${detailTask?.id || ''}`"
      style="width: 94%; max-width: 1100px"
    >
      <NSpin :show="detailLoading">
        <div v-if="detailTask" class="space-y-5">
          <NCard title="参数信息" size="small">
            <template #header-extra>
              <NButton type="primary" size="small" :loading="detailExecuting" @click="executeDetailTask">执行（新任务）</NButton>
            </template>
            <div v-if="Object.keys(detailTask.params || {}).length" class="divide-y border rounded">
              <div v-for="(value, key) in detailTask.params" :key="key" class="grid grid-cols-[180px_minmax(0,1fr)] gap-3 p-2 text-sm">
                <NText strong>{{ key }}</NText>
                <div v-if="isReadonlyMediaParam(String(key))" class="space-y-2 min-h-8">
                  <div class="flex items-center gap-2">
                    <NTag size="small">{{ mediaParamLabel(String(key)) }}</NTag>
                    <NText>素材 #{{ value }}</NText>
                    <NText depth="3">（不可修改）</NText>
                  </div>
                  <NSpin v-if="detailMediaLoading[String(key)]" size="small" />
                  <img
                    v-else-if="detailMediaPreviews[String(key)]?.media_type === 'image'"
                    :src="detailMediaPreviews[String(key)].url"
                    class="w-40 h-32 object-contain bg-gray-100 rounded cursor-pointer"
                    @click="openOutput(detailMediaPreviews[String(key)])"
                  />
                  <button
                    v-else-if="detailMediaPreviews[String(key)]?.media_type === 'video'"
                    class="relative w-40 h-32 bg-gray-100 rounded overflow-hidden cursor-pointer"
                    @click="openOutput(detailMediaPreviews[String(key)])"
                  >
                    <img :src="detailMediaPreviews[String(key)].url" class="w-full h-full object-contain" />
                    <span class="absolute inset-0 flex items-center justify-center text-white text-3xl bg-black/20">▶</span>
                  </button>
                  <audio
                    v-else-if="detailMediaPreviews[String(key)]?.media_type === 'audio'"
                    :src="detailMediaPreviews[String(key)].url"
                    controls
                    class="w-full max-w-md"
                  />
                  <NText v-else depth="3">预览加载失败或素材不存在</NText>
                </div>
                <NCheckbox v-else-if="typeof value === 'boolean'" v-model:checked="detailParamDraft[key]">{{ detailParamDraft[key] ? '是' : '否' }}</NCheckbox>
                <NInputNumber v-else-if="typeof value === 'number'" v-model:value="detailParamDraft[key]" style="width: 100%" />
                <NInput v-else-if="typeof value === 'object' && value !== null" v-model:value="detailParamDraft[key]" type="textarea" :rows="4" />
                <NInput v-else v-model:value="detailParamDraft[key]" type="textarea" :autosize="{ minRows: 1, maxRows: 5 }" />
              </div>
            </div>
            <NText v-else depth="3">暂无参数</NText>
          </NCard>

          <NCard title="运行信息" size="small">
            <NDescriptions bordered label-placement="left" :column="2">
              <NDescriptionsItem label="任务状态">
                <NTag size="small" :type="statusType(detailTask.status)">{{ statusLabels[detailTask.status] || detailTask.status }}</NTag>
              </NDescriptionsItem>
              <NDescriptionsItem label="生成类型">{{ detailTask.generation_type_id ? (generationTypeNames[detailTask.generation_type_id] || `#${detailTask.generation_type_id}`) : '—' }}</NDescriptionsItem>
              <NDescriptionsItem label="批次/行号">#{{ detailTask.batch_id }} / {{ detailTask.row_no + 1 }}</NDescriptionsItem>
              <NDescriptionsItem label="工作流版本">{{ detailTask.workflow_version_id ? `#${detailTask.workflow_version_id}` : '—' }}</NDescriptionsItem>
              <NDescriptionsItem label="执行节点">{{ detailTask.node_id ? `#${detailTask.node_id}` : '—' }}</NDescriptionsItem>
              <NDescriptionsItem label="ComfyUI Prompt ID"><span class="break-all">{{ detailTask.prompt_id || '—' }}</span></NDescriptionsItem>
              <NDescriptionsItem label="优先级">{{ detailTask.priority }}</NDescriptionsItem>
              <NDescriptionsItem label="重试次数">{{ detailTask.retries }}</NDescriptionsItem>
              <NDescriptionsItem label="创建时间">{{ formatDate(detailTask.created_at) }}</NDescriptionsItem>
              <NDescriptionsItem label="开始时间">{{ formatDate(detailTask.started_at) }}</NDescriptionsItem>
              <NDescriptionsItem label="完成时间">{{ formatDate(detailTask.finished_at) }}</NDescriptionsItem>
              <NDescriptionsItem label="运行耗时">{{ durationText(detailTask) }}</NDescriptionsItem>
              <NDescriptionsItem v-if="detailTask.error" label="错误信息" :span="2">
                <NText type="error">{{ detailTask.error }}</NText>
              </NDescriptionsItem>
            </NDescriptions>

            <div class="mt-4">
              <NText strong>执行事件</NText>
              <div v-if="detailEvents.length" class="mt-2 divide-y border rounded max-h-72 overflow-auto">
                <div v-for="event in detailEvents" :key="event.id" class="grid grid-cols-[170px_100px_70px_minmax(0,1fr)] gap-3 p-2 text-xs items-start">
                  <span>{{ formatDate(event.created_at) }}</span>
                  <NTag size="tiny">{{ event.type }}</NTag>
                  <span>{{ event.progress }}%</span>
                  <pre class="m-0 whitespace-pre-wrap break-all">{{ displayValue(event.payload) }}</pre>
                </div>
              </div>
              <NText v-else depth="3" class="block mt-2">暂无执行事件</NText>
            </div>
          </NCard>

          <NCard title="执行结果" size="small">
            <div v-if="(taskOutputs[detailTask.id] || []).length" class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
              <button
                v-for="output in taskOutputs[detailTask.id]"
                :key="output.id"
                class="border rounded p-2 text-left hover:border-blue-500"
                @click="openOutput(output)"
              >
                <div class="h-36 bg-gray-100 rounded flex items-center justify-center overflow-hidden">
                  <img v-if="output.media_type === 'image' || output.mime.startsWith('image/')" :src="output.url" class="w-full h-full object-contain" />
                  <div v-else-if="output.media_type === 'video'" class="relative w-full h-full">
                    <img :src="output.url" class="w-full h-full object-contain" />
                    <span class="absolute inset-0 flex items-center justify-center text-white text-3xl bg-black/20">▶</span>
                  </div>
                  <span v-else class="text-gray-500">音频 ▶</span>
                </div>
                <div class="mt-2 text-sm truncate" :title="output.filename">{{ output.filename }}</div>
                <div class="text-xs text-gray-500">
                  {{ output.media_type }}<template v-if="output.width && output.height"> · {{ output.width }}×{{ output.height }}</template>
                </div>
              </button>
            </div>
            <NSpin v-else-if="outputLoading[detailTask.id]" size="small" />
            <NText v-else depth="3">暂无执行结果</NText>
          </NCard>
        </div>
      </NSpin>
    </NModal>

    <NModal
      :show="!!previewOutput"
      @update:show="closeOutputPreview"
      preset="card"
      :title="previewOutput?.filename || '任务预览'"
      style="width: 94%; max-width: 1200px"
    >
      <NSpin :show="previewLoading">
        <div
          v-if="previewUrl && (previewOutput?.media_type === 'image' || previewOutput?.mime.startsWith('image/'))"
          class="relative flex items-center justify-center bg-gray-100 rounded h-[78vh] overflow-hidden select-none touch-none"
          :class="imageScale > 1 ? (imageDragging ? 'cursor-grabbing' : 'cursor-grab') : 'cursor-default'"
          @wheel="onImageWheel"
          @pointerdown="startImageDrag"
          @pointermove="moveImageDrag"
          @pointerup="endImageDrag"
          @pointercancel="endImageDrag"
          @dblclick="resetImageView"
        >
          <div class="absolute top-3 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1 rounded-lg bg-black/65 p-1 text-white shadow-lg">
            <NButton size="small" quaternary style="color: white" @click.stop="zoomImage(-0.25)">−</NButton>
            <span class="w-14 text-center text-xs">{{ Math.round(imageScale * 100) }}%</span>
            <NButton size="small" quaternary style="color: white" @click.stop="zoomImage(0.25)">＋</NButton>
            <NButton size="small" quaternary style="color: white" @click.stop="resetImageView">适应</NButton>
          </div>
          <img
            :src="previewUrl"
            :alt="previewOutput?.filename"
            draggable="false"
            class="max-w-full max-h-full object-contain will-change-transform"
            :style="{
              transform: `translate(${imageOffsetX}px, ${imageOffsetY}px) scale(${imageScale})`,
              transition: imageDragging ? 'none' : 'transform 120ms ease-out',
            }"
          />
          <div class="absolute bottom-3 left-1/2 -translate-x-1/2 rounded bg-black/55 px-3 py-1 text-xs text-white pointer-events-none">
            滚轮缩放 · 放大后拖动 · 双击复位
          </div>
        </div>
        <div v-else class="flex items-center justify-center bg-gray-100 rounded min-h-48">
          <video
            v-if="previewUrl && previewOutput?.media_type === 'video'"
            :src="previewUrl"
            controls
            autoplay
            class="max-w-full max-h-[78vh]"
          />
          <audio
            v-else-if="previewUrl && previewOutput?.media_type === 'audio'"
            :src="previewUrl"
            controls
            autoplay
            class="w-full m-8"
          />
        </div>
      </NSpin>
    </NModal>
  </div>
</template>
