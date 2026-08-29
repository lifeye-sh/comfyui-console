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
let suppress = true
let saveTimer: ReturnType<typeof setTimeout> | null = null
const promptSegments = [
  ['base_visual', '画面提示词'], ['visual_style', '视觉风格'], ['camera_movement', '镜头运动'],
  ['composition_guide', '构图指导'], ['initial_frame', '起始帧要求'],
  ['character_consistency', '角色一致性'], ['negative_constraints', '负面约束'],
] as const
const adviceCounts = computed(() => Object.fromEntries(['p0', 'p1', 'p2'].map(level => [level, item.value?.validation_errors.filter(issue => issue.severity === level).length || 0])))
const shotCount = computed(() => item.value?.content.scenes.reduce((sum, scene: any) => sum + (scene.shots?.length || 0), 0) || 0)
const readOnly = computed(() => item.value?.status === 'confirmed')
const saveState = computed(() => saving.value ? '保存中…' : error.value ? '保存失败' : readOnly.value ? '已确认并锁定' : dirty.value ? '有未保存修改' : '已自动保存')

function blankPrompt() {
  return { original: Object.fromEntries(promptSegments.map(([key]) => [key, ''])), override: {}, effective: Object.fromEntries(promptSegments.map(([key]) => [key, ''])) }
}
function effectivePrompt(shot: any, key: string) {
  return shot.prompt?.override?.[key] || shot.prompt?.effective?.[key] || shot.prompt?.original?.[key] || ''
}
function setPromptOverride(shot: any, key: string, value: string) {
  shot.prompt ||= blankPrompt(); shot.prompt.override ||= {}; shot.prompt.effective ||= {}
  shot.prompt.override[key] = value
  shot.prompt.effective[key] = value || shot.prompt.original?.[key] || ''
}
async function load() {
  suppress = true
  try {
    const list = await shortDramaApi.scriptManifests(projectId.value, episodeId.value)
    versions.value = list
    item.value = list.find(x => x.id === Number(route.query.version)) || list[0] || null
    await nextTick(); suppress = false
  } catch (e: any) { error.value = e.response?.data?.detail || '拍摄清单加载失败' }
  finally { loading.value = false }
}
async function save() {
  if (!item.value || readOnly.value) return
  if (saveTimer) { clearTimeout(saveTimer); saveTimer = null }
  saving.value = true; error.value = ''
  try {
    const saved = await shortDramaApi.saveScriptManifest(projectId.value, episodeId.value, item.value.id, {
      lock_version: item.value.lock_version, summary: item.value.summary, content: item.value.content,
    })
    suppress = true; item.value = saved; await nextTick(); suppress = false; dirty.value = false
  } catch (e: any) { error.value = e.response?.data?.detail || '保存失败' }
  finally { saving.value = false }
}
async function confirmManifest() {
  if (!item.value || readOnly.value) return
  await save()
  if (!window.confirm('确认后将以此清单生成正式场景、镜头和角色/场景/道具，继续吗？')) return
  try {
    item.value = await shortDramaApi.confirmScriptManifest(projectId.value, episodeId.value, item.value.id)
    await router.push(`/v2/drama/projects/${projectId.value}/assets`)
  } catch (e: any) { error.value = e.response?.data?.detail || '确认失败' }
}
function addShot(scene: any) {
  scene.shots.push({
    shot_no: String(scene.shots.length + 1), title: `镜头 ${scene.shots.length + 1}`, purpose: '',
    visual_description: '', action: '', expression: '', dialogue: '', narration: '', inner_monologue: '',
    character_names: [], prop_names: [], mood: '', shot_size: '中景', camera_angle: '平视',
    camera_movement: '固定', composition: '', transition: '', duration: 3, prompt: blankPrompt(),
  })
}
function applySuggestion(issue: any) {
  if (!item.value || readOnly.value) return
  const payload = issue.action_payload || {}
  const scene = item.value.content.scenes?.[payload.scene_index]
  const shot = scene?.shots?.[payload.shot_index]
  if (!shot) return
  if (issue.action === 'set_duration') shot.duration = Number(payload.duration || 15)
  else if (issue.action === 'set_camera_angle') shot.camera_angle = payload.camera_angle || '45°斜侧平视'
  else if (issue.action === 'set_shot_job') shot.shot_jobs = [...new Set([...(shot.shot_jobs || []), payload.job || '推进动作'])]
  else if (issue.action === 'add_reaction_pause') shot.reaction_pause = Number(payload.reaction_pause || .5)
  else if (issue.action === 'split_dialogue') {
    const text = String(shot.dialogue || '')
    const points = [...text.matchAll(/[，。！？；,.!?;]/g)].map(match => (match.index || 0) + 1)
    const splitAt = points.sort((a, b) => Math.abs(a - text.length / 2) - Math.abs(b - text.length / 2))[0] || Math.ceil(text.length / 2)
    const next = JSON.parse(JSON.stringify(shot)); shot.dialogue = text.slice(0, splitAt).trim(); next.dialogue = text.slice(splitAt).trim()
    shot.duration = Math.max(.1, Number((Number(shot.duration || 3) / 2).toFixed(1))); next.duration = shot.duration
    scene.shots.splice(payload.shot_index + 1, 0, next); scene.shots.forEach((value: any, index: number) => { value.shot_no = String(index + 1); value.title ||= `镜头 ${index + 1}` })
  } else if (issue.action === 'normalize_group_count') {
    const target = Number(payload.target_count || 15)
    const all = () => item.value!.content.scenes.flatMap((value:any, sceneIndex:number) => value.shots.map((shot:any, shotIndex:number) => ({value,sceneIndex,shotIndex,shot})))
    while (all().length < target && all().length) {
      const selected = all().sort((a:any,b:any)=>Number(b.shot.duration||0)-Number(a.shot.duration||0))[0]; const next = JSON.parse(JSON.stringify(selected.shot))
      selected.shot.duration = Math.max(.1, Number((Number(selected.shot.duration||3)/2).toFixed(1))); next.duration = selected.shot.duration
      selected.value.shots.splice(selected.shotIndex + 1, 0, next)
    }
    while (all().length > target) {
      const scene = item.value.content.scenes.slice().reverse().find((value:any)=>value.shots.length > 1); if (!scene) break
      const tail = scene.shots.pop(); const previous = scene.shots[scene.shots.length - 1]
      previous.visual_description = [previous.visual_description, tail.visual_description].filter(Boolean).join('\n'); previous.dialogue = [previous.dialogue, tail.dialogue].filter(Boolean).join('\n'); previous.duration = Number(previous.duration || 0) + Number(tail.duration || 0)
    }
    item.value.content.scenes.forEach((value:any)=>value.shots.forEach((shot:any,index:number)=>{shot.shot_no=String(index+1);shot.title ||= `镜头 ${index+1}`}))
  }
  dirty.value = true; scheduleSave()
}
function scheduleSave() { if (readOnly.value) return; if (saveTimer) clearTimeout(saveTimer); saveTimer = setTimeout(() => void save(), 1000) }
function openVersion(event: Event) { const id = Number((event.target as HTMLSelectElement).value); if (id) void router.replace({ query: { ...route.query, version: id } }).then(load) }
watch(item, () => { if (suppress || readOnly.value) return; dirty.value = true; scheduleSave() }, { deep: true })
onMounted(load)
onBeforeUnmount(() => { if (saveTimer) clearTimeout(saveTimer) })
</script>

