<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { shortDramaApi, type ScriptManifest } from '@/api/modules'
import DramaProjectShell from './DramaProjectShell.vue'
import V2Button from '@/v2/components/V2Button.vue'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => Number(route.params.projectId))
const episodeId = computed(() => Number(route.params.episodeId))
const item = ref<ScriptManifest | null>(null)
const versions = ref<ScriptManifest[]>([])
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const dirty = ref(false)
const unlocking = ref(false)
const reviewing = ref(false)
const splitPreview = ref<any>(null)
const applyingSplit = ref(false)
let suppress = true
let saveTimer: ReturnType<typeof setTimeout> | null = null
const frameStrategies: Array<[string, string]> = [
  ['first', '首帧'], ['last', '尾帧'], ['first_last', '首尾帧'], ['multi', '多关键帧'],
]
const adviceCounts = computed(() => Object.fromEntries(['p0', 'p1', 'p2'].map(level => [level, item.value?.validation_errors.filter(issue => issue.severity === level).length || 0])))
const shotCount = computed(() => item.value?.content.scenes.reduce((sum, scene: any) => sum + (scene.shots?.length || 0), 0) || 0)
const isConfirmed = computed(() => item.value?.status === 'confirmed')
const readOnly = computed(() => isConfirmed.value || !!splitPreview.value || applyingSplit.value)
const saveState = computed(() => saving.value ? '保存中…' : error.value ? '保存失败' : isConfirmed.value ? '已确认并锁定' : splitPreview.value ? '拆镜预览中' : dirty.value ? '有未保存修改' : '已自动保存')

function normalizeStrategy(s: any): string {
  const map: Record<string, string> = {
    '首帧': 'first', 'first': 'first',
    '尾帧': 'last', 'last': 'last',
    '首尾帧': 'first_last', 'first_last': 'first_last', 'first-last': 'first_last', 'both': 'first_last',
    '多关键帧': 'multi', 'multi': 'multi', '多帧': 'multi',
  }
  return map[String(s || '').trim()] || 'first_last'
}
function ensureKeyframePlan(shot: any) {
  if (!shot || typeof shot !== 'object') return
  if (!shot.keyframe_plan || typeof shot.keyframe_plan !== 'object') {
    shot.keyframe_plan = { strategy: 'first_last', first_frame_prompt: '', last_frame_prompt: '', keyframes: [] }
  }
  const kp = shot.keyframe_plan
  kp.strategy = normalizeStrategy(kp.strategy)
  kp.first_frame_prompt ||= ''
  kp.last_frame_prompt ||= ''
  if (!Array.isArray(kp.keyframes)) kp.keyframes = []
}
function showFirstFrame(shot: any) { return ['first', 'first_last', 'multi'].includes(shot.keyframe_plan?.strategy) }
function showLastFrame(shot: any) { return ['last', 'first_last', 'multi'].includes(shot.keyframe_plan?.strategy) }
function setStrategy(shot: any, s: string) {
  ensureKeyframePlan(shot)
  shot.keyframe_plan.strategy = s
  if (s === 'multi' && !shot.keyframe_plan.keyframes.length) {
    shot.keyframe_plan.keyframes = [
      { index: 1, label: '首帧', prompt: shot.keyframe_plan.first_frame_prompt || '' },
      { index: 2, label: '中帧', prompt: '' },
      { index: 3, label: '尾帧', prompt: shot.keyframe_plan.last_frame_prompt || '' },
    ]
  }
}
function addKeyframe(shot: any) {
  ensureKeyframePlan(shot)
  const idx = shot.keyframe_plan.keyframes.length + 1
  shot.keyframe_plan.keyframes.push({ index: idx, label: `关键帧 ${idx}`, prompt: '' })
}
function removeKeyframe(shot: any, i: number) { shot.keyframe_plan?.keyframes.splice(i, 1) }
function ensureDialogueLines(shot: any) {
  if (!Array.isArray(shot.dialogue_lines)) shot.dialogue_lines = []
}
const promptLabels: Record<string, string> = {base_visual:'画面',visual_style:'风格',camera_movement:'运镜',composition_guide:'构图',initial_frame:'起始帧',character_consistency:'角色一致性',negative_constraints:'负面约束'}
function shotTotal(shot: any) { return Number(shot.duration || 0) + (shot.timing_schema_version === 2 ? 0 : Number(shot.reaction_pause || 0)) }
const totalSeconds = computed(() => item.value?.content.scenes.reduce((sum, scene: any) => sum + scene.shots.reduce((n: number, shot: any) => n + shotTotal(shot), 0), 0).toFixed(1))
const SHOT_JOB_OPTIONS = ['改变情绪', '推进动作', '施加压力']
function toggleShotJob(shot: any, job: string) {
  const jobs = new Set(shot.shot_jobs || [])
  if (jobs.has(job)) jobs.delete(job); else jobs.add(job)
  shot.shot_jobs = SHOT_JOB_OPTIONS.filter(item => jobs.has(item))
}
function toggleName(list: string[] | undefined, shot: any, key: 'character_names' | 'prop_names', name: string) {
  const current = new Set(shot[key] || [])
  if (current.has(name)) current.delete(name); else current.add(name)
  shot[key] = [...current]
  void list
}
async function load() {
  suppress = true
  try {
    const list = await shortDramaApi.scriptManifests(projectId.value, episodeId.value)
    versions.value = list
    item.value = list.find(x => x.id === Number(route.query.version)) || list[0] || null
    item.value?.content.scenes.forEach((s: any) => (s.shots || []).forEach((shot: any) => { ensureKeyframePlan(shot); ensureDialogueLines(shot) }))
    await nextTick(); suppress = false
  } catch (e: any) { error.value = e.response?.data?.detail || '拍摄清单加载失败' }
  finally { loading.value = false }
}
async function save(): Promise<boolean> {
  if (!item.value || readOnly.value || saving.value) return false
  if (saveTimer) { clearTimeout(saveTimer); saveTimer = null }
  const id = item.value.id
  const snapshot = JSON.stringify({summary:item.value.summary,content:item.value.content})
  const payload = {lock_version:item.value.lock_version, ...JSON.parse(snapshot)}
  saving.value = true; error.value = ''
  try {
    const saved = await shortDramaApi.saveScriptManifest(projectId.value, episodeId.value, id, payload)
    if (item.value?.id !== id) return false
    const changed = snapshot !== JSON.stringify({summary:item.value.summary,content:item.value.content})
    suppress = true
    if (changed) item.value.lock_version = saved.lock_version
    else item.value = saved
    await nextTick(); suppress = false; dirty.value = changed
    if (changed) { scheduleSave(); return false }
    return true
  } catch (e: any) { error.value = e.response?.data?.detail || '保存失败'; return false }
  finally { saving.value = false }
}
async function confirmManifest() {
  if (!item.value || readOnly.value) return
  if (!await save()) return
  if (!window.confirm('确认后将固化拍摄清单并生成 V6.5 数字资产需求，下一步进入资产图册。继续吗？')) return
  try {
    item.value = await shortDramaApi.confirmScriptManifest(projectId.value, episodeId.value, item.value.id)
    await router.push({path:'/v2/drama/projects/'+projectId.value+'/assets',query:{episode_id:episodeId.value}})
  } catch (e: any) { error.value = e.response?.data?.detail || e.message || '拍摄清单确认失败' }
}

