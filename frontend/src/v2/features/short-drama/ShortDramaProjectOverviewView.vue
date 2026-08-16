<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { shortDramaApi, type ShortDramaBrief, type ShortDramaOverview } from '@/api/modules'
import GlassCard from '@/v2/components/GlassCard.vue'
import GlassPanel from '@/v2/components/GlassPanel.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'

const route = useRoute(); const router = useRouter()
const projectId = computed(() => Number(route.params.id))
const data = ref<ShortDramaOverview|null>(null)
const brief = ref<ShortDramaBrief|null>(null)
const loading = ref(true); const saving = ref(false); const error = ref(''); const saved = ref('')
const stages = ['创作简报','剧本','角色与世界','分镜','镜头生产']
const dirty = ref(false)
let suppressWatch = true
let editRevision = 0
let saveTimer: ReturnType<typeof setTimeout>|null = null

async function load() {
  loading.value=true;error.value=''
  try { data.value=await shortDramaApi.overview(projectId.value); brief.value={...data.value.brief}; await nextTick(); suppressWatch=false }
  catch(event:any){error.value=event.response?.data?.message||'项目加载失败'} finally{loading.value=false}
}
async function saveBrief(){
  if(!brief.value||saving.value)return
  if(saveTimer){clearTimeout(saveTimer);saveTimer=null}
  const savedRevision=editRevision;saving.value=true;error.value='';saved.value='保存中…'
  try{
    const { id, owner_id, project_id, created_at, updated_at, ...payload }=brief.value
    const result=await shortDramaApi.saveBrief(projectId.value,payload)
    suppressWatch=true;brief.value.lock_version=result.lock_version;brief.value.updated_at=result.updated_at
    if(data.value)data.value.brief={...brief.value};await nextTick();suppressWatch=false
    if(editRevision===savedRevision){dirty.value=false;saved.value='已自动保存';window.setTimeout(()=>{if(!dirty.value)saved.value=''},1800)}
  }catch(event:any){saved.value='';error.value=event.response?.status===409?'内容已在其他页面更新，请刷新后重试':event.response?.data?.message||'保存失败'}finally{saving.value=false;if(dirty.value&&editRevision>savedRevision)scheduleSave()}
}
function scheduleSave(){if(saveTimer)clearTimeout(saveTimer);saveTimer=setTimeout(()=>void saveBrief(),1200)}
function beforeUnload(event:BeforeUnloadEvent){if(!dirty.value)return;event.preventDefault();event.returnValue=''}
watch(brief,()=>{if(suppressWatch||!brief.value)return;editRevision++;dirty.value=true;saved.value='有未保存修改';scheduleSave()},{deep:true})
onBeforeRouteLeave(()=>dirty.value?window.confirm('创作简报仍在保存或保存失败，确定离开吗？'):true)
onMounted(()=>{window.addEventListener('beforeunload',beforeUnload);void load()})
onBeforeUnmount(()=>{window.removeEventListener('beforeunload',beforeUnload);if(saveTimer)clearTimeout(saveTimer)})
</script>

<template>
  <div class="v2-page overview-page">
    <div v-if="loading" class="loading">正在加载项目…</div>
    <div v-else-if="error&&!data" class="loading error"><strong>{{ error }}</strong><V2Button variant="ghost" @click="router.push('/v2/drama/projects')">返回项目列表</V2Button></div>
    <template v-else-if="data&&brief">
      <div class="import-entry"><V2Button variant="ghost" @click="router.push(`/v2/drama/projects/${projectId}/import`)">导入故事文档</V2Button><V2Button variant="ghost" @click="router.push(`/v2/drama/projects/${projectId}/screenplay`)">剧本工作台</V2Button><V2Button variant="ghost" @click="router.push(`/v2/drama/projects/${projectId}/world`)">角色与世界设定</V2Button><V2Button variant="ghost" @click="router.push(`/v2/drama/projects/${projectId}/storyboard`)">分镜工作台</V2Button><V2Button variant="primary" @click="router.push(`/v2/drama/projects/${projectId}/production`)">镜头生产</V2Button></div>
      <div class="project-head"><div><button class="back" @click="router.push('/v2/drama/projects')">← 全部项目</button><div class="title-line"><h1>{{ data.project.name }}</h1><StatusBadge tone="info">{{ data.project.status==='draft'?'草稿':data.project.status }}</StatusBadge></div><p>{{ data.project.synopsis||'暂无故事简介' }}</p></div><V2Button variant="primary" disabled>继续剧本创作</V2Button></div>
      <nav class="stage-nav"><button v-for="(item,index) in stages" :key="item" :class="{active:index===0}" :disabled="index>0"><i>{{ index+1 }}</i>{{ item }}<small v-if="index>0">后续轮次</small></button></nav>
      <div class="metric-grid"><GlassCard><span>分集</span><strong>{{ data.episode_count }}</strong><small>计划 {{ brief.episode_count }} 集</small></GlassCard><GlassCard><span>场景</span><strong>{{ data.scene_count }}</strong><small>剧本拆分后统计</small></GlassCard><GlassCard><span>镜头</span><strong>{{ data.shot_count }}</strong><small>已采用 {{ data.selected_take_count }} 个 Take</small></GlassCard><GlassCard><span>创作作业</span><strong>{{ data.active_job_count }}</strong><small>累计 {{ data.creative_job_count }} 项</small></GlassCard></div>
      <GlassPanel title="创作简报" description="后续所有 AI 助手和生成任务共同遵循的项目约束" class="brief-panel"><template #actions><span v-if="saved" class="saved" :class="{pending:dirty}">{{ saved }}</span><V2Button variant="primary" :disabled="saving||!dirty" @click="saveBrief">{{ saving?'保存中…':'立即保存' }}</V2Button></template><p v-if="error" class="error-banner">{{ error }}</p><div class="brief-form"><label><span>题材类型</span><input v-model="brief.genre"></label><label><span>目标受众</span><input v-model="brief.audience"></label><label><span>内容基调</span><input v-model="brief.tone"></label><label><span>目标平台</span><input v-model="brief.platform"></label><label><span>画面比例</span><select v-model="brief.aspect_ratio"><option>9:16</option><option>16:9</option><option>1:1</option><option>4:3</option></select></label><label><span>预计集数</span><input v-model.number="brief.episode_count" type="number" min="1" max="999"></label><label><span>单集时长（秒）</span><input v-model.number="brief.episode_duration" type="number" min="1" max="7200"></label><label><span>质量档位</span><select v-model="brief.quality_tier"><option value="draft">草稿</option><option value="standard">标准</option><option value="final">成片</option></select></label><label class="wide"><span>视觉风格</span><textarea v-model="brief.visual_style" rows="4" placeholder="画风、色彩、镜头语言和需要避免的特征"></textarea></label></div></GlassPanel>
      <div class="next-grid"><GlassCard><b>下一步：剧本创作</b><p>导入小说、剧本或从创意生成分集大纲。</p><small>第3～4轮接入</small></GlassCard><GlassCard><b>项目数据已安全保存</b><p>用户隔离、软删除和乐观锁已经启用。</p><small>更新版本 {{ data.project.lock_version }}</small></GlassCard></div>
    </template>
  </div>
