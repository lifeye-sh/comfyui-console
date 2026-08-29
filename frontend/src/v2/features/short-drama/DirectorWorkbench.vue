<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { shortDramaApi } from '@/api/modules'
import EmotionCurveChart from './EmotionCurveChart.vue'
import ManifestStep from './ManifestStep.vue'
import ContinuityPanel from './ContinuityPanel.vue'
import StaleDependencyView from './StaleDependencyView.vue'
import GuidancePanel from './GuidancePanel.vue'
import DirectorChat from './DirectorChat.vue'
import SourceMaterialStep from './SourceMaterialStep.vue'
import AdaptationStep from './AdaptationStep.vue'
import PromptTemplateEditor from './PromptTemplateEditor.vue'
import AICallLogPanel from './AICallLogPanel.vue'
import GlassPanel from '@/v2/components/GlassPanel.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'

const route = useRoute(); const router = useRouter()
const projectId = computed(() => Number(route.params.id))
const state = ref<any>(null)
const loading = ref(true); const error = ref('')

/** 台账状态 */
const ledgers = ref<any[]>([])
const ledgerDetail = ref<any>(null)
const ledgerLoading = ref(false)
const generating = ref(false)
const decided = ref('')

/** 场景级台账 */
const sceneLedgers = ref<any[]>([])
const sceneSyncResult = ref('')
const syncing = ref(false)
/** 手动创建分集/场景 */
const manualCreateOpen = ref(false)
const manualEpisodeTitle = ref('第一集')
const manualSceneHeading = ref('')
const manualSceneLocation = ref('')
const manualSceneTime = ref('')
const manualCreating = ref(false)
/** 连续性事实 */
const facts = ref<any[]>([])
/** 风格圣经 */
const styleBibles = ref<any[]>([])
const selectedStyleId = ref<number | null>(null)
const creatingStyle = ref(false)
const checkpointB = ref<any>(null)
/** 锚点 */
const charAnchors = ref<any[]>([])
const propAnchors = ref<any[]>([])
const checkpointC = ref<any>(null)
/** 空间资产 */
const spatialPlans = ref<any[]>([])
const locationViews = ref<Record<number, any[]>>({})
/** 短剧 API：查询已确认分析用于生成台账 */
const analyses = ref<any[]>([])
const selectedAnalysisId = ref<number | null>(null)
/** AI 导演助手面板显隐（第 9 轮） */
const aiPanelOpen = ref(false)
/** 提示词编辑弹窗 */
const promptEditorVisible = ref(false)
const promptEditorCode = ref('')
const promptEditorTitle = ref('')
/** 全局操作反馈（成功提示） */
const notice = ref('')
/** 本地查看步骤：推进后仍可点击已完成步骤回看 */
const viewingStep = ref(0)
/** 当前步骤是否只读（回看历史步骤时） */
const isReadOnly = computed(() => viewingStep.value < state.value?.current_step)
/** 全局异步任务状态（解析/AI 分析/台账生成），跨步骤可见 */
const activeJobs = ref<any[]>([])
let jobPollTimer: ReturnType<typeof setTimeout> | null = null

async function loadActiveJobs() {
  try {
    const data = await shortDramaApi.jobs({ project_id: projectId.value, page_size: 50 })
    // 只显示活跃任务（queued/running/cancelling）和最近完成的（succeeded/failed，5 分钟内）
    const now = Date.now()
    activeJobs.value = (data.items as any[]).filter(j => {
      if (['queued', 'running', 'cancelling'].includes(j.status)) return true
      if (['succeeded', 'failed'].includes(j.status) && j.finished_at) {
        return now - new Date(j.finished_at).getTime() < 300000 // 5 分钟内
      }
      return false
    })
  } catch { activeJobs.value = [] }
  // 加载完成后根据是否有活跃任务决定是否继续轮询
  scheduleJobPoll()
}

function scheduleJobPoll() {
  if (jobPollTimer) clearTimeout(jobPollTimer)
  const hasActive = activeJobs.value.some(j => ['queued', 'running', 'cancelling'].includes(j.status))
  if (hasActive) jobPollTimer = setTimeout(() => { void loadActiveJobs() }, 2000)
}

const jobTypeLabel: Record<string, string> = {
  parse_document: '文档解析',
  analyze_novel: 'AI 分析',
  director_story_ledger: '台账生成',
  generate_adaptation: '改编生成',
  generate_episode_screenplay: '剧本生成',
}
const jobStatusTone = (s: string) => s === 'succeeded' ? 'success' : s === 'failed' ? 'danger' : 'warning'
const jobStatusLabel = (s: string) => s === 'queued' ? '排队中' : s === 'running' ? '执行中' : s === 'succeeded' ? '已完成' : s === 'failed' ? '失败' : s

/** 任务显示名：类型 + 有意义的上下文（文件名/文档号/分析号），避免只显示裸编号 */
function jobDisplayName(job: any): string {
  const p = job.input_payload
  const type = jobTypeLabel[job.job_type] || job.job_type
  switch (job.job_type) {
    case 'parse_document':
      return p?.filename ? `${type}·${p.filename}` : `${type} #${job.id}`
    case 'analyze_novel':
      return p?.document_id ? `${type}·文档#${p.document_id}` : `${type} #${job.id}`
    case 'director_story_ledger':
      return p?.analysis_id ? `${type}·分析#${p.analysis_id}` : `${type} #${job.id}`
    case 'generate_adaptation':
      return p?.analysis_id ? `${type}·分析#${p.analysis_id}` : `${type} #${job.id}`
    case 'generate_episode_screenplay':
      return p?.episode_id ? `${type}·分集#${p.episode_id}` : `${type} #${job.id}`
    default:
      return `${type} #${job.id}`
  }
}

const STEPS = [
  { step: 0, label: '源材料导入' },
  { step: 1, label: '故事台账 + 情感曲线', checkpoint: 'A' },
  { step: 2, label: '改编候选确认' },
  { step: 3, label: '场景级剧本台账' },
  { step: 4, label: '风格圣经 + 色卡', checkpoint: 'B' },
  { step: 5, label: '角色/道具锚点', checkpoint: 'C' },
  { step: 6, label: '外景拓扑/内景平面图' },
  { step: 7, label: 'Manifest + 连续性审计' },
  { step: 8, label: '生产编译' },
]

const gateMeta: Record<string, { label: string; tone: 'neutral'|'success'|'warning'|'danger'|'info' }> = {
  pending: { label: '未开始', tone: 'neutral' },
  blocked: { label: '阻塞', tone: 'danger' },
  passed: { label: '已通过', tone: 'success' },
  waived: { label: '已豁免', tone: 'warning' },
}

