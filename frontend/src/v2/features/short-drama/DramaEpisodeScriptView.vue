<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { shortDramaApi, type AIProvider, type EpisodeScript, type ScriptManifest } from '@/api/modules'
import DramaProjectShell from './DramaProjectShell.vue'
import V2Button from '@/v2/components/V2Button.vue'

const route = useRoute(); const router = useRouter()
const projectId = computed(() => Number(route.params.projectId)); const episodeId = computed(() => Number(route.params.episodeId))
const script = ref<EpisodeScript | null>(null); const manifests = ref<ScriptManifest[]>([]); const providers = ref<AIProvider[]>([])
const providerId = ref<number | null>(null); const episodeLockVersion = ref<number | null>(null)
const loading = ref(true); const saving = ref(false); const generating = ref(false); const notice = ref(''); const error = ref('')
const rewriteInstruction = ref(''); const selectionLength = ref(0); const textarea = ref<HTMLTextAreaElement | null>(null)
let timer: ReturnType<typeof setTimeout> | null = null; let suppress = true
const latestManifest = computed(() => manifests.value[0] || null)
const manifestStale = computed(() => !!(script.value && latestManifest.value && latestManifest.value.source_script_revision !== script.value.script_revision))
const lineCount = computed(() => script.value?.text ? script.value.text.split(/\r?\n/).length : 1)
const saveState = computed(() => saving.value ? '保存中…' : error.value ? '保存失败' : notice.value || '已自动保存')
const estimatedGroups = computed(() => {
  const duration = Number(script.value?.settings.target_duration || 60)
  return { min: Math.max(1, Math.ceil(duration / 13)), max: Math.max(1, Math.ceil(duration / 12)) }
})