function blankShot(no: string) {
  return {
    shot_no: no, title: `镜头 ${no}`,
    content: '', character_names: [], prop_names: [], mood: '',
    shot_size: '中景', camera_angle: '平视', camera_movement: '固定', transition: '', duration: 3,
    timing_schema_version: 2, reaction_pause: 0, shot_jobs: [], dialogue_lines: [],
    keyframe_plan: { strategy: 'first_last', first_frame_prompt: '', last_frame_prompt: '', keyframes: [] },
  }
}
/** 场景内重编号：镜号按顺序重排为 1..n，空标题补默认；跨场景时同时刷新全局 shot_no（S-场景-镜）。 */
function renumberShots(scene: any) {
  scene.shots.forEach((s: any, i: number) => {
    s.shot_no = String(i + 1)
    s.title ||= `镜头 ${i + 1}`
  })
}
function addShot(scene: any) {
  scene.shots.push(blankShot(String(scene.shots.length + 1)))
  renumberShots(scene)
}
function insertShot(scene: any, hi: number) {
  scene.shots.splice(hi + 1, 0, blankShot(''))
  renumberShots(scene)
}
function removeShot(scene: any, hi: number) {
  scene.shots.splice(hi, 1)
  renumberShots(scene)
}
async function applySuggestion(issue: any) {
  if (!item.value || readOnly.value) return
  const payload = issue.action_payload || {}
  if (issue.action === 'rebuild_cast') {
    const names: string[] = payload.names || []
    const existing = new Set((item.value.content.characters || []).map((c: any) => c.name))
    names.forEach((name, index) => {
      if (existing.has(name)) return
      item.value!.content.characters.push({ stable_key: `CHR-${String(item.value!.content.characters.length + 1).padStart(3, '0')}`, name, asset_grade: 'B', visual_prompt: '' })
    })
    dirty.value = true; scheduleSave()
    return
  }
  const scene = item.value.content.scenes?.[payload.scene_index]
  const shot = scene?.shots?.[payload.shot_index]
  if (!shot) return
  if (issue.action === 'set_duration') shot.duration = Number(payload.duration || 15)
  else if (issue.action === 'set_camera_angle') shot.camera_angle = payload.camera_angle || '45°斜侧平视'
  else if (issue.action === 'set_shot_job') shot.shot_jobs = [...new Set([...(shot.shot_jobs || []), payload.job || '推进动作'])]
  else if (issue.action === 'add_reaction_pause') shot.reaction_pause = Number(payload.reaction_pause || .5)
  else if (issue.action === 'split_dialogue') {
    if (!await save()) return
    try {
      splitPreview.value = await shortDramaApi.previewScriptManifestSplit(projectId.value, episodeId.value, item.value.id, {
        lock_version:item.value.lock_version, scene_index:payload.scene_index, shot_index:payload.shot_index,
      })
    } catch (e: any) { error.value = e.response?.data?.detail || '拆镜预览失败' }
    return
  } else {
    console.warn('未处理的建议动作', issue.action)
    return
  }
  dirty.value = true; scheduleSave()
}
async function applySplit() {
  if (!item.value || !splitPreview.value || applyingSplit.value) return
  applyingSplit.value = true
  try {
    const saved = await shortDramaApi.applyScriptManifestSplit(projectId.value, episodeId.value, item.value.id, splitPreview.value)
    suppress = true; item.value = saved
    item.value.content.scenes.forEach((scene: any) => scene.shots.forEach(ensureKeyframePlan))
    await nextTick(); suppress = false; dirty.value = false; splitPreview.value = null
  } catch (e: any) { error.value = e.response?.data?.detail || '拆镜应用失败，请取消后重新预览' }
  finally { applyingSplit.value = false }
}
function shotIssues(si: number, hi: number) {
  if (!item.value) return [] as any[]
  const prefix = `scenes[${si}].shots[${hi}]`
  return item.value.validation_errors.filter((issue: any) => {
    const p = String(issue.path || '')
    return p === prefix || p.startsWith(prefix + '.')
  })
}
async function unlockManifest() {
  if (!item.value) return
  if (!window.confirm('解锁后拍摄清单回到可编辑状态；已生成的场景/镜头/角色素材保留，重新确认时会重建场景与镜头。继续吗？')) return
  unlocking.value = true; error.value = ''
  try {
    const unlocked = await shortDramaApi.unlockScriptManifest(projectId.value, episodeId.value, item.value.id)
    item.value = unlocked
    versions.value = await shortDramaApi.scriptManifests(projectId.value, episodeId.value)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '解锁失败'
  } finally { unlocking.value = false }
}
async function reviewManifest() {
  if (!item.value || readOnly.value) return
  reviewing.value = true; error.value = ''
  try {
    if (dirty.value && !await save()) return
    const reviewed = await shortDramaApi.reviewScriptManifest(projectId.value, episodeId.value, item.value.id)
    suppress = true; item.value = reviewed; await nextTick(); suppress = false
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '复核失败'
  } finally { reviewing.value = false }
}
function scheduleSave() { if (readOnly.value) return; if (saveTimer) clearTimeout(saveTimer); saveTimer = setTimeout(() => void save(), 1000) }
async function deleteVersion() {
  if (!item.value || versions.value.length <= 1) return
  if (item.value.status === 'confirmed') { error.value = '已确认的版本不可删除，请先解锁'; return }
  if (!window.confirm(`确定删除 V${item.value.version}（${item.value.status === 'confirmed' ? '已确认' : '草稿'}）？此操作不可恢复。`)) return
  try {
    await shortDramaApi.deleteScriptManifest(projectId.value, episodeId.value, item.value.id)
    versions.value = await shortDramaApi.scriptManifests(projectId.value, episodeId.value)
    const next = versions.value[0]
    if (next) void router.replace({ query: { ...route.query, version: next.id } }).then(load)
    else error.value = '已无拍摄清单'
  } catch (e: any) { error.value = e.response?.data?.detail || '删除失败' }
}
function openVersion(event: Event) { const id = Number((event.target as HTMLSelectElement).value); if (id) void router.replace({ query: { ...route.query, version: id } }).then(load) }
watch(item, () => { if (suppress || readOnly.value) return; dirty.value = true; scheduleSave() }, { deep: true })
onMounted(load)
onBeforeUnmount(() => { if (saveTimer) clearTimeout(saveTimer) })
</script>

