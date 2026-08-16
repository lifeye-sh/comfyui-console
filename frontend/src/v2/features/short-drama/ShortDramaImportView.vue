<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { shortDramaApi, type CreativeJob, type ShortDramaDocument, type ShortDramaProject } from '@/api/modules'
import GlassPanel from '@/v2/components/GlassPanel.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => Number(route.params.id))
const project = ref<ShortDramaProject | null>(null)
const documents = ref<ShortDramaDocument[]>([])
const jobs = ref<CreativeJob[]>([])
const selectedFile = ref<File | null>(null)
const dragging = ref(false)
const uploading = ref(false)
const uploadProgress = ref(0)
const error = ref('')
const expandedJob = ref<number | null>(null)
let pollTimer: ReturnType<typeof setTimeout> | null = null

const active = computed(() => jobs.value.some((item) => ['queued', 'running', 'cancelling'].includes(item.status)))
const statusText: Record<string, string> = { pending: '等待解析', parsing: '解析中', ready: '已就绪', queued: '排队中', running: '解析中', cancelling: '取消中', succeeded: '已完成', failed: '失败', cancelled: '已取消' }
const statusTone = (status: string) => status === 'succeeded' ? 'success' : status === 'failed' ? 'danger' : status === 'cancelled' ? 'neutral' : 'warning'
const formatSize = (value: number) => value < 10000 ? `${value} 字` : `${(value / 10000).toFixed(1)} 万字`

function chooseFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) validateFile(file)
}
function dropFile(event: DragEvent) {
  dragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) validateFile(file)
}
function validateFile(file: File) {
  error.value = ''
  const extension = file.name.split('.').pop()?.toLowerCase()
  if (!extension || !['txt', 'docx', 'epub'].includes(extension)) { error.value = '请选择 TXT、DOCX 或 EPUB 文件'; return }
  if (file.size > 50 * 1024 * 1024) { error.value = '文件不能超过 50MB'; return }
  selectedFile.value = file
}
async function load(showError = true) {
  try {
    const [projectData, documentData, jobData] = await Promise.all([
      shortDramaApi.project(projectId.value), shortDramaApi.documents(projectId.value), shortDramaApi.jobs({ project_id: projectId.value, page_size: 20 }),
    ])
    project.value = projectData
    documents.value = documentData
    jobs.value = jobData.items
  } catch (event: any) {
    if (showError) error.value = event.response?.data?.detail || '导入工作台加载失败'
  }
  schedulePoll()
}
function schedulePoll() {
  if (pollTimer) clearTimeout(pollTimer)
  if (active.value) pollTimer = setTimeout(() => void load(false), 1500)
}
async function upload() {
  if (!selectedFile.value || uploading.value) return
  uploading.value = true
  uploadProgress.value = 0
  error.value = ''
  try {
    await shortDramaApi.importDocument(projectId.value, selectedFile.value, (value) => { uploadProgress.value = value })
    selectedFile.value = null
    uploadProgress.value = 100
    await load()
  } catch (event: any) {
    error.value = event.response?.data?.detail || '文档上传失败'
  } finally {
    uploading.value = false
  }
}
async function cancel(job: CreativeJob) {
  try { await shortDramaApi.cancelJob(job.id); await load() }
  catch (event: any) { error.value = event.response?.data?.detail || '取消失败' }
}
async function retry(job: CreativeJob) {
  try { await shortDramaApi.retryJob(job.id); await load() }
  catch (event: any) { error.value = event.response?.data?.detail || '重试失败' }
}
onMounted(() => void load())
onBeforeUnmount(() => { if (pollTimer) clearTimeout(pollTimer) })
</script>