async function load() {
  try {
    const [value, providerList, manifestList, screenplay] = await Promise.all([
      shortDramaApi.episodeScript(projectId.value, episodeId.value), shortDramaApi.aiProviders(),
      shortDramaApi.scriptManifests(projectId.value, episodeId.value), shortDramaApi.screenplay(projectId.value),
    ])
    value.settings = { language: 'zh-CN', aspect_ratio: '16:9', target_duration: 60, visual_style: '3D 动画', quality_check: true, ...value.settings }
    script.value = value; providers.value = providerList; manifests.value = manifestList
    providerId.value = (providerList.find(x => x.is_default && x.enabled) || providerList.find(x => x.enabled))?.id || null
    episodeLockVersion.value = screenplay.episodes.find(x => x.id === episodeId.value)?.lock_version || null
    await nextTick(); suppress = false
  } catch (e: any) { error.value = e.response?.data?.detail || '剧本加载失败' }
  finally { loading.value = false }
}
function openManifest() { if (latestManifest.value) void router.push(`/v2/drama/projects/${projectId.value}/episodes/${episodeId.value}/manifest?version=${latestManifest.value.id}`) }
async function save() {
  if (!script.value || saving.value) return
  if (timer) clearTimeout(timer); saving.value = true; error.value = ''
  try {
    const saved = await shortDramaApi.saveEpisodeScript(projectId.value, episodeId.value, { lock_version: script.value.lock_version, mode: script.value.mode, text: script.value.text, settings: script.value.settings })
    suppress = true; script.value = saved; await nextTick(); suppress = false; notice.value = '已自动保存'
  } catch (e: any) { error.value = e.response?.data?.detail || '保存失败' }
  finally { suppress = false; saving.value = false }
}
async function saveTitle() {
  if (!script.value || !episodeLockVersion.value || !script.value.title.trim()) return
  try { const episode = await shortDramaApi.patchEpisode(projectId.value, episodeId.value, { lock_version: episodeLockVersion.value, title: script.value.title.trim() }); episodeLockVersion.value = episode.lock_version }
  catch (e: any) { error.value = e.response?.data?.detail || '集标题保存失败' }
}
async function generate() {
  if (!script.value?.text.trim()) return
  await save(); generating.value = true; error.value = ''; notice.value = '任务已提交，等待 AI 分析…'
  try {
    let job = await shortDramaApi.generateScriptManifest(projectId.value, episodeId.value, { idempotency_key: crypto.randomUUID(), provider_config_id: providerId.value })
    while (['queued', 'running', 'cancelling'].includes(job.status)) {
      notice.value = `AI 正在生成拍摄清单 · ${job.progress}%`; await new Promise(resolve => window.setTimeout(resolve, 1200)); job = await shortDramaApi.job(job.id)
    }
    if (job.status !== 'succeeded') throw new Error(job.error || 'AI 任务未完成')
    const manifestId = Number(job.output_payload.manifest_id); if (!manifestId) throw new Error('任务完成但没有返回拍摄清单')
    await router.push(`/v2/drama/projects/${projectId.value}/episodes/${episodeId.value}/manifest?version=${manifestId}`)
  } catch (e: any) { error.value = e.response?.data?.detail || e.message || '拍摄清单生成失败' }
  finally { generating.value = false }
}
function updateSelection() { if (textarea.value) selectionLength.value = Math.abs(textarea.value.selectionEnd - textarea.value.selectionStart) }
function aiUnavailable(action: string) { notice.value = `${action}需要接入剧本改写候选服务，当前版本暂未启用` }
function insertTemplate(kind: 'standard' | 'dialogue') {
  if (!script.value) return
  script.value.text = kind === 'standard'
    ? '### 场景一：地点 / 时间\n\n[分镜 1]\n画面：\n动作任务：\n对白：\n镜头备注：\n'
    : '### 场景一：地点 / 时间\n\n[分镜 1]\n画面：人物进入画面。\n动作任务：\n对白：角色：“……”\n镜头备注：保持对白与反应镜头连续。\n'
}
function applyScriptSuggestion(suggestion:any) {
  if (!script.value) return
  if (suggestion.action === 'insert_premise_template') script.value.text = `核心前提：当【主角】为了【目标】必须面对【阻碍】，否则【代价】。\n\n${script.value.text}`
  else if (suggestion.action === 'split_script_dialogue') {
    const lines = script.value.text.split(/\r?\n/); const index = Number(suggestion.action_payload?.line_index); const line = lines[index] || ''
    const colon = Math.max(line.indexOf('：'), line.indexOf(':')); const body = line.slice(colon + 1)
    const points = [...body.matchAll(/[，。！？；]/g)].map(match => (match.index || 0) + 1); const at = points.sort((a,b)=>Math.abs(a-body.length/2)-Math.abs(b-body.length/2))[0] || Math.ceil(body.length/2)
    if (colon >= 0) lines.splice(index, 1, `${line.slice(0,colon+1)}${body.slice(0,at).trim()}`, '动作：停顿与反应。', `${line.slice(0,colon+1)}${body.slice(at).trim()}`)
    script.value.text = lines.join('\n')
  }
}
watch(script, () => { if (suppress) return; notice.value = '有未保存修改'; if (timer) clearTimeout(timer); timer = setTimeout(() => void save(), 900) }, { deep: true })
onMounted(load); onBeforeUnmount(() => { if (timer) clearTimeout(timer) })
</script>

