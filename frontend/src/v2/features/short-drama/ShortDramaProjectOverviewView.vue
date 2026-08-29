<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { shortDramaApi, type DramaEpisode, type PhaseOneCasting, type Screenplay, type ScriptManifest, type ShortDramaBrief, type ShortDramaOverview } from '@/api/modules'
import { isV3DirectorEnabled } from '@/v2/app/featureFlags'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'

const route = useRoute(); const router = useRouter()
const projectId = computed(() => Number(route.params.id))
const data = ref<ShortDramaOverview | null>(null)
const brief = ref<ShortDramaBrief | null>(null)
const screenplay = ref<Screenplay | null>(null)
const casting = ref<PhaseOneCasting>({ characters: [], locations: [], props: [], asset_versions: [] })
const manifests = ref<Record<number, ScriptManifest[]>>({})
const loading = ref(true); const saving = ref(false); const creatingEpisode = ref(false)
const deletingEpisodeId = ref<number | null>(null); const error = ref(''); const saved = ref(''); const dirty = ref(false)
let suppressWatch = true; let editRevision = 0; let saveTimer: ReturnType<typeof setTimeout> | null = null

const episodes = computed(() => screenplay.value?.episodes ?? [])
const firstEpisode = computed(() => episodes.value[0] ?? null)
const requiredChecks = computed(() => [
  { label: '剧集', done: episodes.value.length > 0 },
  { label: '集数', done: Boolean(brief.value?.episode_count) },
  { label: '角色', done: casting.value.characters.length > 0 },
  { label: '场景', done: casting.value.locations.length > 0 },
  { label: '道具', done: casting.value.props.length > 0 },
])
const completedChecks = computed(() => requiredChecks.value.filter((item) => item.done).length)
const completionPercent = computed(() => Math.round((completedChecks.value / requiredChecks.value.length) * 100))
const hasWorldview = computed(() => Boolean((data.value?.project.settings as Record<string, unknown> | undefined)?.worldview))
const firstManifest = computed(() => firstEpisode.value ? manifests.value[firstEpisode.value.id]?.[0] ?? null : null)
const recommended = computed(() => {
  if (!firstEpisode.value) return { title: '先创建第 1 集', detail: '建立剧集后即可进入剧本策划。', action: '创建第 1 集', type: 'create' }
  if (firstManifest.value) return { title: `继续「第 ${firstEpisode.value.number} 集」拍摄清单`, detail: '分镜脚本已经生成，可以继续核对场景、角色、道具和镜头。', action: '查看拍摄清单', type: 'manifest' }
  return { title: `先开始「第 ${firstEpisode.value.number} 集」剧本策划与分镜`, detail: '完成剧本后生成拍摄清单，再进入角色与场景制作。', action: '进入剧本策划', type: 'script' }
})