<template>
  <div class="v2-page import-page">
    <header class="page-head">
      <div><button class="back" @click="router.push(`/v2/drama/projects/${projectId}`)">← 返回项目概览</button><h1>导入故事文档</h1><p>{{ project?.name || '短剧项目' }} · 原文件保存到素材库，解析由独立 Story Worker 执行。</p></div>
      <div class="head-actions"><StatusBadge tone="info">V2.1 · 文档解析</StatusBadge><V2Button variant="primary" :disabled="!documents.some(item=>item.status==='ready')" @click="router.push(`/v2/drama/projects/${projectId}/screenplay`)">进入剧本工作台</V2Button></div>
    </header>

    <p v-if="error" class="error-banner">{{ error }}</p>
    <GlassPanel title="上传原稿" description="支持 TXT、DOCX、EPUB，单个文件不超过 50MB；重复上传同一文件不会创建重复任务。">
      <div class="drop-zone" :class="{ dragging }" @dragover.prevent="dragging=true" @dragleave.prevent="dragging=false" @drop.prevent="dropFile">
        <input id="story-file" type="file" accept=".txt,.docx,.epub" @change="chooseFile">
        <div class="file-icon">文</div>
        <div><strong>{{ selectedFile?.name || '拖放故事文档到这里' }}</strong><p>{{ selectedFile ? `${(selectedFile.size / 1024 / 1024).toFixed(2)} MB · 等待上传` : '也可以点击选择本地文件' }}</p></div>
        <label for="story-file" class="pick-button">选择文件</label>
      </div>
      <div v-if="uploading" class="upload-progress"><span :style="{width:`${uploadProgress}%`}"></span></div>
      <template #actions><V2Button variant="primary" :disabled="!selectedFile||uploading" @click="upload">{{ uploading ? `上传中 ${uploadProgress}%` : '上传并开始解析' }}</V2Button></template>
    </GlassPanel>

    <div class="workspace-grid">
      <GlassPanel title="解析任务" :description="`共 ${jobs.length} 条任务`">
        <div v-if="!jobs.length" class="empty">上传文档后，解析进度和日志会显示在这里。</div>
        <article v-for="job in jobs" :key="job.id" class="job-row">
          <div class="job-main"><button class="expand" @click="expandedJob=expandedJob===job.id?null:job.id">{{ expandedJob===job.id?'−':'+' }}</button><div><strong>{{ job.input_payload.filename || `任务 #${job.id}` }}</strong><small>#{{ job.id }} · {{ new Date(job.created_at).toLocaleString() }}</small></div><StatusBadge :tone="statusTone(job.status)">{{ statusText[job.status] || job.status }}</StatusBadge></div>
          <div class="progress"><span :style="{width:`${job.progress}%`}"></span></div>
          <div class="job-foot"><span>{{ job.progress }}%</span><span v-if="job.error" class="danger">{{ job.error }}</span><span class="grow"></span><button v-if="['queued','running'].includes(job.status)" @click="cancel(job)">取消</button><button v-if="['failed','cancelled'].includes(job.status)" @click="retry(job)">重新解析</button></div>
          <div v-if="expandedJob===job.id" class="logs"><p v-for="(log,index) in job.logs" :key="index"><time>{{ log.time }}</time><span :class="log.level">{{ log.message }}</span></p></div>
        </article>
      </GlassPanel>

      <GlassPanel title="已导入文档" :description="`共 ${documents.length} 个原稿`">
        <div v-if="!documents.length" class="empty">还没有导入文档。</div>
        <article v-for="document in documents" :key="document.id" class="document-row">
          <div class="format">{{ document.source_format.toUpperCase() }}</div><div class="document-copy"><strong>{{ document.title || document.filename }}</strong><small>{{ document.filename }}</small><p v-if="document.status==='ready'">{{ document.total_chapters }} 章 · {{ document.total_paragraphs }} 段 · {{ formatSize(document.total_chars) }}</p><p v-else>{{ statusText[document.status] || document.status }}</p></div>
        </article>
      </GlassPanel>
    </div>
  </div>
</template>