<template>
  <DramaProjectShell v-if="script" active="script" page-title="剧本与故事" :save-state="saveState" :save-tone="error ? 'error' : 'normal'">
    <template #actions><span class="markdown">MARKDOWN</span></template>
    <div class="script-workspace">
      <aside class="config-panel">
        <header>▣ 项目配置</header>
        <div class="config-scroll">
          <label>项目标题<input v-model="script.title" @blur="saveTitle"></label>
          <label>创作模式<div class="modes"><button :class="{ active: script.mode === 'novel' }" @click="script.mode = 'novel'">小说生成分镜</button><button :class="{ active: script.mode === 'storyboard' }" @click="script.mode = 'storyboard'">分镜生成分镜</button></div></label>
          <p class="hint">{{ script.mode === 'novel' ? '标准模式适合直接粘贴小说、章节正文或剧情大纲，由系统先理解故事，再自动拆成镜头。' : '高级模式会尽量按你已经写好的分镜逐条生成，优先保留镜头顺序、对白、任务动作和镜头备注。' }}</p>
          <label>输出语言<select v-model="script.settings.language"><option value="zh-CN">中文</option><option value="en-US">英语（美国）</option><option value="ja-JP">日语</option><option value="fr-FR">法语</option><option value="es-ES">西班牙语</option></select></label>
          <label>画面比例<div class="switches"><button :class="{ active: script.settings.aspect_ratio === '16:9' }" @click="script.settings.aspect_ratio = '16:9'">▰ 横屏</button><button :class="{ active: script.settings.aspect_ratio === '9:16' }" @click="script.settings.aspect_ratio = '9:16'">▯ 竖屏</button></div><small>后续角色、场景、分镜和视频默认沿用此比例。</small></label>
          <label>目标时长<div class="duration-grid"><button v-for="option in [{v:30,l:'30秒'},{v:60,l:'60秒'},{v:120,l:'2分钟'},{v:180,l:'3分钟'},{v:300,l:'5分钟'}]" :key="option.v" :class="{ active: script.settings.target_duration === option.v }" @click="script.settings.target_duration = option.v">{{ option.l }}</button></div><small>{{ script.settings.target_duration }} 秒 · 建议单组不超过 15 秒，预计 {{ estimatedGroups.min }}～{{ estimatedGroups.max }} 个生成组；不作为操作限制。</small></label>
          <label>分镜生成模型<select v-model="providerId"><option :value="null">请选择模型</option><option v-for="provider in providers.filter(x => x.enabled)" :key="provider.id" :value="provider.id">{{ provider.name }} · {{ provider.model }}</option></select></label>
          <label>视觉风格<select v-model="script.settings.visual_style"><option>日式动漫</option><option>2D 动画</option><option>3D 动画</option><option>赛博朋克</option><option>油画风格</option><option>真人影视</option><option>自定义</option></select></label>
          <button class="style-reverse" @click="router.push('/v2/assets')">⇧ 从素材库选择参考图并反推风格</button>
          <label class="quality"><input v-model="script.settings.quality_check" type="checkbox"><span>显示分镜质量提示与可选修复建议</span></label>
        </div>
        <footer>
          <div v-if="latestManifest" :class="['manifest-state', { stale: manifestStale }]"><b>拍摄清单 V{{ latestManifest.version }}</b><span>{{ manifestStale ? '剧本已修改，现有清单仍可查看' : '与当前剧本一致' }}</span></div>
          <span v-else>{{ notice }}</span>
          <div v-if="latestManifest" class="manifest-actions"><V2Button variant="primary" @click="openManifest">查看拍摄清单</V2Button><V2Button variant="ghost" :disabled="generating || !script.text.trim()" @click="generate">{{ generating ? 'AI 分析中…' : `重新生成 V${latestManifest.version + 1}` }}</V2Button></div>
          <V2Button v-else variant="primary" :disabled="generating || !script.text.trim() || !providerId" @click="generate">{{ generating ? 'AI 分析中…' : '✣ 生成分镜脚本' }}</V2Button>
        </footer>
      </aside>

      <main class="editor-panel">
        <div class="ai-toolbar"><b>剧本编辑器</b><button :disabled="!script.text" @click="aiUnavailable('AI 续写')">＋ AI续写</button><button :disabled="!script.text" @click="aiUnavailable('AI 改写')">↻ AI改写</button><button :disabled="!selectionLength" @click="aiUnavailable('选段改写')">✎ 选段改写</button><button disabled>↶ 撤回改写</button><span>{{ selectionLength ? `已选择 ${selectionLength} 字符` : '请先在下方选择段落' }}</span></div>
        <div class="rewrite-row"><input v-model="rewriteInstruction" placeholder="输入改写要求，例如：更紧张、增加冲突、对白更口语化…"><span>AI 修改将以候选差异呈现，不直接覆盖原文</span></div>
        <div class="editor-scroll">
          <section class="mode-card"><div><small>创作模式</small><b :class="script.mode">{{ script.mode === 'novel' ? '小说生成分镜' : '分镜生成分镜' }}</b></div><p>{{ script.mode === 'novel' ? '系统会先理解故事结构，再自动拆成适合当前时长和节奏的分镜。' : '系统会优先把你已写的镜头块转成结构化分镜，只在缺字段时做最小补全。' }}</p><div v-if="script.mode === 'novel'" class="recommend">推荐输入：章节原文、剧情大纲、角色目标、冲突节点、高潮转折。</div><div v-else class="templates"><button @click="insertTemplate('standard')"><b>模板 A · 标准分镜</b><span>场景、镜号、画面、动作、对白、镜头备注</span></button><button @click="insertTemplate('dialogue')"><b>模板 B · 对话驱动</b><span>以对白为主，系统只补齐必要镜头参数</span></button></div></section>
          <textarea ref="textarea" v-model="script.text" :placeholder="script.mode === 'novel' ? '在此输入故事大纲、章节正文或直接粘贴剧本…' : '在此粘贴你已经写好的分镜脚本，建议按模板填写场景、镜头动作、对白和镜头备注…'" spellcheck="false" @select="updateSelection" @keyup="updateSelection" @mouseup="updateSelection"></textarea>
        </div>
        <p v-if="error" class="error-toast">{{ error }}</p>
        <div class="editor-status"><span>建议单集不超过 8000 字符</span><span>{{ script.text.length }} 字符 · {{ lineCount }} 行 · 修订 {{ script.script_revision }} · {{ saveState }}</span></div>
      </main>
      <aside class="diagnostic-panel"><header><small>DIRECTOR REVIEW</small><h2>规则提示</h2><p>所有检查仅供参考，不阻止保存、分析或生成。</p></header><section><h3>五阶检查</h3><article v-for="gate in script.diagnostics?.gates || []" :key="gate.gate"><b>{{ gate.gate }} · {{ gate.name }}</b><span>{{ gate.detail }}</span></article></section><section><h3>可操作建议</h3><article v-for="(suggestion,index) in script.diagnostics?.suggestions || []" :key="index" :class="suggestion.severity"><b>{{ suggestion.severity?.toUpperCase() }} · {{ suggestion.message }}</b><button v-if="suggestion.actionable" @click="applyScriptSuggestion(suggestion)">{{ suggestion.action_label }}</button><span v-else>人工复核</span></article><p v-if="!script.diagnostics?.suggestions?.length">当前没有自动建议。</p></section></aside>
    </div>
  </DramaProjectShell>
  <div v-else class="loading">{{ loading ? '正在加载…' : error }}</div>