function formatDate(value: string) { return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) }
async function load() {
  loading.value = true; error.value = ''; suppressWatch = true
  try {
    const [overview, script, cast] = await Promise.all([
      shortDramaApi.overview(projectId.value), shortDramaApi.screenplay(projectId.value),
      shortDramaApi.phaseOneCasting(projectId.value).catch(() => ({ characters: [], locations: [], props: [], asset_versions: [] } as PhaseOneCasting)),
    ])
    data.value = overview; brief.value = { ...overview.brief }; screenplay.value = script; casting.value = cast
    const entries = await Promise.all(script.episodes.map(async (episode) => [episode.id, await shortDramaApi.scriptManifests(projectId.value, episode.id).catch(() => [])] as const))
    manifests.value = Object.fromEntries(entries); await nextTick(); dirty.value = false
  } catch (event: any) { error.value = event.response?.data?.message || '项目加载失败' }
  finally { suppressWatch = false; loading.value = false }
}
async function saveBrief() {
  if (!brief.value || saving.value) return
  if (saveTimer) { clearTimeout(saveTimer); saveTimer = null }
  const savedRevision = editRevision; saving.value = true; error.value = ''; saved.value = '保存中…'
  try {
    const { id, owner_id, project_id, created_at, updated_at, ...payload } = brief.value
    const result = await shortDramaApi.saveBrief(projectId.value, payload)
    suppressWatch = true; brief.value.lock_version = result.lock_version; brief.value.updated_at = result.updated_at
    if (data.value) data.value.brief = { ...brief.value }
    await nextTick(); suppressWatch = false
    if (editRevision === savedRevision) { dirty.value = false; saved.value = '已自动保存'; window.setTimeout(() => { if (!dirty.value) saved.value = '' }, 1800) }
  } catch (event: any) { saved.value = ''; error.value = event.response?.status === 409 ? '内容已在其他页面更新，请刷新后重试' : event.response?.data?.message || '保存失败' }
  finally { saving.value = false; if (dirty.value && editRevision > savedRevision) scheduleSave() }
}
function scheduleSave() { if (saveTimer) clearTimeout(saveTimer); saveTimer = setTimeout(() => void saveBrief(), 1200) }
async function createEpisode() {
  if (creatingEpisode.value || !brief.value) return
  creatingEpisode.value = true; error.value = ''
  try {
    const number = episodes.value.length + 1
    const created = await shortDramaApi.createEpisode(projectId.value, { title: `第 ${number} 集`, target_duration: brief.value.episode_duration || 60 })
    await load(); await router.push(`/v2/drama/projects/${projectId.value}/episodes/${created.id}/script`)
  } catch (event: any) { error.value = event.response?.data?.message || '新建剧集失败' }
  finally { creatingEpisode.value = false }
}
async function deleteEpisode(episode: DramaEpisode) {
  if (episodes.value.length <= 1 || deletingEpisodeId.value) return
  if (!window.confirm(`确定删除「第 ${episode.number} 集 ${episode.title}」吗？其场景和剧本内容也会被删除。`)) return
  deletingEpisodeId.value = episode.id
  try { await shortDramaApi.deleteEpisode(projectId.value, episode.id); await load() }
  catch (event: any) { error.value = event.response?.data?.message || '删除剧集失败' }
  finally { deletingEpisodeId.value = null }
}
function openRecommended() {
  if (recommended.value.type === 'create') return void createEpisode()
  if (!firstEpisode.value) return
  const destination = recommended.value.type === 'manifest' ? 'manifest' : 'script'
  void router.push(`/v2/drama/projects/${projectId.value}/episodes/${firstEpisode.value.id}/${destination}`)
}
function openEpisode(episode: DramaEpisode) { void router.push(`/v2/drama/projects/${projectId.value}/episodes/${episode.id}/${manifests.value[episode.id]?.length ? 'manifest' : 'script'}`) }
function exportProject() {
  if (!data.value || !screenplay.value) return
  const payload = { exported_at: new Date().toISOString(), overview: data.value, screenplay: screenplay.value, casting: casting.value, manifests: manifests.value }
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }))
  const link = document.createElement('a'); link.href = url; link.download = `${data.value.project.name || '漫剧项目'}-项目备份.json`; link.click(); URL.revokeObjectURL(url)
}
function beforeUnload(event: BeforeUnloadEvent) { if (!dirty.value) return; event.preventDefault(); event.returnValue = '' }
watch(brief, () => { if (suppressWatch || !brief.value) return; editRevision++; dirty.value = true; saved.value = '有未保存修改'; scheduleSave() }, { deep: true })
onBeforeRouteLeave(() => dirty.value ? window.confirm('创作简报仍在保存或保存失败，确定离开吗？') : true)
onMounted(() => { window.addEventListener('beforeunload', beforeUnload); void load() })
onBeforeUnmount(() => { window.removeEventListener('beforeunload', beforeUnload); if (saveTimer) clearTimeout(saveTimer) })
</script>