</template>

<style scoped>
.loading{min-height:60vh;display:flex;align-items:center;justify-content:center;gap:12px;color:var(--v2-text-muted)}.loading.error{flex-direction:column;color:var(--v2-danger)}.project-head{display:flex;align-items:flex-end;justify-content:space-between;gap:20px}.back{padding:0;color:var(--v2-text-muted);background:none;border:0;cursor:pointer}.title-line{margin-top:14px;display:flex;align-items:center;gap:12px}.title-line h1{margin:0;font-size:34px}.project-head p{margin:8px 0 0;color:var(--v2-text-muted)}.stage-nav{margin:24px 0 16px;padding:10px;display:grid;grid-template-columns:repeat(5,1fr);gap:8px;background:var(--v2-surface);border:1px solid var(--v2-border);border-radius:16px}.stage-nav button{min-height:48px;display:flex;align-items:center;justify-content:center;gap:8px;color:var(--v2-text-subtle);background:transparent;border:0;border-radius:11px}.stage-nav button.active{color:var(--v2-text);background:var(--v2-surface-soft)}.stage-nav i{width:23px;height:23px;display:grid;place-items:center;border:1px solid var(--v2-border);border-radius:50%;font-style:normal;font-size:11px}.stage-nav small{font-size:9px}.metric-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.metric-grid .glass-card{display:grid;gap:7px}.metric-grid span,.metric-grid small{color:var(--v2-text-muted)}.metric-grid strong{font-size:29px}.brief-panel{margin-top:16px}.saved{color:var(--v2-success);font-size:13px}.saved.pending{color:var(--v2-warning)}.error-banner{padding:10px;color:var(--v2-danger);background:rgba(255,127,145,.08);border-radius:10px}.brief-form{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.brief-form label{display:grid;gap:7px}.brief-form span{color:var(--v2-text-muted);font-size:13px}.brief-form input,.brief-form select,.brief-form textarea{width:100%;padding:11px 12px;color:var(--v2-text);background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:10px;outline:none}.brief-form textarea{resize:vertical}.brief-form input:focus,.brief-form select:focus,.brief-form textarea:focus{border-color:var(--v2-primary)}.brief-form .wide{grid-column:1/-1}.next-grid{margin-top:16px;display:grid;grid-template-columns:1fr 1fr;gap:16px}.next-grid .glass-card{display:grid;gap:8px}.next-grid p{margin:0;color:var(--v2-text-muted)}.next-grid small{color:var(--v2-text-subtle)}@media(max-width:900px){.metric-grid,.brief-form{grid-template-columns:repeat(2,1fr)}.stage-nav{overflow:auto;grid-template-columns:repeat(5,150px);justify-content:flex-start}}@media(max-width:650px){.project-head{align-items:flex-start;flex-direction:column}.project-head>.v2-button{width:100%}.metric-grid,.brief-form,.next-grid{grid-template-columns:1fr}.brief-form .wide{grid-column:auto}.title-line h1{font-size:28px}}
.import-entry{display:flex;justify-content:flex-end;gap:8px;margin-bottom:-42px;position:relative;z-index:2}
</style>