</template>

<style scoped>
.markdown{color:#998f82;font:10px ui-monospace,monospace;letter-spacing:.1em}.script-workspace{height:calc(100vh - 64px);display:grid;grid-template-columns:376px minmax(0,1fr);background:#f7f5f0}.config-panel{min-height:0;display:grid;grid-template-rows:58px minmax(0,1fr) auto;background:#fff;border-right:1px solid #ddd6cb}.config-panel>header{padding:0 22px;display:flex;align-items:center;border-bottom:1px solid #e5dfd7;font-weight:700}.config-scroll{padding:22px;overflow:auto}.config-panel label{margin-bottom:18px;display:grid;gap:8px;font-size:12px;font-weight:650}.config-panel label>small{color:#8a8176;font-size:10px;font-weight:400;line-height:1.5}.config-panel input,.config-panel select{box-sizing:border-box;width:100%;padding:11px 12px;color:#28241f;background:#fff;border:1px solid #ddd6cb;border-radius:8px}.modes,.switches{display:grid;grid-template-columns:1fr 1fr;gap:7px}.modes button,.switches button,.duration-grid button{min-height:42px;padding:8px;color:#4c463f;background:#fff;border:1px solid #ddd6cb;border-radius:8px;cursor:pointer}.modes button.active,.switches button.active,.duration-grid button.active{color:#33291d;background:#f2e9dc;border-color:#c3a47c}.hint{margin:-7px 0 18px;padding:10px;background:#f4f1ed;border-radius:8px;color:#6c655d;font-size:11px;line-height:1.55}.duration-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px}.style-reverse{width:100%;margin:-6px 0 18px;padding:10px;color:#6d6256;background:#faf8f4;border:1px dashed #cfc5b9;border-radius:8px;cursor:pointer}.config-panel .quality{display:flex;align-items:center;gap:8px}.quality input{width:auto}.config-panel>footer{padding:14px 22px;display:grid;gap:9px;background:#fff;border-top:1px solid #ddd6cb}.config-panel>footer>span,.manifest-state span{font-size:11px;color:#767069}.manifest-state{display:flex;justify-content:space-between;gap:8px}.manifest-state.stale span{color:#a76b2d}.manifest-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px}.editor-panel{min-width:0;min-height:0;display:grid;grid-template-rows:58px 52px minmax(0,1fr) 36px}.ai-toolbar{padding:0 22px;display:flex;align-items:center;gap:8px;background:#fff;border-bottom:1px solid #e5dfd7}.ai-toolbar b{margin-right:6px}.ai-toolbar button{min-height:34px;padding:0 12px;color:#514b43;background:#f1eee9;border:0;border-radius:7px;cursor:pointer}.ai-toolbar button:disabled{opacity:.45;cursor:not-allowed}.ai-toolbar span{margin-left:auto;color:#90877c;font-size:10px}.rewrite-row{padding:8px 22px;display:flex;align-items:center;gap:12px;background:#fff;border-bottom:1px solid #e5dfd7}.rewrite-row input{flex:1;padding:9px 12px;color:#332f2a;background:#fff;border:1px solid #ded7cd;border-radius:7px}.rewrite-row span{color:#9a9185;font-size:10px}.editor-scroll{min-height:0;overflow:auto}.mode-card{margin:36px auto 16px;width:min(960px,calc(100% - 64px));box-sizing:border-box;padding:20px;border:1px solid #ded7cd;border-radius:16px;background:rgba(255,255,255,.4)}.mode-card>div:first-child{display:flex;align-items:center;gap:10px}.mode-card small{color:#8b847b}.mode-card b.novel{color:#47a975}.mode-card b.storyboard{color:#bd8836}.mode-card p{margin:12px 0;color:#3d3832}.recommend{padding:10px 12px;color:#756d63;background:#f1eee8;border-radius:8px;font-size:12px}.templates{display:grid;grid-template-columns:1fr 1fr;gap:10px}.templates button{padding:13px;display:grid;gap:6px;text-align:left;color:#403a33;background:#fff;border:1px solid #ded7cd;border-radius:9px;cursor:pointer}.templates span{color:#81786d;font-size:11px}.editor-scroll>textarea{box-sizing:border-box;width:min(960px,calc(100% - 64px));min-height:calc(100% - 190px);margin:0 auto 30px;padding:18px;display:block;border:0;outline:0;resize:none;background:transparent;color:#332f2a;font:16px/1.85 Georgia,'Noto Serif SC',serif}.editor-status{padding:0 22px;display:flex;align-items:center;justify-content:space-between;color:#8b847b;background:#fff;border-top:1px solid #e5dfd7;font-size:10px}.error-toast{position:fixed;right:24px;bottom:48px;z-index:20;max-width:420px;padding:11px 14px;color:#a22;background:#fee;border-radius:8px}.loading{min-height:100vh;display:grid;place-items:center;background:#f7f5f0}
@media(max-width:1120px){.script-workspace{grid-template-columns:330px minmax(0,1fr)}.rewrite-row span,.ai-toolbar span{display:none}.ai-toolbar button{padding:0 8px}}
@media(max-width:800px){.script-workspace{height:auto;min-height:calc(100vh - 112px);grid-template-columns:1fr}.config-panel{max-height:none}.config-scroll{max-height:none}.editor-panel{min-height:760px}.ai-toolbar{overflow:auto}.ai-toolbar>*{white-space:nowrap}.templates{grid-template-columns:1fr}.editor-status span:first-child{display:none}}
.script-workspace{grid-template-columns:376px minmax(0,1fr) 300px}.diagnostic-panel{padding:18px;overflow:auto;background:#fff;border-left:1px solid #ddd6cb}.diagnostic-panel header small{color:#9b7748;font:9px ui-monospace,monospace}.diagnostic-panel h2{margin:4px 0}.diagnostic-panel header p,.diagnostic-panel section>p{color:#82796e;font-size:11px}.diagnostic-panel section{margin-top:20px}.diagnostic-panel h3{font-size:12px}.diagnostic-panel article{margin-bottom:7px;padding:9px;display:grid;gap:6px;background:#f7f4ef;border-left:3px solid #d7cec1;border-radius:7px;font-size:11px}.diagnostic-panel article.p0{border-color:#b84545}.diagnostic-panel article.p1{border-color:#c18a35}.diagnostic-panel article.p2{border-color:#7891a8}.diagnostic-panel article span{color:#7a7166;line-height:1.45}.diagnostic-panel article button{justify-self:start;padding:5px 8px;color:#fff;background:#9b7748;border:0;border-radius:5px}@media(max-width:1350px){.script-workspace{grid-template-columns:330px minmax(0,1fr)}.diagnostic-panel{grid-column:1/-1;max-height:320px;border-left:0;border-top:1px solid #ddd6cb}}
</style>