<template>
  <div class="v2-page overview-page">
    <div v-if="loading" class="loading">正在加载项目总览…</div>
    <div v-else-if="error && !data" class="loading error"><strong>{{ error }}</strong><V2Button variant="ghost" @click="router.push('/v2/drama/projects')">返回项目库</V2Button></div>
    <template v-else-if="data && brief && screenplay">
      <button class="back" @click="router.push('/v2/drama/projects')">← 返回项目库</button>
      <p v-if="error" class="error-banner">{{ error }}</p>
      <section class="hero-grid">
        <article class="summary-card panel-card">
          <div class="status-row"><StatusBadge :tone="completionPercent === 100 ? 'success' : 'warning'">{{ completionPercent === 100 ? '已完善' : '完善中' }}</StatusBadge><span class="meta-chip">项目完整度 {{ completionPercent }}%</span><span class="meta-chip">已完成 {{ completedChecks }}/5</span></div>
          <div class="project-title"><div><p class="eyebrow">PROJECT OVERVIEW</p><h1>{{ data.project.name }}</h1><p class="created">创建于 {{ formatDate(data.project.created_at) }}</p></div><span class="ratio">{{ brief.aspect_ratio }}</span></div>
          <p class="synopsis">{{ data.project.synopsis || '还没有项目简介，可在下方项目设置中补充创作信息。' }}</p>
          <div class="progress-box"><div class="progress-head"><strong>制作准备度</strong><span>{{ completionPercent }}%</span></div><div class="progress-track"><i :style="{ width: `${completionPercent}%` }" /></div><div class="check-list"><span v-for="item in requiredChecks" :key="item.label" :class="{ done: item.done }"><i>{{ item.done ? '✓' : '·' }}</i>{{ item.label }}</span><span :class="{ done: hasWorldview }"><i>{{ hasWorldview ? '✓' : '·' }}</i>世界观 <small>可选</small></span></div></div>
          <div class="summary-actions"><V2Button variant="ghost" @click="router.push(`/v2/drama/projects/${projectId}/import`)">⇧ 导入整篇小说</V2Button><V2Button variant="ghost" @click="exportProject">⇩ 导出整项目</V2Button></div>
        </article>
        <article class="next-card panel-card">
          <div><p class="eyebrow">✦ 推荐下一步</p><span class="step-no">01</span></div>
          <div class="next-copy"><h2>{{ recommended.title }}</h2><p>{{ recommended.detail }}</p><ul><li>两种创作模式：小说生成分镜 / 已有分镜生成分镜</li><li>AI 分析后形成可检查、可修改的拍摄清单</li><li>拍摄清单确认后进入角色、场景与道具制作</li></ul></div>
          <V2Button variant="primary" :disabled="creatingEpisode" @click="openRecommended">{{ creatingEpisode ? '创建中…' : recommended.action }} →</V2Button>
        </article>
      </section>

      <section class="section-block">
        <header class="section-head"><div><p class="eyebrow">PROJECT MATERIALS</p><h2>项目素材</h2></div><p>角色、场景和道具统一进入项目素材库管理</p></header>
        <div class="material-grid">
          <button class="material-card" @click="router.push(`/v2/drama/projects/${projectId}/assets`)"><i>♙</i><div><strong>角色</strong><span>{{ casting.characters.length ? `${casting.characters.length} 个角色` : '尚未创建' }}</span></div><b>管理 →</b></button>
          <button class="material-card" @click="router.push(`/v2/drama/projects/${projectId}/assets`)"><i>⌂</i><div><strong>场景</strong><span>{{ casting.locations.length ? `${casting.locations.length} 个场景` : '尚未创建' }}</span></div><b>管理 →</b></button>
          <button class="material-card" @click="router.push(`/v2/drama/projects/${projectId}/assets`)"><i>◇</i><div><strong>道具</strong><span>{{ casting.props.length ? `${casting.props.length} 个道具` : '尚未创建' }}</span></div><b>管理 →</b></button>
          <button class="material-card" @click="router.push(`/v2/drama/projects/${projectId}/world`)"><i>◎</i><div><strong>世界观</strong><span>{{ hasWorldview ? '已设置' : '未设置（可选）' }}</span></div><b>设置 →</b></button>
        </div>
      </section>

      <section class="section-block">
        <header class="section-head"><div><p class="eyebrow">EPISODES</p><h2>剧集管理</h2></div><p>共 {{ episodes.length }} 集 · 计划 {{ brief.episode_count }} 集</p></header>
        <div class="episode-grid">
          <article v-for="episode in episodes" :key="episode.id" class="episode-card" @click="openEpisode(episode)">
            <div class="episode-no"><small>EPISODE</small><strong>{{ String(episode.number).padStart(2, '0') }}</strong></div>
            <div class="episode-copy"><div><h3>{{ episode.title || `第 ${episode.number} 集` }}</h3><StatusBadge :tone="manifests[episode.id]?.length ? 'success' : 'neutral'">{{ manifests[episode.id]?.length ? '已有拍摄清单' : '剧本策划中' }}</StatusBadge></div><p>{{ episode.synopsis || '点击进入本集剧本策划，补充故事内容并生成拍摄清单。' }}</p><span>{{ episode.target_duration }} 秒 · {{ episode.scenes.length }} 个场景</span></div>
            <button v-if="episodes.length > 1" class="delete-episode" :disabled="deletingEpisodeId === episode.id" title="删除本集" @click.stop="deleteEpisode(episode)">×</button>
          </article>
          <button class="add-episode" :disabled="creatingEpisode" @click="createEpisode"><i>＋</i><strong>{{ creatingEpisode ? '创建中…' : '添加新集' }}</strong><span>自动按顺序创建下一集</span></button>
        </div>
      </section>

      <details class="secondary-panel">
        <summary><span><b>项目设置</b><small>创作简报、生成约束与高级工作台</small></span><i>⌄</i></summary>
        <div class="secondary-content">
          <div class="secondary-actions"><span v-if="saved" class="saved" :class="{ pending: dirty }">{{ saved }}</span><V2Button variant="ghost" @click="router.push(`/v2/drama/projects/${projectId}/screenplay`)">剧本工作台</V2Button><V2Button variant="ghost" @click="router.push(`/v2/drama/projects/${projectId}/storyboard`)">分镜工作台</V2Button><V2Button variant="ghost" @click="router.push(`/v2/drama/projects/${projectId}/production`)">镜头生产</V2Button><V2Button v-if="isV3DirectorEnabled()" variant="ghost" @click="router.push(`/v2/drama/projects/${projectId}/director`)">导演前期（实验）</V2Button><V2Button variant="primary" :disabled="saving || !dirty" @click="saveBrief">{{ saving ? '保存中…' : '保存设置' }}</V2Button></div>
          <div class="brief-form"><label><span>题材类型</span><input v-model="brief.genre"></label><label><span>目标受众</span><input v-model="brief.audience"></label><label><span>内容基调</span><input v-model="brief.tone"></label><label><span>目标平台</span><input v-model="brief.platform"></label><label><span>画面比例</span><select v-model="brief.aspect_ratio"><option>9:16</option><option>16:9</option><option>1:1</option><option>4:3</option></select></label><label><span>预计集数</span><input v-model.number="brief.episode_count" type="number" min="1" max="999"></label><label><span>单集时长（秒）</span><input v-model.number="brief.episode_duration" type="number" min="1" max="7200"></label><label><span>质量档位</span><select v-model="brief.quality_tier"><option value="draft">草稿</option><option value="standard">标准</option><option value="final">成片</option></select></label><label class="wide"><span>视觉风格</span><textarea v-model="brief.visual_style" rows="4" placeholder="画风、色彩、镜头语言和需要避免的特征"></textarea></label></div>
        </div>
      </details>
    </template>
  </div>