async function load() {
  loading.value = true; error.value = ''
  try {
    state.value = await shortDramaApi.directorWorkflow(projectId.value)
    if (state.value) {
      // 首次加载或推进后同步查看步骤到当前步骤
      if (viewingStep.value === 0 || viewingStep.value < state.value.current_step) {
        viewingStep.value = state.value.current_step
      }
      void loadLedgers()
    }
    try { analyses.value = await shortDramaApi.novelAnalyses(projectId.value) as any[] } catch { analyses.value = [] }
    const confirmed = analyses.value.filter(a => a.status === 'confirmed')
    if (confirmed.length && !selectedAnalysisId.value) selectedAnalysisId.value = confirmed[0].id
    void loadSceneLedgers()
    void loadFacts()
    void loadStyles()
    void loadCheckpointB()
    void loadAnchors()
    void loadSpatialPlans()
    void loadActiveJobs()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally { loading.value = false }
}

async function loadSceneLedgers() {
  try { sceneLedgers.value = await shortDramaApi.directorSceneLedgers(projectId.value) as any[] }
  catch { sceneLedgers.value = [] }
}

async function loadFacts() {
  try { facts.value = await shortDramaApi.directorContinuityFacts(projectId.value) as any[] } catch { facts.value = [] }
}

async function syncSceneLedgers() {
  syncing.value = true; sceneSyncResult.value = ''
  try {
    const result = await shortDramaApi.directorSyncSceneLedgers(projectId.value, {})
    const total = result.aligned + result.created + result.retired
    if (total === 0) {
      sceneSyncResult.value = '没有检测到剧本场景。场景台账来自改编确认后生成的分集/场景——如果你跳过了改编，请先手动创建分集和场景，或返回步骤 2 做改编。'
    } else {
      sceneSyncResult.value = `对齐完成：沿用 ${result.aligned} 个、新增 ${result.created} 个、退役 ${result.retired} 个场景键`
    }
    void loadSceneLedgers()
  } catch (e: any) {
    sceneSyncResult.value = e?.response?.data?.detail || '对齐失败'
  } finally { syncing.value = false }
}

/** 手动创建分集 + 场景（跳过改编时的补充路径） */
async function createSceneManually() {
  if (!manualSceneHeading.value.trim()) { sceneSyncResult.value = '请填写场景标题'; return }
  manualCreating.value = true; sceneSyncResult.value = ''
  try {
    // 取项目当前分集，没有则创建第一个分集
    let episodes: any[] = []
    try {
      const screenplayData = await shortDramaApi.screenplay(projectId.value) as any
      episodes = screenplayData?.episodes || []
    } catch { episodes = [] }
    let episodeId: number | null = episodes[0]?.id ?? null
    if (!episodeId) {
      const ep = await shortDramaApi.createEpisode(projectId.value, {
        title: manualEpisodeTitle.value.trim() || '第一集',
        target_duration: 60,
      })
      episodeId = ep.id
    }
    await shortDramaApi.createScene(projectId.value, episodeId, {
      heading: manualSceneHeading.value.trim(),
      location_name: manualSceneLocation.value.trim(),
      time_of_day: manualSceneTime.value.trim(),
      content: '',
      elements: [],
      source_references: [],
    })
    // 清空场景字段，保留分集标题
    manualSceneHeading.value = ''
    manualSceneLocation.value = ''
    manualSceneTime.value = ''
    manualCreateOpen.value = false
    sceneSyncResult.value = '场景已创建，正在对齐…'
    await syncSceneLedgers()
  } catch (e: any) {
    sceneSyncResult.value = e?.response?.data?.detail || '创建场景失败'
  } finally { manualCreating.value = false }
}

async function resolveFact(factId: number) {
  const resolution = prompt('输入处理方式') || ''
  if (!resolution && !confirm('不填写处理方式直接标记解决？')) return
  try {
    await shortDramaApi.directorResolveFact(projectId.value, factId, { resolution })
    void loadFacts()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '处理失败'
  }
}

async function loadStyles() {
  try {
    styleBibles.value = await shortDramaApi.directorStyleBibles(projectId.value) as any[]
    const approved = styleBibles.value.find(b => b.status === 'approved')
    if (approved && !selectedStyleId.value) selectedStyleId.value = approved.id
    else if (!selectedStyleId.value && styleBibles.value.length) selectedStyleId.value = styleBibles.value[0].id
  } catch { styleBibles.value = [] }
}

async function loadCheckpointB() {
  try { checkpointB.value = await shortDramaApi.directorCheckpointB(projectId.value) } catch { checkpointB.value = null }
}

/** 稳健提取 axios 错误信息 */
function extractApiError(e: any): string {
  if (!e) return ''
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0]
    return first?.msg || first?.message || JSON.stringify(first)
  }
  return e?.response?.data?.message || e?.message || ''
}

/** 锚点字段中文标签 */
const ANCHOR_FIELD_LABELS: Record<string, string> = {
  story_profile: '故事人物特征',
  face_ratios: '面部比例',
  age_range: '年龄段',
  feature_marks: '特征标记',
  appearance: '外貌',
  personality: '性格',
  identity: '身份描述',
  expression: '表情',
  costume: '服装',
  styling: '造型',
  pose: '姿态',
  lighting: '光照',
  hair_makeup: '妆发',
}

/** 把锚点的 dict 字段转成 {label, value} 列表，过滤空值 */
function dictFields(dict: any): Array<{ label: string; value: string }> {
  if (!dict || typeof dict !== 'object') return []
  return Object.entries(dict)
    .filter(([, v]) => v !== '' && v !== null && v !== undefined)
    .map(([k, v]) => ({
      label: ANCHOR_FIELD_LABELS[k] || k,
      value: typeof v === 'string' ? v : JSON.stringify(v),
    }))
}

async function createStyleFromBrief() {
  creatingStyle.value = true; error.value = ''
  try {
    const brief = await shortDramaApi.brief(projectId.value)
    await shortDramaApi.directorCreateStyleBible(projectId.value, {
      name: `风格圣经（基于简报）`,
      visual_thesis: brief.visual_style || '根据创作简报推导的视觉风格',
      aspect_ratio: brief.aspect_ratio || '9:16',
      palette: {
        name: '通用色卡',
        scope: 'general',
        primary_color: '#3a4a7a',
        secondary_color: '#5a6a9a',
        accent_color: '#ff9a48',
        neutral_color: '#202838',
        skin_tone_protection: '保持肤色自然，不做过度风格化调色',
        forbidden_colors: [],
        exposure_notes: '低对比起步，按场景时段微调',
      },
      provenance: { created_by: 'brief' },
    })
    void loadStyles(); void loadCheckpointB()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '创建风格候选失败'
  } finally { creatingStyle.value = false }
}

async function approveStyle(styleId: number) {
  try {
    await shortDramaApi.directorApproveStyleBible(projectId.value, styleId)
    decided.value = '风格圣经已批准，Checkpoint B 通过'
    void loadStyles(); void loadCheckpointB()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '批准失败'
  }
}

async function loadAnchors() {
  try {
    charAnchors.value = await shortDramaApi.directorCharacterAnchors(projectId.value) as any[]
    propAnchors.value = await shortDramaApi.directorPropAnchors(projectId.value) as any[]
    checkpointC.value = await shortDramaApi.directorCheckpointC(projectId.value)
  } catch { charAnchors.value = []; propAnchors.value = []; checkpointC.value = null }
}

/** 从世界设定（或 AI 分析）生成角色/道具锚点候选 */
async function createAnchorsFromWorld() {
  creatingStyle.value = true; error.value = ''; sceneSyncResult.value = ''
  try {
    // 前置检查：Checkpoint B 必须已通过（有批准风格圣经）
    await loadCheckpointB()
    if (!checkpointB.value?.passed) {
      sceneSyncResult.value = 'Checkpoint B 未通过：请先在步骤 4 批准一个风格圣经，再回来创建角色/道具锚点。'
      return
    }
    const world = await shortDramaApi.world(projectId.value)
    const worldChars: any[] = world?.characters || []
    const worldProps: any[] = world?.props || []

    // 角色数据源：优先 AI 分析（故事人物特征），世界设定补充结构化外貌/性格
    const confirmed = analyses.value.find(a => a.status === 'confirmed')
    const analysisChars: any[] = confirmed?.content?.characters || []
    const worldByName = new Map(worldChars.map(c => [c.name, c]))
    let characters: any[] = []
    let sourceLabel = '世界设定'
    if (analysisChars.length) {
      characters = analysisChars.map(ac => {
        const wc = worldByName.get(ac.name)
        return {
          name: ac.name,
          story_profile: ac.description || '',
          appearance: wc?.appearance || '',
          age_range: wc?.age_appearance || '',
          personality: wc?.personality || '',
        }
      })
      sourceLabel = 'AI 分析'
    } else if (worldChars.length) {
      characters = worldChars.map(wc => ({
        name: wc.name,
        story_profile: wc.identity || wc.description || '',
        appearance: wc.appearance || '',
        age_range: wc.age_appearance || '',
        personality: wc.personality || '',
      }))
    }
    const props = worldProps
    if (!characters.length && !props.length) {
      sceneSyncResult.value = '没有可用的角色数据。请先在「角色与世界设定」页面创建角色，或在步骤 0 确认包含角色的 AI 分析版本。'
      return
    }

    const existingKeys = new Set(charAnchors.value.map(a => a.stable_key))
    const existingPropKeys = new Set(propAnchors.value.map(a => a.stable_key))
    let createdChars = 0, createdProps = 0, skipped = 0
    for (const [i, c] of characters.entries()) {
      const key = `CH-${String(i + 1).padStart(3, '0')}`
      if (existingKeys.has(key)) { skipped++; continue }
      try {
        await shortDramaApi.directorCreateCharAnchor(projectId.value, {
          stable_key: key,
          name: c.name || `角色 ${key}`,
          priority: i === 0 ? 'protagonist' : 'supporting',
          identity_anchor: {
            story_profile: c.story_profile || '',
            appearance: c.appearance || '',
            age_range: c.age_range || '',
            personality: c.personality || '',
            feature_marks: '',
          },
          controllable_vars: { expression: '', costume: '', styling: '' },
          drift_prohibition: ['身份特征不得偏离已批准锚点'],
        })
        createdChars++
      } catch (e: any) {
        // 记录首个创建失败原因，避免静默跳过
        if (!error.value) error.value = extractApiError(e) || '创建角色锚点失败'
        skipped++
      }
    }
    for (const [i, p] of props.entries()) {
      const key = `PR-${String(i + 1).padStart(3, '0')}`
      if (existingPropKeys.has(key)) { skipped++; continue }
      try {
        await shortDramaApi.directorCreatePropAnchor(projectId.value, {
          stable_key: key,
          name: p.name || `道具 ${key}`,
          size: p.appearance || '',
          material: '',
          wear_condition: p.continuity_note || '',
          owner_character_key: p.owner_character_id ? `CH-${String(p.owner_character_id).padStart(3, '0')}` : null,
          priority_rank: i + 1,
        })
        createdProps++
      } catch (e: any) {
        if (!error.value) error.value = extractApiError(e) || '创建道具锚点失败'
        skipped++
      }
    }
    sceneSyncResult.value = `锚点创建完成（来源：${sourceLabel}）：${createdChars} 个角色、${createdProps} 个道具${skipped ? `（跳过 ${skipped} 个）` : ''}`
    void loadAnchors()
  } catch (e: any) {
    error.value = extractApiError(e) || '从世界设定创建锚点失败'
  } finally { creatingStyle.value = false }
}