<template>
  <DramaProjectShell v-if="item" active="manifest" page-title="拍摄清单" :save-state="saveState" :save-tone="error ? 'error' : 'normal'">
    <template #actions><select class="version-switch" :value="item.id" aria-label="拍摄清单版本" @change="openVersion"><option v-for="version in versions" :key="version.id" :value="version.id">V{{ version.version }} · {{ version.status === 'confirmed' ? '已确认' : '草稿' }}</option></select></template>
  <div class="manifest-page">
    <header class="topbar">
      <div class="title"><small>SCRIPT MANIFEST · AI ANALYSIS RESULT</small><h1>拍摄清单</h1><input v-model="item.summary" :disabled="readOnly" aria-label="清单摘要"></div>
      <div class="actions"><span class="save-state">{{ saving ? '保存中…' : readOnly ? '已锁定' : '可编辑' }}</span><V2Button variant="ghost" :disabled="saving || readOnly" @click="save">保存修改</V2Button><V2Button variant="primary" :disabled="readOnly" @click="confirmManifest">{{ readOnly ? '已确认' : '确认并进入角色与场景' }}</V2Button></div>
    </header>
    <section class="summary-bar"><span>版本 V{{ item.version }}</span><b>{{ item.content.scenes.length }} 场</b><b>{{ shotCount }} 镜头</b><b>{{ item.total_duration.toFixed(1) }} 秒</b><span>{{ item.content.characters.length }} 角色</span><span>{{ item.content.locations.length }} 场景素材</span><span>{{ item.content.props.length }} 道具</span><span v-if="item.validation_errors.length" class="advice">建议 P0 {{ adviceCounts.p0 }} · P1 {{ adviceCounts.p1 }} · P2 {{ adviceCounts.p2 }}</span><span :class="['status', item.status]">{{ readOnly ? '已确认' : '待确认' }}</span></section>
    <section v-if="item.validation_errors.length" class="validation"><p>以下均为可忽略的制作建议，不限制保存、确认或生成。</p><div v-for="(issue, index) in item.validation_errors" :key="index" :class="issue.severity"><b>{{ issue.severity?.toUpperCase?.() || '建议' }}</b><span>{{ issue.message }}</span><code>{{ issue.path }}</code><button v-if="issue.actionable && !readOnly" @click="applySuggestion(issue)">{{ issue.action_label || '应用建议' }}</button><small v-else>人工复核</small></div></section>

    <div class="workspace">
      <aside class="analysis-panel">
        <section><div class="section-title"><small>STORY SUMMARY</small><h2>故事梗概</h2></div><textarea v-model="item.content.story_summary" :disabled="readOnly" rows="8" placeholder="本集故事梗概"></textarea></section>
        <section><div class="section-title"><small>CAST</small><h2>演员表 · {{ item.content.characters.length }}</h2></div>
          <details v-for="character in item.content.characters" :key="character.stable_key" class="character-card">
            <summary><span>{{ character.stable_key }}</span><b>{{ character.name || '未命名角色' }}</b><small>{{ character.identity || '待补充身份' }}</small></summary>
            <div class="character-fields"><label>角色名<input v-model="character.name" :disabled="readOnly"></label><label>身份 / 职业<input v-model="character.identity" :disabled="readOnly"></label><label>年龄外观<input v-model="character.age_appearance" :disabled="readOnly"></label><label>面部特征<textarea v-model="character.facial_features" :disabled="readOnly" rows="2"></textarea></label><label>发型<textarea v-model="character.hairstyle" :disabled="readOnly" rows="2"></textarea></label><label>基础服装<textarea v-model="character.clothing" :disabled="readOnly" rows="2"></textarea></label><label>姿态与表情<textarea v-model="character.pose_expression" :disabled="readOnly" rows="2"></textarea></label><label>技术与美术风格<textarea v-model="character.technical_style" :disabled="readOnly" rows="2"></textarea></label><label>角色生成提示词<textarea v-model="character.visual_prompt" :disabled="readOnly" rows="3"></textarea></label></div>
          </details>
        </section>
      </aside>

      <main class="scene-list">
        <article v-for="(scene, si) in item.content.scenes" :key="si" class="scene-card">
          <header class="scene-head"><div class="scene-index">SCENE {{ String(si + 1).padStart(2, '0') }}</div><div class="scene-fields"><label class="heading-label">场次标题<input v-model="scene.heading" :disabled="readOnly" class="heading"></label><div class="inline-fields"><label>主场景<input v-model="scene.location_name" :disabled="readOnly"></label><label>子空间 / 机位区域<input v-model="scene.sub_location" :disabled="readOnly"></label><label>时间<input v-model="scene.time_of_day" :disabled="readOnly"></label><label>内 / 外景<input v-model="scene.interior_exterior" :disabled="readOnly"></label></div><div class="inline-fields semantics"><label>节奏<input v-model="scene.rhythm" :disabled="readOnly"></label><label>核心情绪<input v-model="scene.emotion" :disabled="readOnly"></label><label>环境氛围<input v-model="scene.atmosphere" :disabled="readOnly"></label></div></div></header>
          <div class="shots">
            <article v-for="(shot, hi) in scene.shots" :key="hi" class="shot-row">
              <aside class="shot-meta"><div class="shot-id"><small>SHOT</small><input v-model="shot.shot_no" :disabled="readOnly" class="shot-number" aria-label="镜号"></div><label>景别<input v-model="shot.shot_size" :disabled="readOnly"></label><label>角度<input v-model="shot.camera_angle" :disabled="readOnly"></label><label>运镜<input v-model="shot.camera_movement" :disabled="readOnly"></label><label>时长（建议单组≤15秒）<div class="duration-input"><input v-model.number="shot.duration" :disabled="readOnly" type="number" min="0.1" step="0.1"><i>秒</i></div></label><button v-if="!readOnly" class="remove" title="删除镜头" @click="scene.shots.splice(hi, 1)">删除镜头</button></aside>
              <section class="shot-narrative"><label class="shot-title-label">镜头标题<input v-model="shot.title" :disabled="readOnly" class="shot-title"></label><label class="span-2">画面叙事<textarea v-model="shot.visual_description" :disabled="readOnly" rows="4"></textarea></label><label>镜头目的<textarea v-model="shot.purpose" :disabled="readOnly" rows="2"></textarea></label><label>动作任务<textarea v-model="shot.action" :disabled="readOnly" rows="2"></textarea></label><label>表情 / 情绪<textarea v-model="shot.expression" :disabled="readOnly" rows="2"></textarea></label><label>对白<textarea v-model="shot.dialogue" :disabled="readOnly" rows="2"></textarea></label><label>旁白<textarea v-model="shot.narration" :disabled="readOnly" rows="2"></textarea></label><label>内心独白<textarea v-model="shot.inner_monologue" :disabled="readOnly" rows="2"></textarea></label><div class="binding-row"><span>角色：{{ (shot.character_names || []).join('、') || '无' }}</span><span>道具：{{ (shot.prop_names || []).join('、') || '无' }}</span><label>转场<input v-model="shot.transition" :disabled="readOnly" placeholder="无"></label></div></section>
              <details class="prompt-editor" open><summary><div><small>IMAGE PROMPT</small><b>画面提示词</b></div><span>AI 原稿 / 人工覆盖</span></summary><section class="prompt-grid"><label v-for="[key, label] in promptSegments" :key="key"><span>{{ label }}</span><textarea :value="effectivePrompt(shot, key)" :disabled="readOnly" :placeholder="`填写${label}`" :rows="key === 'base_visual' ? 4 : 2" @input="setPromptOverride(shot, key, ($event.target as HTMLTextAreaElement).value)"></textarea><small v-if="shot.prompt?.override?.[key]">已人工覆盖 AI 原稿</small></label></section></details>
            </article>
            <button v-if="!readOnly" class="add-shot" @click="addShot(scene)">＋ 添加镜头</button>
          </div>
        </article>
      </main>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
  </DramaProjectShell>
  <div v-else class="loading">{{ loading ? 'AI 正在整理拍摄清单…' : error || '暂无拍摄清单' }}</div>