<template>
  <DramaProjectShell v-if="item" active="manifest" page-title="拍摄清单" :save-state="saveState" :save-tone="error ? 'error' : 'normal'">
    <template #actions><div class="version-actions"><select class="version-switch" :value="item.id" aria-label="拍摄清单版本" @change="openVersion"><option v-for="version in versions" :key="version.id" :value="version.id">V{{ version.version }} · {{ version.status === 'confirmed' ? '已确认' : '草稿' }}</option></select><button v-if="versions.length > 1 && item.status !== 'confirmed'" class="version-delete" title="删除此版本" @click="deleteVersion">✕</button></div></template>
  <div class="manifest-page">
    <header class="topbar">
      <div class="title"><small>SCRIPT MANIFEST · AI ANALYSIS RESULT</small><h1>拍摄清单</h1><input v-model="item.summary" :disabled="readOnly" aria-label="清单摘要"></div>
      <div class="actions"><span class="save-state">{{ saving ? '保存中…' : isConfirmed ? '已锁定' : splitPreview ? '预览中' : '可编辑' }}</span><V2Button variant="ghost" :disabled="saving || readOnly" @click="save">保存修改</V2Button><V2Button v-if="!readOnly" variant="ghost" :disabled="reviewing || saving" @click="reviewManifest">{{ reviewing ? '复核中…' : '复核' }}</V2Button><V2Button v-if="isConfirmed" style="color:#5f4317;background:#f2c063;border-color:#d9a441;font-weight:600" :disabled="unlocking" @click="unlockManifest">{{ unlocking ? '解锁中…' : '解锁修改' }}</V2Button><V2Button variant="primary" :disabled="readOnly" @click="confirmManifest">{{ isConfirmed ? '已确认' : '确认拍摄清单并生成资产需求' }}</V2Button></div>
    </header>
    <section class="summary-bar"><span>版本 V{{ item.version }}</span><b>{{ item.content.scenes.length }} 场</b><b>{{ shotCount }} 镜头</b><b>{{ item.total_duration.toFixed(1) }} 秒</b><span>{{ item.content.characters.length }} 角色</span><span>{{ item.content.locations.length }} 场景素材</span><span>{{ item.content.props.length }} 道具</span><span v-if="item.validation_errors.length" class="advice">建议 P0 {{ adviceCounts.p0 }} · P1 {{ adviceCounts.p1 }} · P2 {{ adviceCounts.p2 }}</span><span :class="['status', item.status]">{{ isConfirmed ? '已确认' : '待确认' }}</span></section>
    <details v-if="item.content.analysis_context" class="summary-bar"><summary>本次分析来源：剧本修订 {{ item.content.analysis_context.script?.script_revision }} · 模板 V{{ item.content.analysis_context.template?.version }}</summary><p>使用提交时的项目和资产快照；后续修改不会追溯影响本次分析。</p><pre>{{ item.content.analysis_context.source_lines?.map((line: any) => line.id + ' ' + line.text).join('\n') }}</pre></details>
    <section v-if="item.validation_errors.length" class="validation"><p>创作建议可忽略，草稿始终可保存。标注“确认前修复”的结构或来源错误会阻止确认。</p><div v-for="(issue, index) in item.validation_errors" :key="index" :class="issue.severity"><b>{{ issue.severity?.toUpperCase?.() || '建议' }}</b><span>{{ issue.message }} <strong v-if="issue.blocking_stage === 'confirm'">（确认前修复）</strong></span><code>{{ issue.path }}</code><button v-if="issue.actionable && !readOnly" @click="applySuggestion(issue)">{{ issue.action_label || '应用建议' }}</button><small v-else>人工复核</small></div></section>

    <div class="workspace">
      <aside class="analysis-panel">
        <section><div class="section-title"><small>STORY SUMMARY</small><h2>故事梗概</h2></div><textarea v-model="item.content.story_summary" :disabled="readOnly" rows="8" placeholder="本集故事梗概"></textarea></section>
        <section><div class="section-title"><small>CAST</small><h2>演员表 · {{ item.content.characters.length }}</h2></div>
          <details v-for="character in item.content.characters" :key="character.stable_key" class="character-card">
            <summary><span>{{ character.stable_key }}</span><b>{{ character.name || '未命名角色' }}</b><small>{{ character.asset_grade ? `${character.asset_grade} 级资产` : '未分级' }}</small></summary>
            <div class="character-fields"><label>角色名<input v-model="character.name" :disabled="readOnly"></label><label>资产等级<select v-model="character.asset_grade" :disabled="readOnly"><option value="A">A · 核心资产</option><option value="B">B · 重要资产</option><option value="C">C · 临时资产</option></select></label><label>角色提示词<textarea v-model="character.visual_prompt" :disabled="readOnly" rows="8" placeholder="完整角色视觉描述；身份、五官、发型、服装、姿态和画面风格统一写在这里。"></textarea></label></div>
          </details>
        </section>
      </aside>

      <main class="scene-list">
        <article v-for="(scene, si) in item.content.scenes" :key="si" class="scene-card">
          <header class="scene-head"><div class="scene-index">SCENE {{ String(si + 1).padStart(2, '0') }}</div><div class="scene-fields"><label class="heading-label">场次标题<input v-model="scene.heading" :disabled="readOnly" class="heading"></label><div class="inline-fields"><label>主场景<input v-model="scene.location_name" :disabled="readOnly"></label><label>子空间 / 机位区域<input v-model="scene.sub_location" :disabled="readOnly"></label><label>时间<input v-model="scene.time_of_day" :disabled="readOnly"></label><label>内 / 外景<input v-model="scene.interior_exterior" :disabled="readOnly"></label></div><div class="inline-fields semantics"><label>节奏<input v-model="scene.rhythm" :disabled="readOnly"></label><label>核心情绪<input v-model="scene.emotion" :disabled="readOnly"></label><label>环境氛围<input v-model="scene.atmosphere" :disabled="readOnly"></label></div></div></header>
          <div class="shots">
            <article v-for="(shot, hi) in scene.shots" :key="hi" class="shot-row">
              <aside class="shot-meta"><div class="shot-id"><small>SHOT</small><input v-model="shot.shot_no" :disabled="readOnly" class="shot-number" aria-label="镜号"><span v-if="shotIssues(si, hi).length" class="shot-issue-badge">{{ shotIssues(si, hi).length }}</span></div><label>景别<input v-model="shot.shot_size" :disabled="readOnly"></label><label>角度<input v-model="shot.camera_angle" :disabled="readOnly"></label><label>运镜<input v-model="shot.camera_movement" :disabled="readOnly"></label><label>转场<input v-model="shot.transition" :disabled="readOnly" placeholder="无"></label><label>{{ shot.timing_schema_version === 2 ? '总时长（含反应）' : '原时长（反应另计）' }}<div class="duration-input"><input v-model.number="shot.duration" :disabled="readOnly" type="number" min="0.1" step="0.1"><i>秒</i></div></label><small>生成预算 {{ shotTotal(shot).toFixed(1) }} 秒</small><label>反应时间<div class="duration-input"><input v-model.number="shot.reaction_pause" :disabled="readOnly" type="number" min="0" step="0.1"><i>秒</i></div></label><div class="shot-jobs"><small>镜头任务</small><div><i v-for="job in shot.shot_jobs || []" :key="job">{{ job }}</i><em v-if="!(shot.shot_jobs || []).length">未指定</em></div><div v-if="!readOnly" class="job-picker"><button v-for="job in ['改变情绪', '推进动作', '施加压力']" :key="job" type="button" :class="{ on: (shot.shot_jobs || []).includes(job) }" @click="toggleShotJob(shot, job)">{{ job }}</button></div></div><button v-if="!readOnly" class="insert" title="在此镜头后插入新镜头" @click="insertShot(scene, hi)">＋ 插入镜头</button><button v-if="!readOnly" class="remove" title="删除镜头" @click="removeShot(scene, hi)">删除镜头</button></aside>
              <section class="shot-narrative"><div v-if="shotIssues(si, hi).length" class="shot-issues"><div v-for="(issue, ii) in shotIssues(si, hi)" :key="ii" :class="['shot-issue', issue.severity]"><b>{{ issue.severity?.toUpperCase?.() || '建议' }}</b><span>{{ issue.message }} <strong v-if="issue.blocking_stage === 'confirm'">（确认前修复）</strong></span><button v-if="issue.actionable && !readOnly" @click="applySuggestion(issue)">{{ issue.action_label || '应用建议' }}</button><small v-else>人工复核</small></div></div><label class="shot-title-label">镜头标题<input v-model="shot.title" :disabled="readOnly" class="shot-title"></label><div class="span-2 cast-row">
  <div class="cast-block">
    <small>出场角色（来自演员表，生成时注入角色一致性）</small>
    <div class="cast-picker">
      <button v-for="character in item.content.characters" :key="character.stable_key" type="button" :disabled="readOnly" :class="{ on: (shot.character_names || []).includes(character.name) }" @click="toggleName(shot.character_names, shot, 'character_names', character.name)">{{ character.name || character.stable_key }}</button>
      <em v-if="!item.content.characters.length">本集演员表为空</em>
      <em v-else-if="!(shot.character_names || []).length">未标注出场角色</em>
    </div>
  </div>
  <div class="cast-block">
    <small>出场道具（来自道具档案）</small>
    <div class="cast-picker">
      <button v-for="prop in item.content.props" :key="prop.stable_key" type="button" :disabled="readOnly" :class="{ on: (shot.prop_names || []).includes(prop.name) }" @click="toggleName(shot.prop_names, shot, 'prop_names', prop.name)">{{ prop.name || prop.stable_key }}</button>
      <em v-if="!item.content.props.length">本集无道具档案</em>
      <em v-else-if="!(shot.prop_names || []).length">未标注出场道具</em>
    </div>
  </div>