async function approveCharAnchor(anchorId: number) {
  try {
    await shortDramaApi.directorApproveCharAnchor(projectId.value, anchorId)
    void loadAnchors()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '批准失败'
  }
}

async function approvePropAnchor(anchorId: number) {
  try {
    await shortDramaApi.directorApprovePropAnchor(projectId.value, anchorId)
    void loadAnchors()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '批准失败'
  }
}

async function loadSpatialPlans() {
  try {
    spatialPlans.value = await shortDramaApi.directorSpatialPlans(projectId.value) as any[]
    for (const plan of spatialPlans.value) {
      if (plan.status === 'approved' || plan.status === 'candidate') void loadViews(plan.id)
    }
  } catch { spatialPlans.value = [] }
}

async function loadViews(planId: number) {
  try { locationViews.value[planId] = await shortDramaApi.directorLocationViews(projectId.value, planId) as any[] }
  catch { locationViews.value[planId] = [] }
}

async function createSpatialPlanFromLocation(locationStableKey: string, kind: 'exterior' | 'interior', locationId: number | null) {
  try {
    await shortDramaApi.directorCreateSpatialPlan(projectId.value, {
      location_stable_key: locationStableKey,
      plan_kind: kind,
      name: `${locationStableKey} ${kind === 'exterior' ? '外景拓扑' : '内景平面图'}`,
      topology: kind === 'exterior' ? { landmarks: [{ id: 1, x: 0, y: 0, name: locationStableKey, description: '初始地标' }] } : {},
      floor_plan: kind === 'interior' ? { scale: '1:50', doors: [], furniture_anchors: [], light_sources: [] } : {},
      location_id: locationId,
    })
    void loadSpatialPlans()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '创建空间结构失败'
  }
}

async function approveSpatialPlan(planId: number) {
  try {
    await shortDramaApi.directorApproveSpatialPlan(projectId.value, planId)
    void loadSpatialPlans()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '批准失败'
  }
}

async function createViewForPlan(planId: number, locationStableKey: string) {
  const name = prompt('视图名称', `${locationStableKey} 主视图`)
  if (!name) return
  try {
    await shortDramaApi.directorCreateLocationView(projectId.value, planId, { name })
    void loadViews(planId)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '创建视图失败'
  }
}

async function approveView(viewId: number, planId: number) {
  try {
    await shortDramaApi.directorApproveLocationView(projectId.value, viewId)
    void loadViews(planId)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '批准失败'
  }
}

async function loadLedgers() {
  ledgerLoading.value = true
  try {
    ledgers.value = await shortDramaApi.directorLedgers(projectId.value) as any[]
    if (ledgers.value.length && !ledgerDetail.value) void openLedger(ledgers.value[0].id)
  } catch { ledgers.value = [] }
  finally { ledgerLoading.value = false }
}

async function openLedger(id: number) {
  try { ledgerDetail.value = await shortDramaApi.directorLedgerDetail(projectId.value, id) }
  catch (e: any) { error.value = e?.response?.data?.detail || '台账详情加载失败' }
}

async function generateLedger() {
  if (!selectedAnalysisId.value) { error.value = '请先确认一个小说分析版本'; return }
  generating.value = true; error.value = ''
  try {
    await shortDramaApi.directorGenerateLedger(projectId.value, {
      analysis_id: selectedAnalysisId.value,
      idempotency_key: crypto.randomUUID(),
    })
    // 任务已提交，立即刷新任务栏并轮询台账直到出现
    await loadActiveJobs()
    pollLedger()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '台账生成任务创建失败'
    generating.value = false
  }
}

let ledgerPollTimer: ReturnType<typeof setTimeout> | null = null
function pollLedger(attempts = 0) {
  if (ledgerPollTimer) clearTimeout(ledgerPollTimer)
  if (attempts > 30) { generating.value = false; error.value = '台账生成超时，请检查 AI 配置后重试'; return }
  ledgerPollTimer = setTimeout(async () => {
    try {
      await loadLedgers()
      if (ledgers.value.length) {
        generating.value = false
        await openLedger(ledgers.value[0].id)
      } else {
        pollLedger(attempts + 1)
      }
    } catch {
      pollLedger(attempts + 1)
    }
  }, 2000)
}

