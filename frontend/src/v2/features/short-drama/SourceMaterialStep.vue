<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { shortDramaApi, type CreativeJob, type ShortDramaDocument } from '@/api/modules'
import GlassPanel from '@/v2/components/GlassPanel.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'

const props = defineProps<{ projectId: number }>()
const emit = defineEmits<{ (e: 'edit-prompt', code: string, title: string): void; (e: 'job-created'): void }>()
const router = useRouter()

const documents = ref<ShortDramaDocument[]>([])
const jobs = ref<CreativeJob[]>([])
const selectedFile = ref<File | null>(null)
const dragging = ref(false)
const uploading = ref(false)
const uploadProgress = ref(0)
const errorMsg = ref('')
const expandedJob = ref<number | null>(null)
const analyses = ref<any[]>([])
const expandedAnalysis = ref<number | null>(null)
let pollTimer: ReturnType<typeof setTimeout> | null = null

const active = computed(() => jobs.value.some((item) => ['queued', 'running', 'cancelling'].includes(item.status)))
const readyDocuments = computed(() => documents.value.filter(d => d.status === 'ready'))

const statusText: Record<string, string> = {
  pending: '等待解析', parsing: '解析中', ready: '已就绪',
  queued: '排队中', running: '执行中', cancelling: '取消中',
  succeeded: '已完成', failed: '失败', cancelled: '已取消',
}
const statusTone = (s: string) => s === 'succeeded' || s === 'ready' ? 'success' : s === 'failed' ? 'danger' : s === 'cancelled' ? 'neutral' : 'warning'
const formatSize = (v: number) => v < 10000 ? `${v} 字` : `${(v / 10000).toFixed(1)} 万字`

function analysisSummary(content: any): string {
  if (!content || typeof content !== 'object' || Object.keys(content).length === 0) return '内容为空'
  const parts: string[] = []
  if (content.synopsis) parts.push(`概要: ${String(content.synopsis).slice(0, 80)}…`)
  if (content.characters?.length) parts.push(`角色 ${content.characters.length}`)
  if (content.locations?.length) parts.push(`地点 ${content.locations.length}`)
  if (content.events?.length) parts.push(`事件 ${content.events.length}`)
  if (content.timeline?.length) parts.push(`时间线 ${content.timeline.length}`)
  return parts.join(' · ') || '无摘要'
}

function toggleAnalysis(id: number) {
  expandedAnalysis.value = expandedAnalysis.value === id ? null : id
}

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
  errorMsg.value = ''
  const ext = file.name.split('.').pop()?.toLowerCase()
  if (!ext || !['txt', 'docx', 'epub'].includes(ext)) { errorMsg.value = '请选择 TXT、DOCX 或 EPUB 文件'; return }
  if (file.size > 50 * 1024 * 1024) { errorMsg.value = '文件不能超过 50MB'; return }
  selectedFile.value = file
}

async function load(showError = true) {
  try {
    const [docs, jobData] = await Promise.all([
      shortDramaApi.documents(props.projectId),
      shortDramaApi.jobs({ project_id: props.projectId, page_size: 20 }),
    ])
    documents.value = docs
    jobs.value = jobData.items
  } catch (e: any) {
    if (showError) errorMsg.value = e?.response?.data?.detail || '加载失败'
  }
  schedulePoll()
  void loadAnalyses()
}

async function loadAnalyses() {
  try { analyses.value = await shortDramaApi.novelAnalyses(props.projectId) as any[] }
  catch { analyses.value = [] }
}

function schedulePoll() {
  if (pollTimer) clearTimeout(pollTimer)
  if (active.value) pollTimer = setTimeout(() => void load(false), 1500)
}

async function upload() {
  if (!selectedFile.value || uploading.value) return
  uploading.value = true; uploadProgress.value = 0; errorMsg.value = ''
  try {
    await shortDramaApi.importDocument(props.projectId, selectedFile.value, (v) => { uploadProgress.value = v })
    selectedFile.value = null; uploadProgress.value = 100
    await load()
    emit('job-created')
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || '文档上传失败'
  } finally { uploading.value = false }
}