<style scoped>
.import-page{display:grid;gap:18px}.page-head{display:flex;align-items:flex-start;justify-content:space-between;gap:20px}.page-head h1{margin:14px 0 6px;font-size:32px}.page-head p{margin:0;color:var(--v2-text-muted)}.back{padding:0;color:var(--v2-text-muted);background:none;border:0;cursor:pointer}.error-banner{margin:0;padding:12px 14px;color:var(--v2-danger);background:rgba(255,90,120,.09);border:1px solid rgba(255,90,120,.2);border-radius:12px}.drop-zone{position:relative;min-height:190px;padding:28px;display:flex;align-items:center;justify-content:center;gap:18px;text-align:left;background:var(--v2-surface-soft);border:1px dashed var(--v2-border);border-radius:16px;transition:.2s}.drop-zone.dragging{border-color:var(--v2-primary);background:rgba(102,126,234,.1)}.drop-zone input{position:absolute;width:1px;height:1px;opacity:0}.file-icon,.format{display:grid;place-items:center;color:white;background:linear-gradient(145deg,#7b8cff,#a167e8);border-radius:14px;font-weight:700}.file-icon{width:58px;height:68px;font-size:20px}.drop-zone strong{font-size:17px}.drop-zone p{margin:6px 0 0;color:var(--v2-text-muted)}.pick-button{padding:10px 16px;color:var(--v2-text);background:var(--v2-surface);border:1px solid var(--v2-border);border-radius:10px;cursor:pointer}.upload-progress,.progress{overflow:hidden;background:rgba(255,255,255,.07);border-radius:99px}.upload-progress{height:5px;margin-top:12px}.progress{height:4px}.upload-progress span,.progress span{display:block;height:100%;background:linear-gradient(90deg,#6f86ff,#aa70e8);transition:width .3s}.workspace-grid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(320px,.85fr);gap:18px}.empty{padding:30px;text-align:center;color:var(--v2-text-muted)}.job-row,.document-row{padding:14px;border:1px solid var(--v2-border);border-radius:13px;background:var(--v2-surface-soft)}.job-row+.job-row,.document-row+.document-row{margin-top:10px}.job-main{display:flex;align-items:center;gap:10px;margin-bottom:11px}.job-main>div:nth-child(2){display:grid;gap:3px;min-width:0}.job-main strong,.document-copy strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.job-main small,.document-copy small{color:var(--v2-text-muted)}.job-main .status-badge{margin-left:auto}.expand,.job-foot button{color:var(--v2-text-muted);background:none;border:1px solid var(--v2-border);border-radius:7px;cursor:pointer}.expand{width:25px;height:25px}.job-foot{margin-top:8px;display:flex;align-items:center;gap:9px;color:var(--v2-text-muted);font-size:12px}.job-foot .grow{flex:1}.job-foot button{padding:5px 9px}.danger{color:var(--v2-danger)}.logs{max-height:190px;overflow:auto;margin-top:12px;padding:9px 11px;background:rgba(0,0,0,.18);border-radius:9px}.logs p{margin:5px 0;display:grid;grid-template-columns:140px 1fr;gap:8px;font-size:12px}.logs time{color:var(--v2-text-subtle)}.logs .error{color:var(--v2-danger)}.logs .warning{color:var(--v2-warning)}.document-row{display:flex;gap:12px}.format{flex:0 0 48px;height:48px;border-radius:10px;font-size:11px}.document-copy{display:grid;min-width:0;gap:3px}.document-copy p{margin:3px 0 0;color:var(--v2-text-muted);font-size:12px}@media(max-width:900px){.workspace-grid{grid-template-columns:1fr}}@media(max-width:620px){.page-head{flex-direction:column}.drop-zone{min-height:230px;flex-direction:column;text-align:center}.pick-button{width:100%;text-align:center}.logs p{grid-template-columns:1fr}.page-head h1{font-size:27px}}
.head-actions{display:flex;align-items:center;gap:10px}
</style>