async function approveLedger() {
  if (!ledgerDetail.value) return
  decided.value = ''
  try {
    const result = await shortDramaApi.directorApproveLedger(projectId.value, ledgerDetail.value.id)
    if (result.ok) {
      decided.value = `台账 ${ledgerDetail.value.name} 已批准，步骤 1 门禁已通过`
      void load(); void openLedger(ledgerDetail.value.id)
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '批准失败'
  }
}

async function resolveDecision(decisionId: number, waive: boolean) {
  const chosen = waive ? '' : (prompt('输入选择的方案') || '')
  try {
    await shortDramaApi.directorResolveDecision(projectId.value, decisionId, { chosen, note: '', waive })
    void openLedger(ledgerDetail.value.id)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '处理决策失败'
  }
}

async function resolveDecisionCustom(decisionId: number, custom: string) {
  if (!custom.trim()) return
  await resolveDecisionWithChosen(decisionId, custom.trim())
}

async function resolveDecisionWithChosen(decisionId: number, chosen: string) {
  try {
    await shortDramaApi.directorResolveDecision(projectId.value, decisionId, { chosen, note: '', waive: false })
    void openLedger(ledgerDetail.value.id)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '处理决策失败'
  }
}

async function createWorkflow() {
  try { state.value = await shortDramaApi.directorCreateWorkflow(projectId.value) }
  catch (e: any) { error.value = e?.response?.data?.detail || '创建工作流失败' }
}

async function advance() {
  try { state.value = await shortDramaApi.directorAdvance(projectId.value, { allow_blocked: false })
    if (state.value) viewingStep.value = state.value.current_step
  }
  catch (e: any) { error.value = e?.response?.data?.detail || '推进失败' }
}

async function setGate(step: number, gate: string) {
  try { state.value = await shortDramaApi.directorSetGate(projectId.value, step, { gate_status: gate, reason: null }) }
  catch (e: any) { error.value = e?.response?.data?.detail || '设置门禁失败' }
}

/** 跳过改编：将步骤 2 门禁标记为豁免，然后推进到步骤 3 */
async function skipAdaptation() {
  error.value = ''; notice.value = ''
  try {
    await shortDramaApi.directorSetGate(projectId.value, 2, { gate_status: 'waived', reason: '跳过改编' })
    // 只有当前仍停留在步骤 2 且流程活跃时才推进
    if (state.value?.current_step === 2 && state.value?.status === 'active') {
      state.value = await shortDramaApi.directorAdvance(projectId.value, { allow_blocked: false })
      if (state.value) viewingStep.value = state.value.current_step
      notice.value = '已跳过改编，进入步骤 3（场景级台账）'
    } else {
      state.value = await shortDramaApi.directorWorkflow(projectId.value)
      notice.value = '已将步骤 2（改编）标记为跳过'
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '跳过改编失败'
  }
}

onMounted(() => { void load(); void loadActiveJobs(); scheduleJobPoll() })
</script>

<template>
  <div class="v2-page director-workbench">
    <div class="v2-page-heading heading">
      <div>
        <StatusBadge tone="info">实验</StatusBadge>
        <h1>导演前期工作台</h1>
        <p>AI 导演前期制作流程：台账 → 风格 → 锚点 → 空间 → Manifest。当前为规则状态预览。</p>
      </div>
      <div class="heading-actions">
        <V2Button :variant="aiPanelOpen ? 'primary' : 'ghost'" @click="aiPanelOpen = !aiPanelOpen">
          🤖 AI 助手
        </V2Button>
        <V2Button variant="ghost" @click="load">刷新</V2Button>
        <V2Button variant="ghost" @click="router.push(`/v2/drama/projects/${projectId}`)">返回项目</V2Button>
      </div>
    </div>

    <div v-if="loading" class="loading">加载中…</div>
    <div v-else-if="error" class="load-error"><span>{{ error }}</span><V2Button variant="ghost" @click="load">重试</V2Button></div>
    <div v-else-if="!state" class="empty-state">
      <p>该项目还没有导演前期工作流。</p>
      <V2Button variant="primary" @click="createWorkflow">创建工作流</V2Button>
    </div>
    <div v-else class="workbench">
      <!-- 全局任务状态栏：跨步骤可见 -->
      <div v-if="activeJobs.length" class="job-status-bar">
        <div v-for="job in activeJobs" :key="job.id" class="job-status-item">
          <span class="job-name">{{ jobDisplayName(job) }}</span>
          <StatusBadge :tone="jobStatusTone(job.status)">{{ jobStatusLabel(job.status) }}</StatusBadge>
          <div v-if="['queued', 'running'].includes(job.status)" class="job-mini-bar"><span :style="{ width: `${job.progress}%` }"></span></div>
          <small v-if="job.error" class="job-error-text">{{ job.error.slice(0, 60) }}</small>
        </div>
      </div>

      <!-- 左栏：步骤导航 -->
      <aside class="step-nav">
        <div class="step-nav-head">
          <b>流程步骤</b>
          <small>当前第 {{ state.current_step }} 步<span v-if="isReadOnly"> · 回看第 {{ viewingStep }} 步</span></small>
        </div>
        <button v-for="s in STEPS" :key="s.step" class="step-item"
          :class="{ current: s.step === viewingStep, done: s.step < state.current_step }"
          :disabled="s.step > state.current_step"
          @click="s.step <= state.current_step && (viewingStep = s.step)">
          <i>{{ s.step }}</i>
          <span class="step-label">
            <b>{{ s.label }}</b>
            <small v-if="s.checkpoint">检查点 {{ s.checkpoint }}</small>
          </span>
          <StatusBadge :tone="gateMeta[state.steps[s.step]?.gate_status]?.tone || 'neutral'">
            {{ gateMeta[state.steps[s.step]?.gate_status]?.label || state.steps[s.step]?.gate_status }}
          </StatusBadge>
        </button>
        <div class="step-nav-actions">
          <V2Button variant="ghost" size="sm" :disabled="viewingStep <= 0" @click="viewingStep--">← 上一步</V2Button>
          <V2Button class="advance-btn" :disabled="state.current_step >= 8" @click="advance">推进到下一步</V2Button>
        </div>
      </aside>

      <!-- 中栏：当前步骤工作区 -->
      <main class="workspace">
        <!-- 全局操作反馈 -->
        <div v-if="error" class="wb-error global-feedback">{{ error }} <button class="fb-close" @click="error = ''">✕</button></div>
        <div v-if="notice" class="wb-success global-feedback">{{ notice }} <button class="fb-close" @click="notice = ''">✕</button></div>

        <!-- 回看提示 -->
        <div v-if="isReadOnly" class="readonly-banner">
          正在回看步骤 {{ viewingStep }}（当前进度为步骤 {{ state.current_step }}）
          <V2Button variant="ghost" size="sm" @click="viewingStep = state.current_step">回到当前步骤 →</V2Button>
        </div>

        <!-- 步骤 0：源材料导入 -->
        <template v-if="viewingStep === 0">
          <SourceMaterialStep :project-id="projectId" @edit-prompt="(code: string, title: string) => { promptEditorCode = code; promptEditorTitle = title; promptEditorVisible = true }" @job-created="loadActiveJobs" />
        </template>

        <!-- 步骤 1：故事台账 + 情感曲线 -->
        <template v-if="viewingStep === 1">
          <GlassPanel title="故事台账" description="AI 分析后的节拍表与情感曲线。批准后进入 Checkpoint A。">
            <template #actions>
              <select v-model="selectedAnalysisId" class="analysis-select">
                <option :value="null" disabled>选择已确认的分析</option>
                <option v-for="a in analyses.filter(v=>v.status==='confirmed')" :key="a.id" :value="a.id">
                  分析 #{{ a.id }} · v{{ a.version }}（章节 {{ a.chapter_start }}-{{ a.chapter_end }}）
                </option>
              </select>
              <V2Button variant="primary" :disabled="generating||!selectedAnalysisId" @click="generateLedger">{{ generating ? '生成中…' : 'AI 生成台账' }}</V2Button>
              <V2Button variant="ghost" @click="promptEditorCode = 'director_story_ledger'; promptEditorTitle = '故事台账生成'; promptEditorVisible = true">📝</V2Button>
            </template>
            <div v-if="error" class="wb-error">{{ error }}</div>
            <div v-if="decided" class="wb-success">{{ decided }}</div>

            <div v-if="ledgers.length" class="ledger-tabs">
              <button v-for="l in ledgers" :key="l.id" class="ledger-tab"
                :class="{ active: ledgerDetail?.id === l.id }" @click="openLedger(l.id)">
                {{ l.name || `台账 v${l.version}` }}
                <StatusBadge :tone="l.status === 'approved' ? 'success' : l.status === 'invalid' ? 'danger' : 'info'">
                  {{ l.status === 'approved' ? '已批准' : l.status === 'invalid' ? '校验失败' : l.status === 'candidate' ? '候选' : l.status }}
                </StatusBadge>
              </button>
            </div>

            <div v-if="ledgerDetail" class="ledger-body">
              <p v-if="ledgerDetail.summary" class="ledger-summary">{{ ledgerDetail.summary }}</p>
              <div v-if="ledgerDetail.validation_errors?.length" class="wb-error">
                存在 {{ ledgerDetail.validation_errors.length }} 个校验错误，请检查节拍数据。
                <details><summary>查看详情</summary><pre>{{ JSON.stringify(ledgerDetail.validation_errors, null, 2) }}</pre></details>
              </div>

              <!-- 情感曲线（强制首反馈） -->
              <h4 class="section-title">📈 情感曲线</h4>
              <EmotionCurveChart v-if="ledgerDetail.emotion_curve?.length" :curve="ledgerDetail.emotion_curve" />
              <p v-else class="empty-tip">暂无节拍数据。</p>
              <div v-if="ledgerDetail.curve_summary" class="curve-summary-boxes">
                <span v-if="ledgerDetail.curve_summary.rhythm_risk">⚠️ {{ ledgerDetail.curve_summary.rhythm_risk }}</span>
                <span v-if="ledgerDetail.curve_summary.turning_points?.length">
                  主要转折：{{ ledgerDetail.curve_summary.turning_points.map((p: any) => p.stable_key).join('、') }}
                </span>
              </div>

              <!-- 节拍表 -->
              <h4 class="section-title">🥁 节拍表（{{ ledgerDetail.beats?.length || 0 }}）</h4>
              <div v-if="ledgerDetail.beats?.length" class="beat-table">
                <table>
                  <thead><tr><th>键</th><th>事件</th><th>冲突</th><th>强度</th><th>效价</th><th>情绪</th><th>证据</th><th>来源</th></tr></thead>
                  <tbody>
                    <tr v-for="b in ledgerDetail.beats" :key="b.id">
                      <td><code>{{ b.stable_key }}</code></td>
                      <td class="wrap-cell">{{ b.event }}</td>
                      <td class="wrap-cell">{{ b.conflict || '—' }}</td>
                      <td>{{ b.emotion_intensity }}</td>
                      <td>{{ b.emotion_valence > 0 ? '+' : '' }}{{ b.emotion_valence }}</td>
                      <td>{{ b.dominant_emotion || '—' }}</td>
                      <td><small :class="{ assumed: b.evidence_type === 'assumed' }">{{ b.evidence_type }}</small></td>
                      <td class="loc-cell"><small>{{ b.source_locator || '—' }}</small></td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <!-- Checkpoint A 决策 -->
              <h4 class="section-title">⚖️ 检查点 A · 源材料矛盾决策</h4>
              <div v-if="ledgerDetail.decisions?.length" class="decisions">
                <div v-for="d in ledgerDetail.decisions" :key="d.id" class="decision-item">
                  <b>{{ d.question }}</b>
                  <div v-if="d.options?.length" class="decision-options">
                    <button v-for="o in d.options" :key="o.key" @click="resolveDecisionWithChosen(d.id, o.text)" :disabled="d.status !== 'open'">{{ o.text }}</button>
                  </div>
                  <div class="decision-actions">
                    <template v-if="d.status === 'open'">
                      <input :placeholder="'或输入自定义方案…'" class="custom-input" @keyup.enter="(e: Event) => resolveDecisionCustom(d.id, (e.target as HTMLInputElement).value)" />
                      <V2Button variant="ghost" size="sm" @click="resolveDecision(d.id, true)">豁免</V2Button>
                    </template>
                    <StatusBadge v-else :tone="d.status === 'resolved' ? 'success' : 'warning'">{{ d.status === 'resolved' ? '已处理' : '已豁免' }}</StatusBadge>
                  </div>
                  <small v-if="d.chosen">选择：{{ d.chosen }}</small>
                </div>
              </div>
              <p v-else class="empty-tip">没有检测到源材料矛盾。</p>

              <!-- 批准按钮 -->
              <div class="approve-row">
                <V2Button variant="primary" :disabled="ledgerDetail.status !== 'candidate'" @click="approveLedger">
                  ✅ 批准台账并通过检查点 A
                </V2Button>
                <small>批准前必须处理所有矛盾决策并消除校验错误。</small>
              </div>
            </div>
            <p v-else-if="!ledgers.length" class="empty-tip">还没有台账。选择已确认的分析后点击「AI 生成台账」。</p>
          </GlassPanel>
        </template>

        <!-- 步骤 2：改编候选确认 -->
        <template v-else-if="viewingStep === 2">
          <AdaptationStep :project-id="projectId"
            @edit-prompt="(code: string, title: string) => { promptEditorCode = code; promptEditorTitle = title; promptEditorVisible = true }"
            @skip="skipAdaptation"
            @job-created="loadActiveJobs" />
        </template>

        <!-- 步骤 3：场景级台账 + 稳定键对齐 -->
        <template v-else-if="viewingStep === 3">
          <GlassPanel title="场景级台账" description="改编确认后自动同步场景稳定键（SC-xxx）。替换 StoryVersion 后沿用键、删除退役、新增取新键。">
            <template #actions>
              <V2Button variant="ghost" size="sm" @click="manualCreateOpen = !manualCreateOpen">{{ manualCreateOpen ? '收起' : '+ 手动建场景' }}</V2Button>
              <V2Button variant="primary" :disabled="syncing" @click="syncSceneLedgers">{{ syncing ? '对齐中…' : '重新对齐场景' }}</V2Button>
            </template>

            <!-- 手动创建分集/场景表单 -->
            <div v-if="manualCreateOpen" class="manual-create-box">
              <div class="manual-create-grid">
                <label><span>分集标题</span><input v-model="manualEpisodeTitle" placeholder="第一集" class="scene-input"></label>
                <label><span>场景标题</span><input v-model="manualSceneHeading" placeholder="例如：主角登场" class="scene-input"></label>
                <label><span>地点</span><input v-model="manualSceneLocation" placeholder="例如：车站" class="scene-input"></label>
                <label><span>时段</span><input v-model="manualSceneTime" placeholder="例如：夜" class="scene-input"></label>
              </div>
              <div class="manual-create-actions">
                <V2Button variant="primary" size="sm" :disabled="manualCreating || !manualSceneHeading.trim()" @click="createSceneManually">
                  {{ manualCreating ? '创建中…' : '创建场景' }}
                </V2Button>
                <small>若项目还没有分集，会自动创建第一个分集；创建后自动对齐场景稳定键。</small>
              </div>
            </div>

            <div v-if="sceneSyncResult" class="wb-success">{{ sceneSyncResult }}</div>
            <div v-if="!sceneLedgers.length" class="empty-tip scene-empty">
              <p>还没有场景台账。</p>
              <p class="scene-empty-hint">场景台账来自剧本的分集/场景结构：确认改编候选后会自动生成。如果你跳过了改编，可以点上方「+ 手动建场景」直接添加，或前往剧本工作台批量创建。</p>
              <div class="scene-empty-actions">
                <V2Button variant="ghost" size="sm" @click="manualCreateOpen = true">+ 手动建场景</V2Button>
                <V2Button variant="ghost" size="sm" @click="router.push(`/v2/drama/projects/${projectId}/screenplay`)">前往剧本工作台 →</V2Button>
              </div>
            </div>
            <div v-else class="scene-grid">
              <div v-for="s in sceneLedgers" :key="s.id" class="scene-card" :class="{ retired: s.alignment_status === 'retired' }">
                <header><code>{{ s.stable_key }}</code><StatusBadge :tone="s.alignment_status === 'retired' ? 'neutral' : s.alignment_status === 'pending' ? 'warning' : 'success'">{{ s.alignment_status === 'retired' ? '已退役' : s.alignment_status === 'pending' ? '待对齐' : '已对齐' }}</StatusBadge></header>
                <b class="scene-heading">{{ s.heading || `第 ${s.episode_number} 集` }}</b>
                <small>{{ s.location_name || '—' }} · {{ s.interior_exterior || '—' }} · {{ s.time_of_day || '—' }}</small>
                <p v-if="s.summary" class="scene-summary">{{ s.summary }}</p>
              </div>
            </div>
          </GlassPanel>

          <GlassPanel title="连续性事实" description="跨场景需要保持的事实。blocker 未解决时将阻塞下游步骤。" class="facts-panel">
            <div v-if="!facts.length" class="empty-tip">暂无连续性事实。</div>
            <div v-else class="facts-list">
              <div v-for="f in facts" :key="f.id" class="fact-item" :class="'fact-' + f.severity">
                <StatusBadge :tone="f.severity === 'blocker' ? 'danger' : f.severity === 'risk' ? 'warning' : 'neutral'">{{ f.severity === 'blocker' ? '阻塞' : f.severity === 'risk' ? '风险' : '提示' }}</StatusBadge>
                <div class="fact-body">
                  <b>{{ f.subject_key }}</b>
                  <p>{{ f.fact }}</p>
                  <small v-if="f.from_scene_key">{{ f.from_scene_key }} → {{ f.to_scene_key || '后续' }}</small>
                </div>
                <div class="fact-actions">
                  <template v-if="f.status === 'open'">
                    <V2Button variant="ghost" @click="resolveFact(f.id)">标记解决</V2Button>
                  </template>
                  <StatusBadge v-else tone="success">已解决</StatusBadge>
                </div>
              </div>
            </div>
          </GlassPanel>
        </template>

        <!-- 步骤 4：风格圣经 + 色卡 + Checkpoint B -->
        <template v-else-if="viewingStep === 4">
          <GlassPanel title="风格圣经候选" description="批准一个候选后进入 Checkpoint B。已批准版本不可原地修改，修改需派生新候选。">
            <template #actions>
              <V2Button variant="primary" :disabled="creatingStyle" @click="createStyleFromBrief">{{ creatingStyle ? '创建中…' : '从创作简报生成候选' }}</V2Button>
            </template>
            <div v-if="checkpointB" class="cpb-banner" :class="checkpointB.passed ? 'wb-success' : 'wb-error'">
              Checkpoint B：{{ checkpointB.passed ? '✅ 已通过（风格 v' + checkpointB.style_version + ' + 色卡已关联）' : '❌ 未通过 — ' + (checkpointB.reason || '') }}
            </div>
            <div v-if="!styleBibles.length" class="empty-tip">暂无风格候选。点击「从创作简报生成候选」开始。</div>
            <div v-else class="style-grid">
              <div v-for="b in styleBibles" :key="b.id" class="style-card" :class="{ selected: selectedStyleId === b.id }" @click="selectedStyleId = b.id">
                <header>
                  <b>{{ b.name }}</b>
                  <StatusBadge :tone="b.status === 'approved' ? 'success' : b.status === 'invalid' ? 'danger' : 'info'">{{ b.status === 'approved' ? '已批准' : b.status === 'candidate' ? '候选' : b.status }}</StatusBadge>
                </header>
                <p class="style-thesis">{{ b.visual_thesis || '—' }}</p>
                <div class="style-meta"><small>{{ b.era }} · {{ b.realism }} · {{ b.aspect_ratio }}</small></div>
                <div v-if="b.palettes?.length" class="palette-strip">
                  <div v-for="p in b.palettes" :key="p.id" class="palette-row">
                    <i v-for="(c, ci) in [p.primary_color, p.secondary_color, p.accent_color, p.neutral_color]" :key="ci" class="color-dot" :style="{ background: c || 'transparent' }" :title="[p.primary_color, p.secondary_color, p.accent_color, p.neutral_color][ci]" />
                    <small>{{ p.name || '色卡' }}<template v-if="p.time_variant"> · {{ p.time_variant }}</template></small>
                  </div>
                </div>
                <div class="style-actions">
                  <V2Button v-if="b.status === 'candidate'" variant="primary" @click="approveStyle(b.id)">批准</V2Button>
                  <small v-else-if="b.status === 'approved'">批准于 {{ new Date(b.approved_at).toLocaleDateString() }}</small>
                </div>
              </div>
            </div>
          </GlassPanel>
        </template>

        <!-- 步骤 5：角色/道具锚点 + Checkpoint C -->
        <template v-else-if="viewingStep === 5">
          <GlassPanel title="角色与道具锚点" description="身份锚点与可控变量严格分离。Checkpoint C 要求逐实体审批，不允许全局自动通过。">
            <template #actions>
              <V2Button variant="primary" :disabled="creatingStyle" @click="createAnchorsFromWorld">{{ creatingStyle ? '创建中…' : '从世界设定生成候选' }}</V2Button>
            </template>
            <div v-if="error" class="wb-error">{{ error }}</div>
            <div v-if="sceneSyncResult" class="wb-success">{{ sceneSyncResult }}</div>
            <div v-if="checkpointC" class="cpb-banner" :class="checkpointC.passed ? 'wb-success' : 'wb-error'">
              Checkpoint C：{{ checkpointC.passed ? '✅ 已通过（所有锚点逐实体批准）' : `❌ 未通过 — ${checkpointC.reason}` }}
            </div>
            <div v-if="!charAnchors.length && !propAnchors.length" class="empty-tip">
              暂无锚点。确认已批准风格圣经后，点击「从世界设定生成候选」。
            </div>

            <!-- 角色锚点 -->
            <h4 class="section-title">👤 角色锚点（{{ checkpointC?.character_approved || 0 }}/{{ checkpointC?.character_total || 0 }} 已批准）</h4>
            <div v-if="charAnchors.length" class="anchor-list">
              <div v-for="a in charAnchors" :key="a.id" class="anchor-card">
                <header>
                  <code>{{ a.stable_key }}</code>
                  <b>{{ a.name }}</b>
                  <StatusBadge :tone="a.priority === 'protagonist' ? 'info' : 'neutral'">{{ a.priority === 'protagonist' ? '主角' : a.priority === 'supporting' ? '配角' : '群演' }}</StatusBadge>
                  <StatusBadge :tone="a.status === 'approved' ? 'success' : 'warning'">{{ a.status === 'approved' ? '已批准' : '待审批' }}</StatusBadge>
                </header>
                <div class="anchor-sections">
                  <div class="anchor-section">
                    <label>不可变身份锚点</label>
                    <div v-if="dictFields(a.identity_anchor).length" class="anchor-fields">
                      <div v-for="(f, fi) in dictFields(a.identity_anchor)" :key="fi" class="anchor-field">
                        <span class="anchor-field-label">{{ f.label }}</span>
                        <span class="anchor-field-value">{{ f.value }}</span>
                      </div>
                    </div>
                    <small v-else class="anchor-empty">暂无身份锚点数据</small>
                  </div>
                  <div class="anchor-section">
                    <label>可控变量</label>
                    <div v-if="dictFields(a.controllable_vars).length" class="anchor-fields">
                      <div v-for="(f, fi) in dictFields(a.controllable_vars)" :key="fi" class="anchor-field">
                        <span class="anchor-field-label">{{ f.label }}</span>
                        <span class="anchor-field-value">{{ f.value }}</span>
                      </div>
                    </div>
                    <small v-else class="anchor-empty">暂无可控变量</small>
                  </div>
                  <div class="anchor-section" v-if="a.drift_prohibition?.length">
                    <label>禁止漂移</label>
                    <ul><li v-for="(d, di) in a.drift_prohibition" :key="di">{{ d }}</li></ul>
                  </div>
                </div>
                <div class="anchor-actions">
                  <V2Button v-if="a.status === 'candidate'" variant="primary" @click="approveCharAnchor(a.id)">批准锚点</V2Button>
                  <small v-else-if="a.status === 'approved'">✓ 批准</small>
                </div>
              </div>
            </div>
            <p v-else class="empty-tip">暂无角色锚点。</p>

            <!-- 道具锚点 -->
            <h4 class="section-title">道具锚点（{{ checkpointC?.prop_approved || 0 }}/{{ checkpointC?.prop_total || 0 }} 已批准）</h4>
            <div v-if="propAnchors.length" class="anchor-list">
              <div v-for="a in propAnchors" :key="a.id" class="anchor-card">
                <header>
                  <code>{{ a.stable_key }}</code>
                  <b>{{ a.name }}</b>
                  <StatusBadge :tone="a.status === 'approved' ? 'success' : 'warning'">{{ a.status === 'approved' ? '已批准' : '待审批' }}</StatusBadge>
                </header>
                <div class="anchor-sections">
                  <div class="anchor-section">
                    <label>属性</label>
                    <small>{{ a.size || '—' }} · {{ a.material || '—' }} · {{ a.wear_condition || '无磨损' }}</small>
                  </div>
                </div>
                <div class="anchor-actions">
                  <V2Button v-if="a.status === 'candidate'" variant="primary" @click="approvePropAnchor(a.id)">批准锚点</V2Button>
                  <small v-else-if="a.status === 'approved'">批准</small>
                </div>
              </div>
            </div>
            <p v-else class="empty-tip">暂无道具锚点。</p>
          </GlassPanel>
        </template>

        <!-- 步骤 6：空间拓扑 / 内景平面图 / 关键视图 -->
        <template v-else-if="viewingStep === 6">
          <GlassPanel title="空间结构版本" description="外景拓扑 / 内景平面图。视图必须挂在空间结构版本下，不能反向覆盖空间。">
            <div v-if="!spatialPlans.length" class="empty-tip">
              暂无空间结构。从场景台账中的地点稳定键（LOC-xxx）创建外景拓扑或内景平面图。
            </div>
            <div v-else class="spatial-grid">
              <div v-for="plan in spatialPlans" :key="plan.id" class="spatial-card" :class="{ invalid: plan.status === 'invalid' }">
                <header>
                  <code>{{ plan.location_stable_key }}</code>
                  <StatusBadge :tone="plan.status === 'approved' ? 'success' : plan.status === 'invalid' ? 'danger' : 'info'">
                    {{ plan.status === 'approved' ? '已批准' : plan.status === 'invalid' ? '校验失败' : plan.status === 'candidate' ? '候选' : plan.status }}
                  </StatusBadge>
                </header>
                <b>{{ plan.name }}</b>
                <small>{{ plan.plan_kind === 'exterior' ? '外景拓扑' : '内景平面图' }} · v{{ plan.version }}</small>
                <details v-if="plan.plan_kind === 'exterior'"><summary>拓扑数据</summary><pre>{{ JSON.stringify(plan.topology, null, 2) }}</pre></details>
                <details v-else><summary>平面图数据</summary><pre>{{ JSON.stringify(plan.floor_plan, null, 2) }}</pre></details>
                <div class="anchor-actions">
                  <V2Button v-if="plan.status === 'candidate'" variant="primary" @click="approveSpatialPlan(plan.id)">批准结构</V2Button>
                  <V2Button variant="ghost" @click="createViewForPlan(plan.id, plan.location_stable_key)">+ 关键视图</V2Button>
                </div>
                <!-- 关键视图列表 -->
                <div v-if="locationViews[plan.id]?.length" class="view-list">
                  <div v-for="v in locationViews[plan.id]" :key="v.id" class="view-item">
                    <code>{{ v.stable_key }}</code>
                    <span>{{ v.name }}</span>
                    <StatusBadge v-if="v.status !== 'open'" :tone="v.status === 'approved' ? 'success' : v.status === 'stale' ? 'warning' : 'neutral'">{{ v.status === 'approved' ? '已批准' : v.status === 'stale' ? '已过期' : v.status }}</StatusBadge>
                    <V2Button v-if="v.status === 'candidate'" variant="ghost" @click="approveView(v.id, plan.id)">批准</V2Button>
                  </div>
                </div>
              </div>
            </div>
          </GlassPanel>
        </template>

        <!-- 步骤 7：Manifest + 连续性审计 -->
        <template v-else-if="viewingStep === 7">
          <ManifestStep :project-id="projectId" />
          <StaleDependencyView :project-id="projectId" />
          <ContinuityPanel :project-id="projectId" />
        </template>

        <!-- 其他步骤占位 -->
        <GlassPanel v-else :title="`步骤 ${viewingStep}：${STEPS[viewingStep]?.label || ''}`" :description="'该步骤的编辑器将在后续轮次接入。'">
          <div class="placeholder">
            <p>规则状态已就绪。当前工作流状态：<b>{{ state.status }}</b></p>
            <p v-if="viewingStep < state.current_step" class="readonly-hint">此步骤已完成，以下为门禁操作（只读模式下不会影响当前进度）。</p>
            <p>门禁操作：</p>
            <div class="gate-actions">
              <V2Button variant="ghost" @click="setGate(viewingStep, 'passed')">标记通过</V2Button>
              <V2Button variant="ghost" @click="setGate(viewingStep, 'blocked')">标记阻塞</V2Button>
              <V2Button variant="ghost" @click="setGate(viewingStep, 'waived')">标记豁免</V2Button>
            </div>
          </div>
        </GlassPanel>
      </main>
    </div>

    <!-- AI 导演助手抽屉（第 9 轮：建议 + 对话 + 候选提案） -->
    <div v-if="aiPanelOpen" class="ai-drawer">
      <div class="ai-drawer-head">
        <b>AI 导演助手</b>
        <button class="ai-drawer-close" @click="aiPanelOpen = false">✕</button>
      </div>
      <div class="ai-drawer-body">
        <GuidancePanel :project-id="projectId" @edit-prompt="(code: string, title: string) => { promptEditorCode = code; promptEditorTitle = title; promptEditorVisible = true }" />
        <DirectorChat :project-id="projectId" @edit-prompt="(code: string, title: string) => { promptEditorCode = code; promptEditorTitle = title; promptEditorVisible = true }" />
        <AICallLogPanel :project-id="projectId" />
      </div>
    </div>

    <!-- AI 提示词编辑弹窗 -->
    <PromptTemplateEditor
      :visible="promptEditorVisible"
      :code="promptEditorCode"
      :title="promptEditorTitle"
      @close="promptEditorVisible = false"
    />
  </div>
</template>

<style scoped>
.heading{display:flex;align-items:flex-end;justify-content:space-between;gap:16px}.heading h1{margin-top:14px}.heading-actions{display:flex;gap:8px}
.loading{min-height:50vh;display:grid;place-items:center;color:var(--v2-text-muted)}
.load-error{margin-top:16px;padding:16px;display:flex;align-items:center;justify-content:space-between;color:var(--v2-danger);background:rgba(255,127,145,.08);border-radius:12px}
.empty-state{margin-top:40px;display:grid;place-items:center;gap:16px;color:var(--v2-text-muted)}
.workbench{display:grid;grid-template-columns:300px minmax(0,1fr);gap:16px;margin-top:16px;align-items:start}
.job-status-bar{grid-column:1/-1;display:flex;gap:10px;flex-wrap:wrap;padding:10px 14px;background:var(--v2-surface);border:1px solid var(--v2-border);border-radius:12px;margin-bottom:4px}
.job-status-item{display:flex;align-items:center;gap:8px;padding:6px 12px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:9px;font-size:11px}
.job-name{color:var(--v2-text);max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500}
.job-mini-bar{width:60px;height:3px;background:rgba(255,255,255,.08);border-radius:99px;overflow:hidden}
.job-mini-bar span{display:block;height:100%;background:linear-gradient(90deg,#6f86ff,#aa70e8);transition:width .3s}
.job-error-text{color:var(--v2-danger);font-size:10px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.step-nav{padding:14px;display:grid;gap:6px;background:var(--v2-surface);border:1px solid var(--v2-border);border-radius:16px;position:sticky;top:90px}
.step-nav-head{display:flex;align-items:center;justify-content:space-between;padding:4px 4px 10px;border-bottom:1px solid var(--v2-border)}
.step-nav-head b{font-size:13px}.step-nav-head small{color:var(--v2-text-muted)}
.step-item{min-height:44px;padding:8px 10px;display:flex;align-items:center;gap:10px;color:var(--v2-text-muted);background:transparent;border:1px solid transparent;border-radius:10px;cursor:pointer;text-align:left}
.step-item.current{color:var(--v2-text);background:rgba(130,149,255,.08);border-color:rgba(130,149,255,.2)}
.step-item.done{color:var(--v2-success);opacity:.85}
.step-item.done i{border-color:var(--v2-success);color:var(--v2-success)}
.step-item:disabled{opacity:.45;cursor:not-allowed}
.step-item i{width:26px;height:26px;flex-shrink:0;display:grid;place-items:center;border:1px solid var(--v2-border);border-radius:50%;font-style:normal;font-size:11px}
.step-item .step-label{flex:1;min-width:0;display:grid;gap:2px}
.step-item .step-label b{font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.step-item .step-label small{font-size:10px;color:var(--v2-text-subtle)}
.advance-btn{margin-top:8px}
.step-nav-actions{display:flex;gap:6px;margin-top:8px}
.readonly-banner{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:8px 14px;margin-bottom:12px;background:rgba(255,183,77,.08);border:1px solid rgba(255,183,77,.2);border-radius:10px;color:#ffb347;font-size:12px}
.readonly-hint{color:var(--v2-text-subtle);font-size:11px}
.placeholder{padding:20px;display:grid;gap:12px;color:var(--v2-text-muted)}
.placeholder b{color:var(--v2-text)}
.gate-actions{display:flex;gap:8px;flex-wrap:wrap}
.analysis-select{min-height:36px;padding:6px 10px;color:var(--v2-text);background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:9px;font-size:12px}
.wb-error{padding:10px;color:#ffdce1;background:rgba(255,127,145,.1);border-radius:10px;font-size:12px}
.wb-success{padding:10px;color:#a7f3d0;background:rgba(79,209,165,.1);border-radius:10px;font-size:12px}
.global-feedback{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}
.fb-close{padding:0 6px;color:inherit;background:transparent;border:1px solid rgba(255,255,255,.2);border-radius:6px;cursor:pointer;font-size:12px;flex-shrink:0}
.fb-close:hover{opacity:.8}
.ledger-tabs{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}
.ledger-tab{display:flex;align-items:center;gap:6px;padding:7px 12px;color:var(--v2-text-muted);background:transparent;border:1px solid var(--v2-border);border-radius:9px;cursor:pointer;font-size:12px}
.ledger-tab.active{color:var(--v2-text);background:rgba(130,149,255,.1);border-color:rgba(130,149,255,.35)}
.ledger-summary{margin:0 0 14px;padding:11px 13px;color:var(--v2-text-muted);background:var(--v2-surface-soft);border-radius:10px;font-size:13px;line-height:1.7}
.section-title{margin:20px 0 10px;font-size:14px;color:#e8edff}
.empty-tip{color:var(--v2-text-subtle);font-size:12px}
.scene-empty{display:grid;gap:8px;padding:16px 0}
.scene-empty p{margin:0}
.scene-empty-hint{color:var(--v2-text-muted);line-height:1.6}
.scene-empty-actions{display:flex;gap:8px;margin-top:4px}
.manual-create-box{display:grid;gap:10px;padding:12px 14px;margin-bottom:12px;background:rgba(130,149,255,.04);border:1px solid var(--v2-border);border-radius:10px}
.manual-create-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.manual-create-grid label{display:grid;gap:5px}
.manual-create-grid span{font-size:11px;color:var(--v2-text-subtle)}
.scene-input{width:100%;padding:8px 10px;color:var(--v2-text);background:rgba(3,8,17,.72);border:1px solid var(--v2-border);border-radius:8px;font-size:12px}
.scene-input:focus{border-color:var(--v2-primary);outline:none}
.manual-create-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.manual-create-actions small{color:var(--v2-text-subtle);font-size:10px}
@media(max-width:650px){.manual-create-grid{grid-template-columns:1fr}}
details pre{margin-top:6px;max-height:200px;overflow:auto;font-size:11px;background:rgba(0,0,0,.3);padding:8px;border-radius:8px}
.curve-summary-boxes{display:flex;flex-direction:column;gap:5px;margin-top:8px;color:#ffb347;font-size:12px}
.beat-table{overflow-x:auto;border:1px solid var(--v2-border);border-radius:10px}
.beat-table table{width:100%;border-collapse:collapse;font-size:11px}
.beat-table th{position:sticky;top:0;padding:8px 10px;text-align:left;color:var(--v2-text-subtle);background:var(--v2-surface-soft);white-space:nowrap;border-bottom:1px solid var(--v2-border)}
.beat-table td{padding:8px 10px;color:var(--v2-text-muted);vertical-align:top;border-bottom:1px solid rgba(130,149,255,.06)}
.beat-table code{color:var(--v2-primary);font-size:11px}
.wrap-cell{max-width:220px;line-height:1.5}
.loc-cell{max-width:100px}
small.assumed{color:#ffb347}
.decisions{display:grid;gap:10px}
.decision-item{padding:12px;display:grid;gap:8px;background:var(--v2-surface-soft);border:1px solid rgba(255,183,77,.18);border-radius:10px}
.decision-item b{font-size:12px;color:#e8edff}
.decision-options{display:flex;gap:6px;flex-wrap:wrap}
.decision-options button{padding:6px 12px;color:#c8d0ee;background:rgba(130,149,255,.08);border:1px solid rgba(130,149,255,.18);border-radius:8px;cursor:pointer;font-size:11px;text-align:left}
.decision-options button:hover:not(:disabled){background:rgba(130,149,255,.16)}
.decision-options button:disabled{opacity:.45;cursor:not-allowed}
.decision-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.custom-input{flex:1;min-width:160px;padding:6px 10px;color:var(--v2-text);background:rgba(3,8,17,.72);border:1px solid var(--v2-border);border-radius:8px;font-size:11px}
.approve-row{display:grid;gap:8px;margin-top:24px;padding-top:16px;border-top:1px solid var(--v2-border);justify-items:start}
.approve-row small{color:var(--v2-text-subtle)}
.scene-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px}
.scene-card{padding:12px;display:grid;gap:7px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:10px}
.scene-card.retired{opacity:.5}
.scene-card header{display:flex;align-items:center;justify-content:space-between;gap:8px}
.scene-card header code{color:var(--v2-primary);font-size:11px}
.scene-heading{font-size:12px;color:var(--v2-text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.scene-card small{color:var(--v2-text-subtle);font-size:11px}
.scene-summary{margin:0;color:var(--v2-text-muted);font-size:11px;line-height:1.5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.facts-panel{margin-top:16px}
.facts-list{display:grid;gap:8px}
.fact-item{padding:11px;display:flex;align-items:flex-start;gap:10px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:10px}
.fact-item.fact-blocker{border-color:rgba(255,127,145,.3);background:rgba(255,127,145,.06)}
.fact-item.fact-risk{border-color:rgba(255,183,77,.25)}
.fact-body{flex:1;min-width:0;display:grid;gap:4px}
.fact-body b{font-size:12px;color:var(--v2-primary)}
.fact-body p{margin:0;font-size:12px;color:var(--v2-text);line-height:1.5}
.fact-body small{color:var(--v2-text-subtle);font-size:10px}
.fact-actions{flex-shrink:0}
.cpb-banner{margin-bottom:14px}
.style-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
.style-card{padding:14px;display:grid;gap:9px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:12px;cursor:pointer;transition:.15s}
.style-card:hover{border-color:rgba(130,149,255,.35)}
.style-card.selected{border-color:var(--v2-primary);box-shadow:0 0 0 1px var(--v2-primary)}
.style-card header{display:flex;align-items:center;justify-content:space-between;gap:8px}
.style-card header b{font-size:13px;color:var(--v2-text)}
.style-thesis{margin:0;color:var(--v2-text-muted);font-size:12px;line-height:1.6}
.style-meta small{color:var(--v2-text-subtle);font-size:11px}
.palette-strip{display:grid;gap:5px}
.palette-row{display:flex;align-items:center;gap:5px}
.palette-row small{color:var(--v2-text-subtle);font-size:10px;margin-left:4px}
.color-dot{width:16px;height:16px;border-radius:4px;border:1px solid rgba(255,255,255,.15);display:inline-block}
.style-actions{display:flex;align-items:center;gap:8px;margin-top:4px}
.style-actions small{color:var(--v2-text-subtle)}
.anchor-list{display:grid;gap:12px}
.anchor-card{padding:14px;display:grid;gap:10px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:12px}
.anchor-card header{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.anchor-card header code{color:var(--v2-primary);font-size:11px}
.anchor-card header b{font-size:13px;color:var(--v2-text);flex:1}
.anchor-sections{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}
.anchor-section label{display:block;font-size:11px;color:var(--v2-text-subtle);margin-bottom:5px}
.anchor-section pre{margin:0;padding:8px;background:rgba(0,0,0,.25);border-radius:8px;font-size:10px;color:var(--v2-text-muted);max-height:120px;overflow:auto;white-space:pre-wrap;word-break:break-word}
.anchor-section ul{margin:0;padding-left:14px;color:var(--v2-text-muted);font-size:11px;line-height:1.6}
.anchor-fields{display:grid;gap:5px}
.anchor-field{display:flex;gap:8px;align-items:baseline;padding:5px 8px;background:rgba(0,0,0,.18);border-radius:7px}
.anchor-field-label{flex-shrink:0;min-width:56px;font-size:10px;color:var(--v2-primary);font-weight:600}
.anchor-field-value{font-size:11px;color:var(--v2-text);line-height:1.5;word-break:break-word}
.anchor-empty{font-size:10px;color:var(--v2-text-subtle)}
.anchor-section small{color:var(--v2-text-muted);font-size:11px}
.anchor-actions{display:flex;align-items:center;gap:8px}
.anchor-actions small{color:var(--v2-success)}
.spatial-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.spatial-card{padding:14px;display:grid;gap:9px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:12px}
.spatial-card.invalid{border-color:rgba(255,127,145,.3)}
.spatial-card header{display:flex;align-items:center;justify-content:space-between;gap:8px}
.spatial-card header code{color:var(--v2-primary);font-size:11px}
.spatial-card b{font-size:12px;color:var(--v2-text)}
.spatial-card small{color:var(--v2-text-subtle);font-size:11px}
.spatial-card details{font-size:11px;color:var(--v2-text-subtle)}
.spatial-card details summary{cursor:pointer}
.spatial-card details pre{margin-top:6px;max-height:160px;overflow:auto;font-size:10px;background:rgba(0,0,0,.3);padding:8px;border-radius:8px}
.view-list{display:grid;gap:5px;padding-top:8px;border-top:1px solid var(--v2-border)}
.view-item{display:flex;align-items:center;gap:8px;font-size:11px;color:var(--v2-text-muted);flex-wrap:wrap}
.view-item code{color:var(--v2-primary);font-size:10px}
.view-item span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
@media(max-width:900px){.workbench{grid-template-columns:1fr}.step-nav{position:static}}
.ai-drawer{position:fixed;right:0;top:64px;bottom:0;width:min(480px,92vw);z-index:60;background:var(--v2-surface);border-left:1px solid var(--v2-border);box-shadow:-16px 0 40px rgba(0,0,0,.4);overflow-y:auto}
.ai-drawer-head{position:sticky;top:0;z-index:1;display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:var(--v2-surface);border-bottom:1px solid var(--v2-border)}
.ai-drawer-head b{font-size:14px;color:var(--v2-text)}
.ai-drawer-close{width:28px;height:28px;display:grid;place-items:center;color:var(--v2-text-muted);background:transparent;border:1px solid var(--v2-border);border-radius:8px;cursor:pointer;font-size:14px}
.ai-drawer-close:hover{color:var(--v2-text);border-color:var(--v2-primary)}
.ai-drawer-body{padding:16px;display:grid;gap:16px}
@media(max-width:900px){.ai-drawer{top:auto;height:70vh;border-top:1px solid var(--v2-border);border-left:none}}
</style>