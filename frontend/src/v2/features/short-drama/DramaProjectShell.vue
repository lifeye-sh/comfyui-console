<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { shortDramaApi, type DramaEpisode, type ShortDramaProject } from '@/api/modules'
import AICallLogPanel from './AICallLogPanel.vue'

const props = defineProps<{ active: 'script' | 'manifest' | 'assets' | 'spatial' | 'director' | 'quality'; pageTitle: string; saveState?: string; saveTone?: 'normal' | 'error' }>()
const route = useRoute(); const router = useRouter()
const projectId = computed(() => Number(route.params.projectId))
const selectedEpisodeId = ref(0)
const routeEpisodeId = computed(() => Number(route.params.episodeId || route.query.episode_id) || 0)
const episodeId = computed(() => routeEpisodeId.value || selectedEpisodeId.value)
const project = ref<ShortDramaProject | null>(null)
const episodes = ref<DramaEpisode[]>([])
const hasManifest = ref(false)
const navItems = [
  { icon: '◆', label: '立项与剧本', phase: 'P0–P1', key: 'story' },
  { icon: '♙', label: '数字资产包', phase: 'P2', key: 'assets' },
  { icon: '⌖', label: '空间与分镜', phase: 'P3', key: 'spatial' },
  { icon: '▰', label: '视频制作', phase: 'P4', key: 'director' },
  { icon: '✓', label: '质检与交付', phase: 'P5', key: 'quality' },
]
const currentEpisode = computed(() => episodes.value.find((episode) => episode.id === episodeId.value) || episodes.value[0] || null)

async function loadContext() {
  try {
    const [overview, script] = await Promise.all([
      shortDramaApi.overview(projectId.value),
      shortDramaApi.screenplay(projectId.value),
    ])
    project.value = overview.project; episodes.value = script.episodes
    selectedEpisodeId.value = routeEpisodeId.value || script.episodes[0]?.id || 0
    const manifestList = episodeId.value ? await shortDramaApi.scriptManifests(projectId.value, episodeId.value).catch(() => []) : []
    hasManifest.value = manifestList.length > 0
  } catch { /* 页面主体负责显示详细错误 */ }
}
function openView(view: 'script' | 'manifest') {
  if (view === 'manifest' && !hasManifest.value) return
  void router.push(`/v2/drama/projects/${projectId.value}/episodes/${episodeId.value}/${view}`)
}
function openEpisode(event: Event) {
  const id = Number((event.target as HTMLSelectElement).value)
  if (!id) return
  selectedEpisodeId.value = id
  if (props.active === 'assets') void router.push({ path: `/v2/drama/projects/${projectId.value}/assets`, query: { episode_id: id } })
  else void router.push(`/v2/drama/projects/${projectId.value}/episodes/${id}/${props.active}`)
}
function openNav(key: string) {
  const routes: Record<string, string> = {
    story: `/v2/drama/projects/${projectId.value}/episodes/${episodeId.value}/script`,
    assets: `/v2/drama/projects/${projectId.value}/assets?episode_id=${episodeId.value}`,
    spatial: '/v2/drama/projects/'+projectId.value+'/episodes/'+episodeId.value+'/spatial',
    director: '/v2/drama/projects/'+projectId.value+'/episodes/'+episodeId.value+'/director',
    quality: '/v2/drama/projects/'+projectId.value+'/episodes/'+episodeId.value+'/quality',
  }
  void router.push(routes[key])
}
const aiLogOpen = ref(false)
onMounted(loadContext)
</script>