</div>
<label class="span-2">镜头任务依据<input v-model="shot.job_reason" :disabled="readOnly" placeholder="发生了什么具体变化？未分析请留空"></label><p v-if="shot.evidence" class="span-2">证据：{{ shot.evidence.level }} · {{ shot.evidence.quote }} · {{ shot.evidence.reason }} / 来源 {{ shot.source_refs?.join('、') }}</p><label class="span-2">剧本内容<textarea v-model="shot.content" :disabled="readOnly" rows="8" placeholder="该镜头的完整剧本内容（含对白、动作等全部文字）"></textarea></label>
<div class="span-2 dialogue-block">
  <header class="dialogue-head"><b>对白（从剧本内容派生）</b><span>保存后由后端重新提取；请在上方修改原文</span></header>
  <p v-if="!(shot.dialogue_lines || []).length" class="dialogue-empty">未识别到对白；空镜头允许无对白。</p>
  <p v-for="(line, di) in shot.dialogue_lines" :key="di">{{ line.speaker || '说话人待确认' }}：{{ line.text }}</p>
  <small v-if="shot.dialogue_metrics">对白与反应至少 {{ shot.dialogue_metrics.required_seconds }} 秒 / 总预算 {{ shotTotal(shot).toFixed(1) }} 秒</small>
