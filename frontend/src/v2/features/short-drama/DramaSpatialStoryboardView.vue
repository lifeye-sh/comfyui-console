<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { shortDramaApi, type AIProvider, type DramaPipeline, type Storyboard } from '@/api/modules'
import DramaProjectShell from './DramaProjectShell.vue'
import V2Button from '@/v2/components/V2Button.vue'

const route=useRoute(), router=useRouter()
const projectId=computed(()=>Number(route.params.projectId)), episodeId=computed(()=>Number(route.params.episodeId))
const pipeline=ref<DramaPipeline|null>(null), storyboard=ref<Storyboard|null>(null), providers=ref<AIProvider[]>([])
const providerId=ref<number|null>(null), adapter=ref('seedance_2_5'), busy=ref(false), progress=ref(0), error=ref('')
const episodeBoard=computed(()=>storyboard.value?.episodes.find(x=>x.episode.id===episodeId.value))
async function load(){
  try{
    const [p,b,ps]=await Promise.all([shortDramaApi.dramaPipeline(projectId.value,episodeId.value),shortDramaApi.storyboard(projectId.value),shortDramaApi.aiProviders().catch(()=>[])])
    pipeline.value=p;storyboard.value=b;providers.value=ps;providerId.value=(ps.find(x=>x.is_default&&x.enabled)||ps.find(x=>x.enabled))?.id||null
  }catch(e:any){error.value=e.response?.data?.detail||'空间分镜加载失败'}
}
async function confirmAndGenerate(){
  if(!providerId.value){error.value='请先配置可用的 AI 服务商';return}
  busy.value=true;error.value=''
  try{
    pipeline.value=await shortDramaApi.confirmSpatialStoryboard(projectId.value,episodeId.value)
    let job=await shortDramaApi.generateVideoPrompts(projectId.value,episodeId.value,{provider_config_id:providerId.value,idempotency_key:crypto.randomUUID(),model_adapter:adapter.value})
    while(['queued','running','cancelling'].includes(job.status)){progress.value=job.progress;await new Promise(r=>setTimeout(r,1200));job=await shortDramaApi.job(job.id)}
    if(job.status!=='succeeded')throw new Error(job.error||'提示词生成失败')
    await router.push('/v2/drama/projects/'+projectId.value+'/episodes/'+episodeId.value+'/director')
  }catch(e:any){error.value=e.response?.data?.detail||e.message||'V6.5 空间分镜门禁未通过'}finally{busy.value=false}
}
onMounted(load)
</script>
<template><DramaProjectShell active="spatial" page-title="空间走位与分镜" :save-state="error||'V6.5 资产优先门禁' " :save-tone="error?'error':'normal'">
<div class="pipeline-page">
<header><div><small>P3 · SPATIAL BLOCKING & STORYBOARD</small><h1>空间走位与分镜</h1><p>先固定 3D 空间、动作轴线和 CAM1～CAM4，再确认每组 Shot 的内部时间轴。</p></div><div class="controls"><select v-model="adapter"><option value="seedance_2_5">Seedance 2.5</option><option value="seedance_2_0">Seedance 2.0</option><option value="jimeng">即梦</option><option value="kling">可灵</option><option value="minimax_h3">MiniMax H3</option><option value="comfyui">ComfyUI 工作流</option></select><select v-model.number="providerId"><option :value="null">选择 AI 服务商</option><option v-for="p in providers" :key="p.id" :value="p.id">{{p.name}} · {{p.model}}</option></select><V2Button variant="primary" :disabled="busy||!pipeline?.asset_atlas_locked" @click="confirmAndGenerate">{{busy?'技能生成中 '+progress+'%':'确认分镜并生成视频提示词'}}</V2Button></div></header>
<div v-if="error" class="alert">{{error}}</div>
<section class="gate"><b>资产图册</b><span :class="{ok:pipeline?.asset_atlas_locked}">{{pipeline?.asset_atlas_locked?'已锁定':'未锁定'}}</span><b>空间问题</b><span>{{pipeline?.spatial_issues.length||0}}</span><button v-if="!pipeline?.asset_atlas_locked" @click="router.push('/v2/drama/projects/'+projectId+'/assets?episode_id='+episodeId)">返回资产图册</button></section>
<section v-if="pipeline?.spatial_issues.length" class="issues"><article v-for="(issue,i) in pipeline.spatial_issues" :key="i"><b>{{issue.label}}</b><p>{{issue.message}}</p></article></section>
<section class="scene-list"><article v-for="scene in episodeBoard?.scenes" :key="scene.scene.id"><header><div><small>{{scene.scene.scene_no}}</small><h2>{{scene.scene.heading}}</h2></div><span>{{scene.shots.length}} 组 · {{scene.shot_duration.toFixed(1)}}s</span></header><div class="shots"><div v-for="shot in scene.shots" :key="shot.id"><b>U{{scene.scene.scene_no}}-S{{shot.shot_no}}</b><span>{{shot.shot_size}} · {{shot.camera_angle}} · {{shot.camera_movement}}</span><p>{{shot.timeline_storyboard||'缺少时间轴分镜'}}</p></div></div></article></section>
</div></DramaProjectShell></template>
<style scoped>.pipeline-page{width:100%;height:100%;min-width:0;min-height:0;padding:22px 24px;box-sizing:border-box;display:flex;flex-direction:column;gap:14px;overflow:hidden}.pipeline-page>header{flex:0 0 auto;display:flex;justify-content:space-between;gap:20px}.pipeline-page h1{margin:4px 0}.pipeline-page p{color:#766e63}.controls{display:flex;align-items:center;gap:8px}.controls select{padding:9px;border:1px solid #d8d1c6;border-radius:8px}.gate{flex:0 0 auto;padding:12px 14px;display:flex;gap:14px;align-items:center;background:#fff;border:1px solid #ded8ce;border-radius:10px}.gate .ok{color:#168650}.issues{flex:0 0 auto;max-height:120px;display:grid;gap:8px;overflow:auto}.issues article,.scene-list>article{padding:16px;background:#fff;border:1px solid #ded8ce;border-radius:12px}.issues p{margin:5px 0;color:#a14a3c}.scene-list{flex:1 1 auto;min-height:0;padding-right:5px;display:grid;align-content:start;gap:12px;overflow:auto;overscroll-behavior:contain}.scene-list>article>header{display:flex;justify-content:space-between}.scene-list h2{margin:3px 0}.shots{display:grid;gap:8px;margin-top:12px}.shots>div{padding:12px;background:#f7f5f0;border-radius:8px}.shots span{margin-left:12px;color:#81786d}.shots p{white-space:pre-wrap}.alert{padding:10px;color:#9b332e;background:#fff1ef;border-radius:8px}@media(max-width:900px){.pipeline-page>header,.controls{display:grid}}@media(max-width:700px){.pipeline-page{height:auto;min-height:calc(100vh - 64px);padding:16px;overflow:visible}.scene-list{overflow:visible}.issues{max-height:none}}</style>