async function cancelJob(job: CreativeJob) {
  try { await shortDramaApi.cancelJob(job.id); await load() }
  catch (e: any) { errorMsg.value = e?.response?.data?.detail || '取消失败' }
}
async function retryJob(job: CreativeJob) {
  try { await shortDramaApi.retryJob(job.id); await load() }
  catch (e: any) { errorMsg.value = e?.response?.data?.detail || '重试失败' }
}

async function analyzeNovel() {
  errorMsg.value = ''
  try {
    const readyDoc = readyDocuments.value[0]
    if (!readyDoc) { errorMsg.value = '请先上传并解析文档'; return }
    await shortDramaApi.analyzeNovel(props.projectId, {
      document_id: readyDoc.id,
      chapter_start: 1,
      chapter_end: readyDoc.total_chapters || 999,
      idempotency_key: crypto.randomUUID(),
    })
    await load()
    emit('job-created')
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || 'AI 分析启动失败'
  }
}

async function confirmAnalysis(id: number) {
  errorMsg.value = ''
  try {
    await shortDramaApi.confirmNovelAnalysis(props.projectId, id)
    await loadAnalyses()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || '确认失败'
  }
}

onMounted(() => void load())
onBeforeUnmount(() => { if (pollTimer) clearTimeout(pollTimer) })
watch(() => props.projectId, () => void load())
</script>