</div>
<details v-if="shot.prompt" class="span-2"><summary>生成提示词（人工覆盖优先；留空恢复原始值）</summary>
  <label v-for="(label, key) in promptLabels" :key="key">{{ label }}<textarea v-model="shot.prompt.override[key]" :disabled="readOnly" :placeholder="shot.prompt.original[key]" rows="2"></textarea><small>当前有效：{{ shot.prompt.override[key] || shot.prompt.original[key] }}</small></label>
</details></section>
              <section class="frame-plan"><header class="frame-head"><div><small>KEYFRAME ADVICE</small><b>关键帧建议</b></div><span>首帧=视频第一画面的生图提示词 · 尾帧=视频最后画面的生图提示词</span></header><div class="frame-strategy"><span>策略</span><button v-for="[v, label] in frameStrategies" :key="v" type="button" :disabled="readOnly" :class="{ active: shot.keyframe_plan?.strategy === v }" @click="setStrategy(shot, v)">{{ label }}</button></div><label v-if="showFirstFrame(shot)" class="frame-field"><span>首帧提示词（视频第一画面的生图提示词）</span><textarea v-model="shot.keyframe_plan.first_frame_prompt" :disabled="readOnly" rows="4"></textarea></label><label v-if="showLastFrame(shot)" class="frame-field"><span>尾帧提示词（视频最后画面的生图提示词）</span><textarea v-model="shot.keyframe_plan.last_frame_prompt" :disabled="readOnly" rows="4"></textarea></label><div v-if="shot.keyframe_plan?.strategy === 'multi'" class="frame-keyframes"><div v-for="(kf, ki) in shot.keyframe_plan.keyframes" :key="ki" class="frame-keyframe"><div class="kf-head"><input v-model="kf.label" :disabled="readOnly"><button v-if="!readOnly" type="button" class="kf-remove" title="删除关键帧" @click="removeKeyframe(shot, ki)">×</button></div><textarea v-model="kf.prompt" :disabled="readOnly" rows="3"></textarea></div><button v-if="!readOnly" type="button" class="add-keyframe" @click="addKeyframe(shot)">＋ 添加关键帧</button></div></section>
            </article>
            <button v-if="!readOnly" class="add-shot" @click="addShot(scene)">＋ 添加镜头</button>
          </div>
        </article>
      </main>
    </div>
    <div v-if="splitPreview" class="split-overlay" role="dialog" aria-modal="true" aria-label="拆镜预览">
      <section class="split-dialog"><h2>拆镜预览</h2><p>总预算：{{ splitPreview.before_duration }} → {{ splitPreview.after_duration }} 秒</p>
      <p v-for="warning in splitPreview.warnings" :key="warning">{{ warning }}</p>
      <h3>原镜头</h3><pre>{{ splitPreview.before.content }}</pre>
      <article v-for="(shot, index) in splitPreview.shots" :key="index"><h3>分段 {{ index + 1 }} · {{ shot.duration }} 秒</h3><pre>{{ shot.content }}</pre></article>
      <V2Button :disabled="applyingSplit" @click="splitPreview = null">取消</V2Button><V2Button :disabled="applyingSplit" @click="applySplit">确认应用</V2Button></section>
    </div>
    <p class="save-state">当前镜头生成总预算 {{ totalSeconds }} 秒；模型时长限制以生产工作流为准。</p>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
  </DramaProjectShell>
  <div v-else class="loading">{{ loading ? 'AI 正在整理拍摄清单…' : error || '暂无拍摄清单' }}</div>
</template>