</template>

<style scoped>
.overview-page{max-width:1440px;margin:0 auto;padding-bottom:48px}.loading{min-height:60vh;display:flex;align-items:center;justify-content:center;gap:12px;color:var(--v2-text-muted)}.loading.error{flex-direction:column;color:var(--v2-danger)}.back{margin:0 0 18px;padding:0;color:var(--v2-text-muted);background:none;border:0;cursor:pointer}.back:hover{color:var(--v2-text)}.error-banner{margin:0 0 16px;padding:11px 14px;color:var(--v2-danger);background:rgba(255,127,145,.08);border:1px solid rgba(255,127,145,.18);border-radius:10px}.hero-grid{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(360px,.7fr);gap:18px}.panel-card,.secondary-panel{background:var(--v2-surface);border:1px solid var(--v2-border);border-radius:20px;box-shadow:0 18px 44px rgba(0,0,0,.1)}.summary-card,.next-card{min-height:410px;padding:30px}.status-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.meta-chip{padding:5px 10px;color:var(--v2-text-muted);background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:999px;font-size:12px}.project-title{margin-top:34px;display:flex;align-items:flex-start;justify-content:space-between;gap:20px}.eyebrow{margin:0 0 8px;color:var(--v2-text-subtle);font-size:11px;font-weight:700;letter-spacing:.14em}.project-title h1{margin:0;font-size:36px;line-height:1.15;letter-spacing:-.03em}.created{margin:8px 0 0;color:var(--v2-text-subtle);font-size:12px}.ratio{padding:7px 10px;color:var(--v2-text-muted);border:1px solid var(--v2-border);border-radius:8px;font-size:12px}.synopsis{max-width:720px;min-height:44px;margin:22px 0;color:var(--v2-text-muted);line-height:1.7}.progress-box{padding:18px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:14px}.progress-head{display:flex;justify-content:space-between;gap:12px;font-size:13px}.progress-head span{color:var(--v2-text-muted)}.progress-track{height:6px;margin:12px 0 14px;overflow:hidden;background:rgba(127,127,127,.16);border-radius:99px}.progress-track i{display:block;height:100%;background:linear-gradient(90deg,var(--v2-primary-strong),var(--v2-info));border-radius:inherit;transition:width .3s ease}.check-list{display:flex;gap:8px;flex-wrap:wrap}.check-list>span{display:inline-flex;align-items:center;gap:5px;color:var(--v2-text-subtle);font-size:12px}.check-list>span.done{color:var(--v2-success)}.check-list i{width:17px;height:17px;display:grid;place-items:center;background:rgba(127,127,127,.08);border:1px solid currentColor;border-radius:50%;font-style:normal;font-size:10px}.check-list small{font-size:9px}.summary-actions{margin-top:18px;display:flex;gap:10px}.next-card{display:flex;flex-direction:column;justify-content:space-between;background:linear-gradient(145deg,var(--v2-surface),var(--v2-surface-soft))}.next-card>div:first-child{display:flex;align-items:flex-start;justify-content:space-between}.step-no{color:var(--v2-text-subtle);font:700 48px/1 ui-monospace,monospace;opacity:.28}.next-copy h2{max-width:430px;margin:0;font-size:27px;line-height:1.35}.next-copy>p{margin:14px 0 18px;color:var(--v2-text-muted);line-height:1.6}.next-copy ul{margin:0;padding-left:18px;color:var(--v2-text-subtle);font-size:13px;line-height:1.9}.next-card>.v2-button{width:100%;min-height:50px}.section-block{margin-top:34px}.section-head{margin-bottom:15px;display:flex;align-items:flex-end;justify-content:space-between;gap:18px}.section-head h2{margin:0;font-size:22px}.section-head>p{margin:0;color:var(--v2-text-muted);font-size:13px}.material-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px}.material-card{min-height:116px;padding:18px;display:grid;grid-template-columns:42px 1fr auto;align-items:center;gap:12px;text-align:left;color:var(--v2-text);background:var(--v2-surface);border:1px solid var(--v2-border);border-radius:15px;cursor:pointer;transition:transform .15s ease,border-color .15s ease}.material-card:hover{transform:translateY(-2px);border-color:var(--v2-border-strong)}.material-card>i{width:42px;height:42px;display:grid;place-items:center;color:var(--v2-info);background:var(--v2-surface-soft);border-radius:12px;font-style:normal;font-size:20px}.material-card div{display:grid;gap:6px}.material-card span{color:var(--v2-text-muted);font-size:12px}.material-card b{color:var(--v2-text-subtle);font-size:11px}.episode-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.episode-card{position:relative;min-height:150px;padding:20px;display:grid;grid-template-columns:90px 1fr;gap:20px;background:var(--v2-surface);border:1px solid var(--v2-border);border-radius:16px;cursor:pointer;transition:transform .15s ease,border-color .15s ease}.episode-card:hover{transform:translateY(-2px);border-color:var(--v2-border-strong)}.episode-no{padding-right:18px;display:grid;align-content:center;border-right:1px solid var(--v2-border)}.episode-no small{color:var(--v2-text-subtle);font-size:9px;letter-spacing:.12em}.episode-no strong{font:700 38px/1.15 ui-monospace,monospace}.episode-copy>div{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.episode-copy h3{margin:0;font-size:17px}.episode-copy p{margin:14px 0;color:var(--v2-text-muted);font-size:13px;line-height:1.5}.episode-copy>span{color:var(--v2-text-subtle);font-size:11px}.delete-episode{position:absolute;top:12px;right:12px;width:28px;height:28px;color:var(--v2-text-subtle);background:transparent;border:0;border-radius:50%;cursor:pointer;font-size:18px}.delete-episode:hover{color:var(--v2-danger);background:rgba(255,127,145,.1)}.add-episode{min-height:150px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:7px;color:var(--v2-text-muted);background:transparent;border:1px dashed var(--v2-border-strong);border-radius:16px;cursor:pointer}.add-episode:hover{color:var(--v2-text);background:var(--v2-surface-soft)}.add-episode i{font-style:normal;font-size:26px}.add-episode span{font-size:11px}.secondary-panel{margin-top:34px;overflow:hidden}.secondary-panel summary{padding:20px 24px;display:flex;align-items:center;justify-content:space-between;cursor:pointer;list-style:none}.secondary-panel summary::-webkit-details-marker{display:none}.secondary-panel summary span{display:grid;gap:4px}.secondary-panel summary small{color:var(--v2-text-muted);font-size:12px;font-weight:400}.secondary-panel summary>i{font-style:normal;transition:transform .2s ease}.secondary-panel[open] summary>i{transform:rotate(180deg)}.secondary-content{padding:0 24px 24px;border-top:1px solid var(--v2-border)}.secondary-actions{padding:18px 0;display:flex;justify-content:flex-end;align-items:center;gap:8px;flex-wrap:wrap}.saved{margin-right:auto;color:var(--v2-success);font-size:13px}.saved.pending{color:var(--v2-warning)}.brief-form{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.brief-form label{display:grid;gap:7px}.brief-form span{color:var(--v2-text-muted);font-size:13px}.brief-form input,.brief-form select,.brief-form textarea{width:100%;box-sizing:border-box;padding:11px 12px;color:var(--v2-text);background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:10px;outline:none}.brief-form textarea{resize:vertical}.brief-form input:focus,.brief-form select:focus,.brief-form textarea:focus{border-color:var(--v2-primary)}.brief-form .wide{grid-column:1/-1}
@media(max-width:1080px){.hero-grid{grid-template-columns:1fr}.next-card{min-height:340px}.material-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:760px){.summary-card,.next-card{padding:22px}.project-title h1{font-size:30px}.episode-grid,.brief-form{grid-template-columns:1fr}.brief-form .wide{grid-column:auto}.section-head{align-items:flex-start;flex-direction:column}.episode-card{grid-template-columns:68px 1fr}.summary-actions{flex-direction:column}.summary-actions>.v2-button{width:100%}}
@media(max-width:520px){.material-grid{grid-template-columns:1fr}.status-row{align-items:flex-start}.project-title{margin-top:24px}.summary-card,.next-card{min-height:0}.episode-card{grid-template-columns:1fr}.episode-no{padding:0 0 12px;grid-template-columns:auto 1fr;align-items:end;gap:8px;border-right:0;border-bottom:1px solid var(--v2-border)}.episode-no strong{font-size:28px}}
</style>