<template>
  <GlassPanel
    title="源材料导入"
    description="上传小说/剧本文档，AI 解析后生成分析版本。确认分析后可进入步骤 1 生成故事台账。"
  >
    <template #actions>
      <V2Button variant="ghost" @click="router.push(`/v2/drama/projects/${projectId}/import`)">完整导入页 →</V2Button>
    </template>

    <!-- 错误提示 -->
    <div v-if="errorMsg" class="sm-error">{{ errorMsg }}</div>

    <!-- 上传区 -->
    <div class="sm-drop" :class="{ smDragging: dragging }"
      @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="dropFile">
      <input id="sm-file-input" type="file" accept=".txt,.docx,.epub" @change="chooseFile">
      <div class="sm-drop-icon">📄</div>
      <div class="sm-drop-info">
        <strong>{{ selectedFile?.name || '拖放故事文档到这里' }}</strong>
        <p>{{ selectedFile ? `${(selectedFile.size / 1024 / 1024).toFixed(2)} MB · 等待上传` : '支持 TXT / DOCX / EPUB，≤ 50MB' }}</p>
      </div>
      <label for="sm-file-input" class="sm-pick">选择文件</label>
    </div>
    <div v-if="uploading" class="sm-bar"><span :style="{ width: `${uploadProgress}%` }"></span></div>
    <div v-if="selectedFile && !uploading" class="sm-upload-act">
      <V2Button variant="primary" @click="upload">上传并开始解析</V2Button>
    </div>

    <!-- 文档列表 -->
    <div v-if="documents.length" class="sm-block">
      <h4 class="sm-h4">已导入文档（{{ documents.length }}）</h4>
      <div class="sm-card-list">
        <div v-for="doc in documents" :key="doc.id" class="sm-doc-card">
          <div class="sm-doc-fmt">{{ doc.source_format.toUpperCase() }}</div>
          <div class="sm-doc-body">
            <strong>{{ doc.title || doc.filename }}</strong>
            <small>{{ doc.filename }}</small>
            <p v-if="doc.status === 'ready'">{{ doc.total_chapters }} 章 · {{ formatSize(doc.total_chars) }}</p>
            <p v-else class="sm-pending">{{ statusText[doc.status] || doc.status }}</p>
          </div>
          <StatusBadge :tone="doc.status === 'ready' ? 'success' : 'warning'">
            {{ doc.status === 'ready' ? '就绪' : '解析中' }}
          </StatusBadge>
        </div>
      </div>
    </div>

    <!-- 解析任务 -->
    <div v-if="jobs.length" class="sm-block">
      <h4 class="sm-h4">解析任务（{{ jobs.length }}）</h4>
      <div class="sm-card-list">
        <div v-for="job in jobs" :key="job.id" class="sm-job-card">
          <div class="sm-job-head">
            <strong>{{ (job.input_payload as any)?.filename || `任务 #${job.id}` }}</strong>
            <StatusBadge :tone="statusTone(job.status)">{{ statusText[job.status] || job.status }}</StatusBadge>
          </div>
          <div class="sm-bar sm-bar-sm"><span :style="{ width: `${job.progress}%` }"></span></div>
          <div class="sm-job-foot">
            <small>{{ job.progress }}%</small>
            <small v-if="job.error" class="sm-danger">{{ job.error }}</small>
            <span class="sm-grow" />
            <button v-if="['queued', 'running'].includes(job.status)" class="sm-btn-mini" @click="cancelJob(job)">取消</button>
            <button v-if="['failed', 'cancelled'].includes(job.status)" class="sm-btn-mini" @click="retryJob(job)">重试</button>
          </div>
        </div>
      </div>
    </div>

    <!-- AI 分析 -->
    <div v-if="readyDocuments.length" class="sm-block">
      <h4 class="sm-h4">AI 分析版本</h4>
      <p class="sm-hint">对已就绪文档运行 AI 分析，提取人物、地点、事件和时间线。确认后可用于步骤 1 的故事台账生成。</p>
      <div class="sm-analyze-act">
        <V2Button variant="primary" :disabled="active" @click="analyzeNovel">
          {{ active ? '分析中…' : '启动 AI 分析' }}
        </V2Button>
        <V2Button variant="ghost" @click="emit('edit-prompt', 'novel_chunk_analysis', '小说分析')">📝</V2Button>
      </div>

      <div v-if="analyses.length" class="sm-card-list">
        <div v-for="a in analyses" :key="a.id" class="sm-analysis-card" :class="{ 'sm-failed': a.status === 'failed' }">
          <!-- 行头：点击展开/收起 -->
          <div class="sm-analysis-head" @click="toggleAnalysis(a.id)">
            <div class="sm-analysis-meta">
              <strong>分析 #{{ a.id }} · v{{ a.version }}</strong>
              <small>章节 {{ a.chapter_start }}-{{ a.chapter_end }}</small>
            </div>
            <span class="sm-analysis-summ">{{ analysisSummary(a.content) }}</span>
            <div class="sm-analysis-right">
              <StatusBadge :tone="a.status === 'confirmed' ? 'success' : a.status === 'failed' ? 'danger' : 'info'">
                {{ a.status === 'confirmed' ? '已确认' : a.status === 'failed' ? '失败' : '待确认' }}
              </StatusBadge>
              <button class="sm-expand-btn">{{ expandedAnalysis === a.id ? '−' : '+' }}</button>
            </div>
          </div>

          <!-- 校验错误 -->
          <div v-if="a.validation_errors?.length" class="sm-err-list">
            <small v-for="(err, i) in a.validation_errors" :key="i" class="sm-danger">⚠ {{ err.message || JSON.stringify(err) }}</small>
          </div>

          <!-- 展开详情 -->
          <div v-if="expandedAnalysis === a.id" class="sm-analysis-body">
            <div v-if="a.content?.synopsis" class="sm-field">
              <label>概要</label>
              <p>{{ a.content.synopsis }}</p>
            </div>
            <div v-if="a.content?.core_conflict" class="sm-field">
              <label>核心冲突</label>
              <p>{{ a.content.core_conflict }}</p>
            </div>
            <div v-if="a.content?.characters?.length" class="sm-field">
              <label>角色（{{ a.content.characters.length }}）</label>
              <div class="sm-tags">
                <span v-for="(c, i) in a.content.characters" :key="i" class="sm-tag">{{ typeof c === 'string' ? c : (c.name || JSON.stringify(c)) }}</span>
              </div>
            </div>
            <div v-if="a.content?.locations?.length" class="sm-field">
              <label>地点（{{ a.content.locations.length }}）</label>
              <div class="sm-tags">
                <span v-for="(l, i) in a.content.locations" :key="i" class="sm-tag">{{ typeof l === 'string' ? l : (l.name || JSON.stringify(l)) }}</span>
              </div>
            </div>
            <div v-if="a.content?.events?.length" class="sm-field">
              <label>事件（{{ a.content.events.length }}）</label>
              <div class="sm-event-list">
                <div v-for="(ev, i) in a.content.events.slice(0, 10)" :key="i" class="sm-event">
                  <small>{{ typeof ev === 'string' ? ev : (ev.description || ev.summary || ev.event || JSON.stringify(ev)) }}</small>
                </div>
                <small v-if="a.content.events.length > 10" class="sm-more">…还有 {{ a.content.events.length - 10 }} 条</small>
              </div>
            </div>
            <div v-if="a.content?.timeline?.length" class="sm-field">
              <label>时间线（{{ a.content.timeline.length }}）</label>
              <div class="sm-tags">
                <span v-for="(t, i) in a.content.timeline.slice(0, 15)" :key="i" class="sm-tag">{{ typeof t === 'string' ? t : (t.event || t.time || JSON.stringify(t)) }}</span>
              </div>
            </div>
            <div v-if="a.content?.hooks?.length" class="sm-field">
              <label>钩子（{{ a.content.hooks.length }}）</label>
              <div class="sm-tags">
                <span v-for="(h, i) in a.content.hooks" :key="i" class="sm-tag">{{ typeof h === 'string' ? h : (h.text || h.hook || JSON.stringify(h)) }}</span>
              </div>
            </div>

            <div v-if="!a.content || Object.keys(a.content).length === 0" class="sm-empty-content">
              分析内容为空。可能 AI 解析任务尚未完成或已失败。
            </div>

            <div class="sm-analysis-actions">
              <V2Button v-if="a.status === 'candidate'" variant="primary" size="sm" @click="confirmAnalysis(a.id)">确认此分析</V2Button>
              <V2Button v-if="a.status === 'failed'" variant="ghost" size="sm" @click="analyzeNovel">重新分析</V2Button>
            </div>
          </div>

          <!-- 未展开时的快捷确认 -->
          <div v-else-if="a.status === 'candidate'" class="sm-quick-act">
            <V2Button variant="ghost" size="sm" @click="confirmAnalysis(a.id)">确认</V2Button>
          </div>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="!documents.length && !jobs.length" class="sm-empty">
      还没有导入文档。上传小说原文后，系统会自动解析并提取章节结构。
    </div>
  </GlassPanel>