<style scoped>
.split-overlay{position:fixed;inset:0;z-index:50;background:#0008;display:grid;place-items:center}.split-dialog{background:#fff;color:#312c26;padding:24px;border-radius:12px;max-width:850px;width:85vw;max-height:85vh;overflow:auto}.split-dialog pre{white-space:pre-wrap;background:#f7f5f0;padding:12px}

.manifest-page{width:100%;max-width:1540px;margin:0 auto;color:var(--v2-text)}
.topbar{display:grid;grid-template-columns:auto minmax(280px,1fr) auto;align-items:center;gap:18px;padding:4px 0 14px}.back{align-self:start;margin-top:7px;background:none;border:0;color:var(--v2-text-muted);cursor:pointer}.title{min-width:0}.title small,.section-title small,.shot-id small,.prompt-editor summary small{letter-spacing:.12em;color:var(--v2-primary)}.title h1{margin:3px 0 5px;font-size:28px}.title>input{padding:0;border:0;background:transparent;color:var(--v2-text-muted)}.actions{display:flex;align-items:center;justify-content:flex-end;gap:8px}.save-state{font-size:12px;color:var(--v2-text-muted)}
.summary-bar{margin-bottom:14px;padding:12px 16px;display:flex;flex-wrap:wrap;gap:20px;align-items:center;background:var(--v2-surface);border:1px solid var(--v2-border);border-radius:13px}.status{margin-left:auto;padding:5px 10px;border-radius:20px;background:rgba(234,179,8,.12);color:#d5a20d}.status.confirmed{background:rgba(34,197,94,.12);color:#32c56a}.advice{color:var(--v2-warning)}.validation{display:grid;gap:6px;margin-bottom:14px}.validation>p{margin:0 0 3px;color:var(--v2-text-muted);font-size:12px}.validation>div{display:grid;grid-template-columns:auto minmax(0,1fr) auto auto;gap:9px;align-items:center;padding:8px 11px;background:var(--v2-surface-soft);border-left:3px solid var(--v2-border);border-radius:7px;font-size:12px}.validation .p0{border-left-color:var(--v2-danger)}.validation .p1{border-left-color:var(--v2-warning)}.validation .p2{border-left-color:var(--v2-primary)}.validation code{color:var(--v2-text-subtle)}.validation button{padding:5px 9px;color:#fff;background:var(--v2-primary);border:0;border-radius:6px}.validation small{color:var(--v2-text-subtle)}
.workspace{display:grid;grid-template-columns:280px minmax(0,1fr);gap:14px;align-items:start}.analysis-panel{position:sticky;top:88px;max-height:calc(100vh - 110px);overflow:auto;padding:15px;background:var(--v2-surface);border:1px solid var(--v2-border);border-radius:15px}.analysis-panel section+section{margin-top:20px}.section-title{display:flex;align-items:baseline;justify-content:space-between}.section-title h2{margin:0 0 10px;font-size:15px}.character-card{margin-top:8px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:9px;overflow:hidden}.character-card summary{padding:10px;display:grid;grid-template-columns:auto 1fr;gap:3px 7px;cursor:pointer;list-style:none}.character-card summary::-webkit-details-marker{display:none}.character-card summary span{grid-row:1/3;color:var(--v2-primary);font-size:10px}.character-card summary b{font-size:13px}.character-card summary small{color:var(--v2-text-muted)}.character-fields{padding:0 10px 10px;display:grid;gap:7px}.character-fields label,.shot-narrative label,.prompt-grid label{display:grid;gap:4px;color:var(--v2-text-muted);font-size:11px}input,textarea,.character-fields select{box-sizing:border-box;width:100%;min-width:0;padding:8px 9px;color:var(--v2-text);background:rgba(3,12,25,.38);border:1px solid var(--v2-border);border-radius:7px;font:inherit;outline:none}input:focus,textarea:focus,.character-fields select:focus{border-color:var(--v2-primary)}textarea{resize:vertical}input:disabled,textarea:disabled,.character-fields select:disabled{opacity:.72}
.scene-list{min-width:0}.scene-card{margin-bottom:16px;background:var(--v2-surface);border:1px solid var(--v2-border);border-radius:15px;overflow:hidden}.scene-head{display:grid;grid-template-columns:88px minmax(0,1fr);gap:14px;padding:14px 16px;background:rgba(255,255,255,.015);border-bottom:1px solid var(--v2-border)}.scene-index{padding-top:24px;font-size:12px;font-weight:800;color:var(--v2-primary)}.scene-fields{min-width:0;display:grid;gap:7px}.scene-fields label,.shot-title-label,.shot-quick label{display:grid;gap:3px;color:var(--v2-text-muted);font-size:10px}.heading{font-size:16px;font-weight:700}.inline-fields{display:grid;grid-template-columns:1.2fr 1fr .65fr .65fr;gap:7px}.semantics{grid-template-columns:.65fr 1fr 1.5fr}.shots{padding:12px}.shot-row{margin-bottom:11px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:11px;overflow:hidden}.shot-bar{padding:9px 10px;display:grid;grid-template-columns:64px minmax(150px,1fr) minmax(350px,1.25fr) 28px;gap:8px;align-items:end;border-bottom:1px solid var(--v2-border)}.shot-id{display:flex;align-items:center;gap:5px;padding-bottom:1px}.shot-number{padding:5px;font-size:17px;font-weight:800;text-align:center}.shot-title{font-weight:650}.shot-quick{display:grid;grid-template-columns:repeat(4,minmax(70px,1fr));gap:6px}.duration-input{display:flex;align-items:center;gap:4px}.duration-input i{font-style:normal;color:var(--v2-text-subtle)}.remove{width:28px;height:28px;margin-bottom:1px;padding:0;color:var(--v2-text-muted);background:none;border:0;border-radius:6px;font-size:18px;cursor:pointer}.remove:hover{color:var(--v2-danger);background:rgba(239,68,68,.1)}
.shot-narrative{padding:10px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.shot-narrative .span-2,.binding-row{grid-column:1/-1}.binding-row{padding:7px 9px;display:grid;grid-template-columns:1fr 1fr 180px;gap:8px;align-items:end;color:var(--v2-text-muted);background:rgba(255,255,255,.018);border-radius:7px;font-size:11px}.binding-row label{display:grid;gap:3px}.prompt-editor{border-top:1px solid var(--v2-border)}.prompt-editor>summary{padding:10px 12px;display:flex;align-items:center;justify-content:space-between;gap:12px;cursor:pointer;list-style:none}.prompt-editor>summary::-webkit-details-marker{display:none}.prompt-editor>summary div{display:flex;align-items:center;gap:9px}.prompt-editor>summary span{color:var(--v2-text-subtle);font-size:11px}.prompt-editor[open]>summary{background:rgba(125,140,255,.05)}.prompt-grid{padding:10px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;border-top:1px solid var(--v2-border)}.prompt-grid .wide{grid-column:1/-1}.prompt-grid label small{color:var(--v2-primary)}.add-shot{width:100%;padding:10px;color:var(--v2-text-muted);background:none;border:1px dashed var(--v2-border);border-radius:8px;cursor:pointer}.error{position:fixed;right:22px;bottom:22px;z-index:20;max-width:440px;padding:12px 16px;color:#fff;background:#b91c1c;border-radius:10px;box-shadow:var(--v2-shadow)}.loading{min-height:60vh;display:grid;place-items:center}
@media(max-width:1360px){.workspace{grid-template-columns:1fr}.analysis-panel{position:static;max-height:none;display:grid;grid-template-columns:minmax(260px,.8fr) minmax(320px,1.2fr);gap:18px}.analysis-panel section+section{margin-top:0}.shot-bar{grid-template-columns:56px 1fr minmax(350px,1.2fr) 28px}.inline-fields{grid-template-columns:1fr 1fr}}
@media(max-width:980px){.topbar{grid-template-columns:1fr}.back{margin:0}.actions{justify-content:flex-start;flex-wrap:wrap}.analysis-panel{display:block}.analysis-panel section+section{margin-top:20px}.shot-bar{grid-template-columns:56px 1fr 28px}.shot-quick{grid-column:1/4}.remove{grid-column:3;grid-row:1}}
@media(max-width:700px){.summary-bar{gap:10px}.status{margin-left:0}.scene-head{grid-template-columns:1fr}.scene-index{padding:0}.inline-fields,.semantics,.shot-narrative,.prompt-grid{grid-template-columns:1fr}.shot-narrative .span-2,.binding-row,.prompt-grid .wide{grid-column:auto}.binding-row{grid-template-columns:1fr}.shot-quick{grid-template-columns:1fr 1fr}.validation>div{grid-template-columns:1fr}.validation code{display:none}}
</style>


<style scoped>
.version-switch{padding:7px 9px;color:#4b443c;background:#fff;border:1px solid #ded8ce;border-radius:7px}.version-actions{display:flex;align-items:center;gap:6px}.version-delete{width:28px;height:28px;display:grid;place-items:center;color:#a74c49;background:#fff1ef;border:1px solid #efd0cc;border-radius:7px;cursor:pointer;font-size:12px}.version-delete:hover{background:#fde5e2}.manifest-page{box-sizing:border-box;width:100%;max-width:none;margin:0;padding:22px 26px 48px;color:#29251f;background:#f7f5f0}.topbar{display:grid;grid-template-columns:minmax(280px,1fr) auto;align-items:center;gap:18px;padding:0 0 15px}.title small,.section-title small,.shot-id small,.prompt-editor summary small{color:#9b7748;letter-spacing:.12em}.title h1{margin:3px 0 5px;font-size:28px}.title>input{padding:0;color:#766e64;background:transparent;border:0}.actions{display:flex;align-items:center;justify-content:flex-end;gap:8px}.save-state{color:#82796e;font-size:12px}.summary-bar{margin-bottom:14px;padding:12px 16px;display:flex;align-items:center;gap:20px;flex-wrap:wrap;color:#554e46;background:#fff;border:1px solid #dfd8cf;border-radius:11px}.status{margin-left:auto;padding:5px 10px;color:#b07d25;background:#f7ecd9;border-radius:20px}.status.confirmed{color:#27865b;background:#e2f3e9}.blocker{color:#b84545}.validation>div{background:#fff;border-color:#d4cdc4}.validation code{color:#938a7f}.workspace{display:grid;grid-template-columns:300px minmax(0,1fr);gap:16px;align-items:start}.analysis-panel{position:sticky;top:86px;max-height:calc(100vh - 110px);overflow:auto;padding:16px;background:#fff;border:1px solid #dfd8cf;border-radius:12px}.analysis-panel section+section{margin-top:22px}.section-title h2{color:#302b25}.character-card{background:#f5f2ed;border:1px solid #e1dbd2}.character-card summary span{color:#9b7748}.character-card summary small{color:#81796f}.character-fields label,.shot-narrative label,.prompt-grid label,.shot-meta label{color:#756d63}input,textarea,.character-fields select{color:#312c26;background:#fff;border-color:#ddd6cb}input:focus,textarea:focus,.character-fields select:focus{border-color:#b28a56}input:disabled,textarea:disabled,.character-fields select:disabled{opacity:.78;color:#4f4942;background:#f8f6f2}.scene-card{margin-bottom:18px;background:#fff;border:1px solid #ddd6cb;border-radius:12px;box-shadow:0 10px 25px rgba(74,56,31,.06)}.scene-head{grid-template-columns:95px minmax(0,1fr);padding:17px 18px;background:#fbfaf7;border-bottom-color:#e3ddd4}.scene-index{color:#9b7748}.scene-fields label{color:#756d63}.shots{padding:0}.shot-row{margin:0;display:grid;grid-template-columns:150px minmax(340px,1fr) minmax(300px,390px);background:#fff;border:0;border-bottom:1px solid #ddd6cb;border-radius:0}.shot-row:last-of-type{border-bottom:0}.shot-meta{padding:22px 16px;display:grid;align-content:start;gap:10px;background:#fbfaf7;border-right:1px solid #e2dcd3}.shot-id{display:grid;grid-template-columns:auto 1fr;align-items:center;gap:7px;margin-bottom:6px}.shot-number{padding:4px;font-size:22px;font-weight:800;text-align:center}.shot-meta label{display:grid;gap:4px;font-size:10px}.duration-input i{color:#8f867b}.insert{width:100%;height:30px;margin-top:8px;color:#5f4317;background:#f2c063;border:1px solid #d9a441;border-radius:7px;font-size:11px}.remove{width:100%;height:30px;margin-top:8px;color:#a74c49;background:#fff1ef;border:1px solid #efd0cc;border-radius:7px;font-size:11px}.shot-narrative{padding:20px;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.shot-title-label{grid-column:1/-1}.shot-title{font-size:15px;font-weight:700}.binding-row{background:#f7f4ef;color:#6e665c}.prompt-editor{min-width:0;border-top:0;border-left:1px solid #e2dcd3;background:#fbfaf7}.prompt-editor>summary{padding:18px 15px;background:transparent!important}.prompt-editor>summary span{color:#8e857a}.prompt-grid{padding:0 15px 18px;display:grid;grid-template-columns:1fr;gap:9px;border-top:0}.prompt-grid .wide{grid-column:auto}.prompt-grid label small{color:#9b7748}.add-shot{margin:12px;width:calc(100% - 24px);color:#756d63;border-color:#cfc6bb}.error{background:#b44542}.loading{min-height:100vh;background:#f7f5f0;color:#4f4840}
@media(max-width:1480px){.workspace{grid-template-columns:270px minmax(0,1fr)}.shot-row{grid-template-columns:130px minmax(320px,1fr) 320px}.inline-fields{grid-template-columns:1fr 1fr}}
@media(max-width:1180px){.workspace{grid-template-columns:1fr}.analysis-panel{position:static;max-height:none;display:grid;grid-template-columns:minmax(260px,.8fr) minmax(320px,1.2fr);gap:18px}.analysis-panel section+section{margin-top:0}.shot-row{grid-template-columns:130px minmax(320px,1fr)}.prompt-editor,.frame-plan{grid-column:1/-1;border-left:0;border-top:1px solid #e2dcd3}.prompt-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:820px){.manifest-page{padding:16px 14px 40px}.topbar{grid-template-columns:1fr}.actions{justify-content:flex-start;flex-wrap:wrap}.analysis-panel{display:block}.analysis-panel section+section{margin-top:20px}.scene-head,.shot-row{grid-template-columns:1fr}.shot-meta{grid-template-columns:repeat(4,1fr);border-right:0;border-bottom:1px solid #e2dcd3}.shot-id{grid-column:1/-1}.remove{grid-column:1/-1}.inline-fields,.semantics{grid-template-columns:1fr 1fr}.prompt-grid{grid-template-columns:1fr}}
@media(max-width:560px){.summary-bar{gap:9px}.status{margin-left:0}.inline-fields,.semantics,.shot-narrative{grid-template-columns:1fr}.shot-narrative .span-2,.binding-row{grid-column:auto}.binding-row,.shot-meta{grid-template-columns:1fr}.validation>div{grid-template-columns:1fr}.validation code{display:none}}
.shot-id{position:relative}
.shot-issues{grid-column:1/-1;display:grid;gap:5px;margin-bottom:2px}
.shot-issue{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:8px;align-items:center;padding:6px 9px;font-size:11px;background:#fdf3e3;border:1px solid #ecdcc0;border-left:3px solid #d9a441;border-radius:7px}
.shot-issue.p0{border-left-color:#b84545;background:#fdecec;border-color:#f0cfcf}
.shot-issue.p2{border-left-color:#7a8fd6;background:#eef1fb;border-color:#d4dbf4}
.shot-issue b{color:#8a6d2f}
.shot-issue button{padding:3px 8px;color:#fff;background:#b28a56;border:0;border-radius:5px;font-size:11px;cursor:pointer}
.shot-issue small{color:#938a7f}
.shot-issue-badge{position:absolute;top:-7px;right:-7px;display:inline-flex;align-items:center;justify-content:center;min-width:18px;height:18px;padding:0 5px;color:#fff;background:#c26a3a;border-radius:9px;font-size:11px;font-weight:700}
.shot-jobs{display:grid;gap:3px}
.shot-jobs small{color:#756d63;font-size:10px}
.shot-jobs i{display:inline-block;padding:2px 6px;margin-right:4px;color:#5f4317;background:#f2c063;border-radius:5px;font-size:10px;font-style:normal}
.shot-jobs em{color:#938a7f;font-size:10px;font-style:normal}
.job-picker{display:flex;flex-wrap:wrap;gap:4px;margin-top:2px}
.job-picker button{padding:3px 8px;color:#756d63;background:#fff;border:1px solid #d8d1c7;border-radius:6px;font-size:10px;cursor:pointer}
.job-picker button.on{color:#5f4317;background:#f2c063;border-color:#d9a441;font-weight:600}
.cast-row{display:grid;grid-template-columns:1fr 1fr;gap:9px}
.cast-block{display:grid;gap:4px;padding:10px;background:#fbfaf7;border:1px solid #e4ded5;border-radius:9px}
.cast-block>small{color:#756d63;font-size:10px}
.cast-picker{display:flex;flex-wrap:wrap;gap:5px;align-items:center}
.cast-picker button{padding:4px 10px;color:#5b544b;background:#fff;border:1px solid #d8d1c7;border-radius:14px;font-size:11px;cursor:pointer}
.cast-picker button.on{color:#fff;background:#9b7748;border-color:#9b7748;font-weight:600}
.cast-picker button:disabled{opacity:.7;cursor:not-allowed}
.cast-picker em{color:#938a7f;font-size:10px;font-style:normal}
.frame-plan{min-width:0;padding:16px 15px;background:#fbfaf7;border-left:1px solid #e2dcd3;display:grid;gap:12px;align-content:start}
.frame-head{display:flex;align-items:center;justify-content:space-between;gap:10px}
.frame-head small{color:#9b7748;letter-spacing:.12em;font-size:10px}
.frame-head b{font-size:13px;color:#302b25}
.frame-head span{color:#8e857a;font-size:11px}
.frame-strategy{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.frame-strategy>span{color:#756d63;font-size:11px}
.frame-strategy button{padding:5px 10px;color:#756d63;background:#fff;border:1px solid #d8d1c7;border-radius:7px;font-size:11px;cursor:pointer}
.frame-strategy button.active{color:#5f4317;background:#f2c063;border-color:#d9a441;font-weight:600}
.frame-strategy button:disabled{opacity:.5;cursor:not-allowed}
.frame-field{display:grid;gap:4px}
.frame-field>span{color:#756d63;font-size:11px}
.frame-keyframes{display:grid;gap:8px;border-top:1px dashed #d8d1c7;padding-top:10px}
.frame-keyframe{display:grid;gap:4px;padding:8px;background:#fff;border:1px solid #e1dbd2;border-radius:8px}
.kf-head{display:flex;align-items:center;gap:6px}
.kf-head input{flex:1}
.kf-remove{width:22px;height:22px;padding:0;color:#a74c49;background:#fff1ef;border:1px solid #efd0cc;border-radius:6px;font-size:13px;line-height:1;cursor:pointer}
.add-keyframe{width:100%;padding:7px;color:#756d63;background:none;border:1px dashed #cfc6bb;border-radius:7px;font-size:11px;cursor:pointer}
.dialogue-block{display:grid;gap:7px;padding:11px;background:#fbfaf7;border:1px solid #e4ded5;border-radius:9px}
.dialogue-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.dialogue-head small{color:#9b7748;letter-spacing:.12em;font-size:10px}
.dialogue-head b{font-size:12px;color:#302b25}
.dialogue-head span{color:#8e857a;font-size:11px}
.dialogue-head button{margin-left:auto;padding:4px 9px;color:#5f4317;background:#fff;border:1px solid #d9c9ae;border-radius:6px;font-size:11px;cursor:pointer}
.dialogue-empty{margin:0;color:#938a7f;font-size:11px}
.dialogue-line{display:grid;grid-template-columns:110px minmax(0,1fr) 26px;gap:6px;align-items:start}
.dialogue-line .speaker{font-weight:650}
.dialogue-line textarea{min-height:34px}
.line-remove{width:26px;height:26px;padding:0;color:#a74c49;background:#fff1ef;border:1px solid #efd0cc;border-radius:6px;font-size:13px;line-height:1;cursor:pointer}
.add-line{justify-self:start;padding:6px 10px;color:#756d63;background:none;border:1px dashed #cfc6bb;border-radius:7px;font-size:11px;cursor:pointer}
</style>