</template>

<style scoped>
.manifest-page{width:100%;max-width:1540px;margin:0 auto;color:var(--v2-text)}
.topbar{display:grid;grid-template-columns:auto minmax(280px,1fr) auto;align-items:center;gap:18px;padding:4px 0 14px}.back{align-self:start;margin-top:7px;background:none;border:0;color:var(--v2-text-muted);cursor:pointer}.title{min-width:0}.title small,.section-title small,.shot-id small,.prompt-editor summary small{letter-spacing:.12em;color:var(--v2-primary)}.title h1{margin:3px 0 5px;font-size:28px}.title>input{padding:0;border:0;background:transparent;color:var(--v2-text-muted)}.actions{display:flex;align-items:center;justify-content:flex-end;gap:8px}.save-state{font-size:12px;color:var(--v2-text-muted)}
.summary-bar{margin-bottom:14px;padding:12px 16px;display:flex;flex-wrap:wrap;gap:20px;align-items:center;background:var(--v2-surface);border:1px solid var(--v2-border);border-radius:13px}.status{margin-left:auto;padding:5px 10px;border-radius:20px;background:rgba(234,179,8,.12);color:#d5a20d}.status.confirmed{background:rgba(34,197,94,.12);color:#32c56a}.advice{color:var(--v2-warning)}.validation{display:grid;gap:6px;margin-bottom:14px}.validation>p{margin:0 0 3px;color:var(--v2-text-muted);font-size:12px}.validation>div{display:grid;grid-template-columns:auto minmax(0,1fr) auto auto;gap:9px;align-items:center;padding:8px 11px;background:var(--v2-surface-soft);border-left:3px solid var(--v2-border);border-radius:7px;font-size:12px}.validation .p0{border-left-color:var(--v2-danger)}.validation .p1{border-left-color:var(--v2-warning)}.validation .p2{border-left-color:var(--v2-primary)}.validation code{color:var(--v2-text-subtle)}.validation button{padding:5px 9px;color:#fff;background:var(--v2-primary);border:0;border-radius:6px}.validation small{color:var(--v2-text-subtle)}
.workspace{display:grid;grid-template-columns:280px minmax(0,1fr);gap:14px;align-items:start}.analysis-panel{position:sticky;top:88px;max-height:calc(100vh - 110px);overflow:auto;padding:15px;background:var(--v2-surface);border:1px solid var(--v2-border);border-radius:15px}.analysis-panel section+section{margin-top:20px}.section-title{display:flex;align-items:baseline;justify-content:space-between}.section-title h2{margin:0 0 10px;font-size:15px}.character-card{margin-top:8px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:9px;overflow:hidden}.character-card summary{padding:10px;display:grid;grid-template-columns:auto 1fr;gap:3px 7px;cursor:pointer;list-style:none}.character-card summary::-webkit-details-marker{display:none}.character-card summary span{grid-row:1/3;color:var(--v2-primary);font-size:10px}.character-card summary b{font-size:13px}.character-card summary small{color:var(--v2-text-muted)}.character-fields{padding:0 10px 10px;display:grid;gap:7px}.character-fields label,.shot-narrative label,.prompt-grid label{display:grid;gap:4px;color:var(--v2-text-muted);font-size:11px}input,textarea{box-sizing:border-box;width:100%;min-width:0;padding:8px 9px;color:var(--v2-text);background:rgba(3,12,25,.38);border:1px solid var(--v2-border);border-radius:7px;font:inherit;outline:none}input:focus,textarea:focus{border-color:var(--v2-primary)}textarea{resize:vertical}input:disabled,textarea:disabled{opacity:.72}
.scene-list{min-width:0}.scene-card{margin-bottom:16px;background:var(--v2-surface);border:1px solid var(--v2-border);border-radius:15px;overflow:hidden}.scene-head{display:grid;grid-template-columns:88px minmax(0,1fr);gap:14px;padding:14px 16px;background:rgba(255,255,255,.015);border-bottom:1px solid var(--v2-border)}.scene-index{padding-top:24px;font-size:12px;font-weight:800;color:var(--v2-primary)}.scene-fields{min-width:0;display:grid;gap:7px}.scene-fields label,.shot-title-label,.shot-quick label{display:grid;gap:3px;color:var(--v2-text-muted);font-size:10px}.heading{font-size:16px;font-weight:700}.inline-fields{display:grid;grid-template-columns:1.2fr 1fr .65fr .65fr;gap:7px}.semantics{grid-template-columns:.65fr 1fr 1.5fr}.shots{padding:12px}.shot-row{margin-bottom:11px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:11px;overflow:hidden}.shot-bar{padding:9px 10px;display:grid;grid-template-columns:64px minmax(150px,1fr) minmax(350px,1.25fr) 28px;gap:8px;align-items:end;border-bottom:1px solid var(--v2-border)}.shot-id{display:flex;align-items:center;gap:5px;padding-bottom:1px}.shot-number{padding:5px;font-size:17px;font-weight:800;text-align:center}.shot-title{font-weight:650}.shot-quick{display:grid;grid-template-columns:repeat(4,minmax(70px,1fr));gap:6px}.duration-input{display:flex;align-items:center;gap:4px}.duration-input i{font-style:normal;color:var(--v2-text-subtle)}.remove{width:28px;height:28px;margin-bottom:1px;padding:0;color:var(--v2-text-muted);background:none;border:0;border-radius:6px;font-size:18px;cursor:pointer}.remove:hover{color:var(--v2-danger);background:rgba(239,68,68,.1)}
.shot-narrative{padding:10px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.shot-narrative .span-2,.binding-row{grid-column:1/-1}.binding-row{padding:7px 9px;display:grid;grid-template-columns:1fr 1fr 180px;gap:8px;align-items:end;color:var(--v2-text-muted);background:rgba(255,255,255,.018);border-radius:7px;font-size:11px}.binding-row label{display:grid;gap:3px}.prompt-editor{border-top:1px solid var(--v2-border)}.prompt-editor>summary{padding:10px 12px;display:flex;align-items:center;justify-content:space-between;gap:12px;cursor:pointer;list-style:none}.prompt-editor>summary::-webkit-details-marker{display:none}.prompt-editor>summary div{display:flex;align-items:center;gap:9px}.prompt-editor>summary span{color:var(--v2-text-subtle);font-size:11px}.prompt-editor[open]>summary{background:rgba(125,140,255,.05)}.prompt-grid{padding:10px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;border-top:1px solid var(--v2-border)}.prompt-grid .wide{grid-column:1/-1}.prompt-grid label small{color:var(--v2-primary)}.add-shot{width:100%;padding:10px;color:var(--v2-text-muted);background:none;border:1px dashed var(--v2-border);border-radius:8px;cursor:pointer}.error{position:fixed;right:22px;bottom:22px;z-index:20;max-width:440px;padding:12px 16px;color:#fff;background:#b91c1c;border-radius:10px;box-shadow:var(--v2-shadow)}.loading{min-height:60vh;display:grid;place-items:center}
@media(max-width:1360px){.workspace{grid-template-columns:1fr}.analysis-panel{position:static;max-height:none;display:grid;grid-template-columns:minmax(260px,.8fr) minmax(320px,1.2fr);gap:18px}.analysis-panel section+section{margin-top:0}.shot-bar{grid-template-columns:56px 1fr minmax(350px,1.2fr) 28px}.inline-fields{grid-template-columns:1fr 1fr}}
@media(max-width:980px){.topbar{grid-template-columns:1fr}.back{margin:0}.actions{justify-content:flex-start;flex-wrap:wrap}.analysis-panel{display:block}.analysis-panel section+section{margin-top:20px}.shot-bar{grid-template-columns:56px 1fr 28px}.shot-quick{grid-column:1/4}.remove{grid-column:3;grid-row:1}}
@media(max-width:700px){.summary-bar{gap:10px}.status{margin-left:0}.scene-head{grid-template-columns:1fr}.scene-index{padding:0}.inline-fields,.semantics,.shot-narrative,.prompt-grid{grid-template-columns:1fr}.shot-narrative .span-2,.binding-row,.prompt-grid .wide{grid-column:auto}.binding-row{grid-template-columns:1fr}.shot-quick{grid-template-columns:1fr 1fr}.validation>div{grid-template-columns:1fr}.validation code{display:none}}
</style>


<style scoped>
.version-switch{padding:7px 9px;color:#4b443c;background:#fff;border:1px solid #ded8ce;border-radius:7px}.manifest-page{box-sizing:border-box;width:100%;max-width:none;margin:0;padding:22px 26px 48px;color:#29251f;background:#f7f5f0}.topbar{display:grid;grid-template-columns:minmax(280px,1fr) auto;align-items:center;gap:18px;padding:0 0 15px}.title small,.section-title small,.shot-id small,.prompt-editor summary small{color:#9b7748;letter-spacing:.12em}.title h1{margin:3px 0 5px;font-size:28px}.title>input{padding:0;color:#766e64;background:transparent;border:0}.actions{display:flex;align-items:center;justify-content:flex-end;gap:8px}.save-state{color:#82796e;font-size:12px}.summary-bar{margin-bottom:14px;padding:12px 16px;display:flex;align-items:center;gap:20px;flex-wrap:wrap;color:#554e46;background:#fff;border:1px solid #dfd8cf;border-radius:11px}.status{margin-left:auto;padding:5px 10px;color:#b07d25;background:#f7ecd9;border-radius:20px}.status.confirmed{color:#27865b;background:#e2f3e9}.blocker{color:#b84545}.validation>div{background:#fff;border-color:#d4cdc4}.validation code{color:#938a7f}.workspace{display:grid;grid-template-columns:300px minmax(0,1fr);gap:16px;align-items:start}.analysis-panel{position:sticky;top:86px;max-height:calc(100vh - 110px);overflow:auto;padding:16px;background:#fff;border:1px solid #dfd8cf;border-radius:12px}.analysis-panel section+section{margin-top:22px}.section-title h2{color:#302b25}.character-card{background:#f5f2ed;border:1px solid #e1dbd2}.character-card summary span{color:#9b7748}.character-card summary small{color:#81796f}.character-fields label,.shot-narrative label,.prompt-grid label,.shot-meta label{color:#756d63}input,textarea{color:#312c26;background:#fff;border-color:#ddd6cb}input:focus,textarea:focus{border-color:#b28a56}input:disabled,textarea:disabled{opacity:.78;color:#4f4942;background:#f8f6f2}.scene-card{margin-bottom:18px;background:#fff;border:1px solid #ddd6cb;border-radius:12px;box-shadow:0 10px 25px rgba(74,56,31,.06)}.scene-head{grid-template-columns:95px minmax(0,1fr);padding:17px 18px;background:#fbfaf7;border-bottom-color:#e3ddd4}.scene-index{color:#9b7748}.scene-fields label{color:#756d63}.shots{padding:0}.shot-row{margin:0;display:grid;grid-template-columns:150px minmax(340px,1fr) minmax(300px,390px);background:#fff;border:0;border-bottom:1px solid #ddd6cb;border-radius:0}.shot-row:last-of-type{border-bottom:0}.shot-meta{padding:22px 16px;display:grid;align-content:start;gap:10px;background:#fbfaf7;border-right:1px solid #e2dcd3}.shot-id{display:grid;grid-template-columns:auto 1fr;align-items:center;gap:7px;margin-bottom:6px}.shot-number{padding:4px;font-size:22px;font-weight:800;text-align:center}.shot-meta label{display:grid;gap:4px;font-size:10px}.duration-input i{color:#8f867b}.remove{width:100%;height:30px;margin-top:8px;color:#a74c49;background:#fff1ef;border:1px solid #efd0cc;border-radius:7px;font-size:11px}.shot-narrative{padding:20px;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.shot-title-label{grid-column:1/-1}.shot-title{font-size:15px;font-weight:700}.binding-row{background:#f7f4ef;color:#6e665c}.prompt-editor{min-width:0;border-top:0;border-left:1px solid #e2dcd3;background:#fbfaf7}.prompt-editor>summary{padding:18px 15px;background:transparent!important}.prompt-editor>summary span{color:#8e857a}.prompt-grid{padding:0 15px 18px;display:grid;grid-template-columns:1fr;gap:9px;border-top:0}.prompt-grid .wide{grid-column:auto}.prompt-grid label small{color:#9b7748}.add-shot{margin:12px;width:calc(100% - 24px);color:#756d63;border-color:#cfc6bb}.error{background:#b44542}.loading{min-height:100vh;background:#f7f5f0;color:#4f4840}
@media(max-width:1480px){.workspace{grid-template-columns:270px minmax(0,1fr)}.shot-row{grid-template-columns:130px minmax(320px,1fr) 320px}.inline-fields{grid-template-columns:1fr 1fr}}
@media(max-width:1180px){.workspace{grid-template-columns:1fr}.analysis-panel{position:static;max-height:none;display:grid;grid-template-columns:minmax(260px,.8fr) minmax(320px,1.2fr);gap:18px}.analysis-panel section+section{margin-top:0}.shot-row{grid-template-columns:130px minmax(320px,1fr)}.prompt-editor{grid-column:1/-1;border-left:0;border-top:1px solid #e2dcd3}.prompt-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:820px){.manifest-page{padding:16px 14px 40px}.topbar{grid-template-columns:1fr}.actions{justify-content:flex-start;flex-wrap:wrap}.analysis-panel{display:block}.analysis-panel section+section{margin-top:20px}.scene-head,.shot-row{grid-template-columns:1fr}.shot-meta{grid-template-columns:repeat(4,1fr);border-right:0;border-bottom:1px solid #e2dcd3}.shot-id{grid-column:1/-1}.remove{grid-column:1/-1}.inline-fields,.semantics{grid-template-columns:1fr 1fr}.prompt-grid{grid-template-columns:1fr}}
@media(max-width:560px){.summary-bar{gap:9px}.status{margin-left:0}.inline-fields,.semantics,.shot-narrative{grid-template-columns:1fr}.shot-narrative .span-2,.binding-row{grid-column:auto}.binding-row,.shot-meta{grid-template-columns:1fr}.validation>div{grid-template-columns:1fr}.validation code{display:none}}
</style>