</template>

<style scoped>
/* 全部类名带 sm- 前缀，避免与 DirectorWorkbench / GlassPanel 内部样式冲突 */
.sm-error{padding:10px 12px;color:#ffdce1;background:rgba(255,127,145,.1);border-radius:10px;font-size:12px;margin-bottom:12px}

/* 上传区 */
.sm-drop{position:relative;min-height:130px;padding:18px 20px;display:flex;align-items:center;gap:14px;background:rgba(130,149,255,.04);border:2px dashed var(--v2-border);border-radius:14px;transition:.2s}
.sm-drop.smDragging{border-color:var(--v2-primary);background:rgba(102,126,234,.08)}
.sm-drop input{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none}
.sm-drop-icon{font-size:28px;flex-shrink:0}
.sm-drop-info{flex:1;min-width:0}
.sm-drop-info strong{font-size:13px;color:var(--v2-text)}
.sm-drop-info p{margin:3px 0 0;color:var(--v2-text-muted);font-size:11px}
.sm-pick{flex-shrink:0;padding:7px 14px;color:var(--v2-text);background:var(--v2-surface);border:1px solid var(--v2-border);border-radius:9px;cursor:pointer;font-size:12px}
.sm-pick:hover{border-color:var(--v2-primary)}

/* 进度条 */
.sm-bar{height:4px;background:rgba(255,255,255,.06);border-radius:99px;overflow:hidden}
.sm-bar span{display:block;height:100%;background:linear-gradient(90deg,#6f86ff,#aa70e8);transition:width .3s}
.sm-bar.sm-bar{margin-top:10px}
.sm-bar-sm{height:3px;margin-top:6px}
.sm-upload-act{margin-top:10px}

/* 区块标题 */
.sm-block{margin-top:18px}
.sm-h4{margin:0 0 8px;font-size:13px;color:#c8d0ee;font-weight:600}
.sm-hint{margin:0 0 10px;color:var(--v2-text-subtle);font-size:11px;line-height:1.5}
.sm-empty{margin-top:20px;color:var(--v2-text-subtle);font-size:12px;text-align:center;padding:16px 0}

/* 卡片列表通用 */
.sm-card-list{display:grid;gap:10px}

/* 文档卡片 */
.sm-doc-card{display:flex;align-items:center;gap:12px;padding:12px 14px;background:rgba(130,149,255,.04);border:1px solid var(--v2-border);border-radius:10px}
.sm-doc-fmt{flex-shrink:0;width:38px;height:38px;display:grid;place-items:center;color:#fff;background:linear-gradient(145deg,#7b8cff,#a167e8);border-radius:8px;font-size:9px;font-weight:700}
.sm-doc-body{flex:1;min-width:0;display:grid;gap:2px}
.sm-doc-body strong{font-size:12px;color:var(--v2-text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sm-doc-body small{color:var(--v2-text-muted);font-size:10px}
.sm-doc-body p{margin:2px 0 0;color:var(--v2-text-muted);font-size:11px}
.sm-pending{color:var(--v2-warning) !important}

/* 任务卡片 */
.sm-job-card{padding:12px 14px;background:rgba(130,149,255,.04);border:1px solid var(--v2-border);border-radius:10px}
.sm-job-head{display:flex;align-items:center;justify-content:space-between;gap:8px}
.sm-job-head strong{font-size:12px;color:var(--v2-text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sm-job-foot{display:flex;align-items:center;gap:8px;margin-top:6px;font-size:11px;color:var(--v2-text-muted)}
.sm-job-foot .sm-grow{flex:1}
.sm-btn-mini{padding:3px 10px;color:var(--v2-text-muted);background:none;border:1px solid var(--v2-border);border-radius:6px;cursor:pointer;font-size:11px}
.sm-btn-mini:hover{color:var(--v2-text);border-color:var(--v2-primary)}
.sm-danger{color:var(--v2-danger) !important}

/* AI 分析操作 */
.sm-analyze-act{margin-bottom:12px;display:flex;gap:8px;align-items:center}

/* 分析卡片 */
.sm-analysis-card{background:rgba(130,149,255,.04);border:1px solid var(--v2-border);border-radius:12px;overflow:hidden}
.sm-analysis-card.sm-failed{border-color:rgba(255,127,145,.3)}
.sm-analysis-head{display:flex;align-items:center;gap:10px;padding:12px 14px;cursor:pointer;user-select:none;flex-wrap:nowrap}
.sm-analysis-head:hover{background:rgba(130,149,255,.06)}
.sm-analysis-meta{display:grid;gap:2px;flex-shrink:0;min-width:130px}
.sm-analysis-meta strong{font-size:12px;color:var(--v2-text)}
.sm-analysis-meta small{color:var(--v2-text-muted);font-size:10px}
.sm-analysis-summ{flex:1;font-size:11px;color:var(--v2-text-subtle);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.sm-analysis-right{display:flex;align-items:center;gap:8px;flex-shrink:0}
.sm-expand-btn{width:26px;height:26px;display:grid;place-items:center;color:var(--v2-text-muted);background:none;border:1px solid var(--v2-border);border-radius:7px;cursor:pointer;font-size:14px}
.sm-expand-btn:hover{color:var(--v2-text);border-color:var(--v2-primary)}

.sm-err-list{padding:0 14px 8px;display:grid;gap:3px}
.sm-err-list small{font-size:11px}

/* 展开详情 */
.sm-analysis-body{padding:0 14px 14px;border-top:1px solid var(--v2-border);display:grid;gap:12px}
.sm-field{padding-top:10px}
.sm-field label{display:block;font-size:10px;color:var(--v2-text-subtle);margin-bottom:5px;text-transform:uppercase;letter-spacing:.5px;font-weight:600}
.sm-field p{margin:0;font-size:12px;color:var(--v2-text);line-height:1.65}
.sm-tags{display:flex;gap:5px;flex-wrap:wrap}
.sm-tag{padding:4px 10px;background:rgba(130,149,255,.08);border:1px solid rgba(130,149,255,.18);border-radius:7px;font-size:11px;color:#a8b8ee}
.sm-event-list{display:grid;gap:5px}
.sm-event{padding:7px 10px;background:rgba(0,0,0,.15);border-radius:8px}
.sm-event small{font-size:11px;color:var(--v2-text-muted);line-height:1.5}
.sm-more{color:var(--v2-text-subtle);font-size:10px;padding-top:4px}
.sm-empty-content{color:var(--v2-danger);font-size:12px;padding:10px 0}
.sm-analysis-actions{display:flex;gap:8px;padding-top:10px;border-top:1px solid var(--v2-border)}
.sm-quick-act{padding:0 14px 10px;display:flex;justify-content:flex-end}
</style>