<template>
  <div class="project-shell" :class="{'director-shell':active==='director'}">
    <aside class="project-sidebar" aria-label="漫剧项目主菜单">
      <div class="project-brand"><span>漫</span><div><strong>漫剧制作</strong><small>COMFY DIRECTOR</small></div></div>
      <button class="back-library" @click="router.push(`/v2/drama/projects/${projectId}`)">‹ 返回项目总览</button>
      <section class="project-context"><small>当前项目</small><strong :title="project?.name">{{ project?.name || '加载中…' }}</strong><label><span>当前集数</span><select :value="episodeId" @change="openEpisode"><option v-for="episode in episodes" :key="episode.id" :value="episode.id">第 {{ episode.number }} 集{{ episode.title && episode.title !== `第 ${episode.number} 集` ? ` · ${episode.title}` : '' }}</option></select></label></section>
      <nav class="project-nav">
        <button v-for="entry in navItems" :key="entry.key" :class="{ active: entry.key === active || (entry.key === 'story' && (active === 'script' || active === 'manifest')) }" @click="openNav(entry.key)"><i>{{ entry.icon }}</i><span>{{ entry.label }}</span><small>{{ entry.phase }}</small></button>
      </nav>
      <div class="project-secondary"><button @click="aiLogOpen = true">☰ AI 调用日志</button><button @click="router.push(`/v2/drama/projects/${projectId}`)">⌂ 项目总览</button><button @click="router.push('/v2/assets')">◇ 素材库</button><button @click="router.push('/v2/tasks')">☷ 任务日志</button></div>
      <footer><button @click="router.push('/v2')">← 返回 Comfy Console</button></footer>
    </aside>

    <section class="project-stage">
      <header class="context-bar">
        <div class="mobile-context"><button @click="router.push('/v2/drama/projects')">‹</button><div><small>{{ project?.name || '漫剧项目' }} · 第 {{ currentEpisode?.number || 1 }} 集</small><strong>{{ pageTitle }}</strong></div></div>
        <div v-if="active === 'script' || active === 'manifest'" class="view-tabs" role="tablist" aria-label="剧本页面切换"><button :class="{ active: active === 'script' }" @click="openView('script')">剧本与故事</button><button :class="{ active: active === 'manifest' }" :disabled="!hasManifest" :title="hasManifest ? '查看拍摄清单' : '生成分镜脚本后可查看'" @click="openView('manifest')">拍摄清单<span v-if="hasManifest">●</span></button></div>
        <div v-else class="stage-label">{{ active === 'assets' ? 'P2 · 数字资产包' : active === 'spatial' ? 'P3 · 空间与分镜' : active === 'director' ? 'P4 · 视频制作' : 'P5 · 质检与交付' }}</div>
        <div class="context-status"><span v-if="saveState" :class="saveTone">{{ saveState }}</span><slot name="actions" /></div>
      </header>
      <main class="project-content"><slot /></main>
    </section>

    <div v-if="aiLogOpen" class="ai-log-drawer" @click.self="aiLogOpen = false">
      <div class="ai-log-drawer-body">
        <div class="ai-log-drawer-head"><b>AI 调用日志</b><button class="ai-log-close" @click="aiLogOpen = false">✕</button></div>
        <AICallLogPanel :project-id="projectId" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.project-shell{height:100vh;min-height:0;overflow:hidden;display:grid;grid-template-columns:248px minmax(0,1fr);color:#29251f;background:#f7f5f0}.project-sidebar{position:relative;height:100vh;min-height:0;overflow:hidden;display:flex;flex-direction:column;background:#f7f5f0;border-right:1px solid #ded8ce;z-index:10}.project-brand{height:70px;padding:0 22px;display:flex;align-items:center;gap:12px;border-bottom:1px solid #e5dfd6}.project-brand>span{width:36px;height:36px;display:grid;place-items:center;color:#fff;background:#201d18;border-radius:10px;font-weight:800}.project-brand div{display:grid}.project-brand strong{font-size:18px}.project-brand small{color:#8a8277;font-size:9px;letter-spacing:.16em}.back-library{margin:16px 18px 10px;height:42px;color:#514b43;background:#fff;border:1px solid #ded8ce;border-radius:9px;cursor:pointer}.project-context{padding:14px 22px 18px;display:grid;gap:7px;border-bottom:1px solid #e5dfd6}.project-context>small,.project-context label span{color:#9a9185;font-size:10px}.project-context>strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.project-context label{margin-top:8px;display:grid;gap:6px}.project-context select{width:100%;padding:9px 10px;color:#29251f;background:#211e1a;border:0;border-radius:999px;color:#fff}.project-nav{padding:14px 10px;display:grid;overflow:auto;gap:4px}.project-nav button{min-height:55px;padding:0 13px;display:grid;grid-template-columns:28px 1fr auto;align-items:center;gap:8px;color:#5e574e;background:transparent;border:1px solid transparent;border-radius:10px;cursor:pointer;text-align:left}.project-nav button:hover,.project-nav button.active{color:#201d19;background:#fff;border-color:#ded8ce;box-shadow:0 5px 15px rgba(64,50,31,.06)}.project-nav button.active{border-left:3px solid #201d19}.project-nav i{font-style:normal;font-size:17px}.project-nav small{color:#9f968b;font:9px ui-monospace,monospace}.project-secondary{margin-top:auto;padding:10px 20px;display:grid;gap:2px;border-top:1px solid #e5dfd6}.project-secondary button,.project-sidebar footer button{padding:8px 0;color:#756d63;background:none;border:0;cursor:pointer;text-align:left}.project-sidebar footer{padding:8px 20px 15px}.project-stage{min-width:0;min-height:0;height:100vh;display:grid;grid-template-rows:64px minmax(0,1fr);overflow:hidden}.context-bar{position:relative;top:auto;z-index:8;height:64px;padding:0 22px;display:grid;grid-template-columns:minmax(220px,1fr) auto minmax(220px,1fr);align-items:center;gap:18px;background:rgba(255,255,255,.92);border-bottom:1px solid #e1dbd2;backdrop-filter:blur(12px)}.mobile-context{display:flex;align-items:center;gap:10px}.mobile-context button{display:none}.mobile-context div{display:grid;gap:3px}.mobile-context small{color:#8e8579;font-size:10px}.mobile-context strong{font-size:14px}.view-tabs{padding:4px;display:flex;background:#f1eee8;border:1px solid #ded8ce;border-radius:10px}.view-tabs button{min-height:34px;padding:0 18px;color:#766e63;background:transparent;border:0;border-radius:7px;cursor:pointer}.view-tabs button.active{color:#211e1a;background:#fff;box-shadow:0 2px 8px rgba(54,43,28,.09)}.view-tabs button:disabled{opacity:.42;cursor:not-allowed}.view-tabs span{margin-left:6px;color:#39aa72;font-size:8px}.context-status{display:flex;justify-content:flex-end;align-items:center;gap:8px;color:#6e665c;font-size:12px}.context-status .error{color:#b94a46}.project-content{min-width:0;min-height:0;overflow:auto}.director-shell .project-content{overflow:auto}
.stage-label{color:#9a9185;font:10px ui-monospace,monospace;letter-spacing:.12em}
.ai-log-drawer{position:fixed;inset:0;z-index:40;display:flex;justify-content:flex-end;background:rgba(24,20,15,.35)}
.ai-log-drawer-body{width:min(560px,92vw);padding:18px;overflow:auto;background:#f7f5f0;box-shadow:-12px 0 40px rgba(40,30,15,.18)}
.ai-log-drawer-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}
.ai-log-drawer-head b{font-size:16px}
.ai-log-close{width:30px;height:30px;color:#5e574e;background:#fff;border:1px solid #ded8ce;border-radius:8px;cursor:pointer}
@media(max-width:1024px){.project-shell{grid-template-columns:72px minmax(0,1fr)}.project-brand{padding:0 18px}.project-brand div,.back-library,.project-context,.project-nav span,.project-nav small,.project-secondary button,.project-sidebar footer{display:none}.project-nav{padding:14px 8px}.project-nav button{padding:0;display:grid;grid-template-columns:1fr;place-items:center}.project-nav button.active{border-left:1px solid #ded8ce}.project-brand>span{min-width:36px}}
@media(max-width:700px){.project-shell{display:block;height:auto;min-height:100vh;overflow:visible;padding-bottom:0}.project-sidebar{display:none}.project-stage{height:auto;min-height:100vh;display:block;overflow:visible}.context-bar{height:auto;min-height:64px;padding:8px 12px;grid-template-columns:1fr auto}.mobile-context button{display:block;width:32px;height:32px;background:#f1eee8;border:0;border-radius:8px}.mobile-context small{display:none}.view-tabs{grid-column:1/-1;grid-row:2;width:100%;box-sizing:border-box}.view-tabs button{flex:1}.context-status{grid-column:2;grid-row:1}.project-content,.director-shell .project-content{min-height:calc(100vh - 112px);overflow:visible}}
</style>
