<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {http} from '@/api/client'
type Param={key:string;label:string;type:string}
type Workflow={id:number;name:string;version:number;parameters:Param[]}
const list=ref<Workflow[]>([]), id=ref(0), prompt=ref(''), mapping=ref<Record<string,string>>({}), notice=ref('')
const roles={portrait:'人像',costume:'服装',pose:'姿势 / 深度',extras:'附加图',composite:'三合一拼图'}
const fields=computed(()=>list.value.find(w=>w.id===id.value)?.parameters||[])
const url='/api/v2/gallery'
const mode=ref('all'), loading=ref(false)
onMounted(load)
async function load(){
  loading.value=true; notice.value=''; id.value=0; prompt.value=''; mapping.value={}
  try {
    list.value=(await http.get(url+'/workflows',{baseURL:''})).data
    const c=(await http.get(url+'/config',{baseURL:'',params:{mode:mode.value}})).data
    if(c){id.value=c.workflow_version_id;prompt.value=c.prompt_key;mapping.value=c.mapping}
  } catch{notice.value='读取配置失败'} finally{loading.value=false}
}
async function save(){
  try {
    await http.put(url+'/config',{workflow_version_id:id.value,prompt_key:prompt.value,mapping:Object.fromEntries(Object.entries(mapping.value).filter(([,v])=>v))},{baseURL:'',params:{mode:mode.value}})
    notice.value='配置已发布'
  } catch(e:any){notice.value=e.response?.data?.detail||'发布失败'}
}
</script>
<template><main class="config"><h1>图库合成工作流</h1><p>将图库输入绑定到 Console 工作流版本。发布后，图库按此配置生成任务。</p>
<label>生成组合<select v-model="mode" :disabled="loading" @change="load"><option value="all">人像 + 服装 + 姿势</option><option value="outfit">人像 + 服装</option><option value="pose">人像 + 姿势</option></select></label>
<label>工作流版本<select v-model="id" @change="mapping={};prompt=''"><option :value="0">请选择</option><option v-for="w in list" :value="w.id">{{w.name}} · v{{w.version}} (#{{w.id}})</option></select></label>
<label>提示词<select v-model="prompt"><option value="">请选择</option><option v-for="p in fields.filter(f=>['text','textarea'].includes(f.type))" :value="p.key">{{p.label}} · {{p.key}}</option></select></label>
<label v-for="(name,key) in roles">{{name}}<select v-model="mapping[key]"><option value="">不绑定</option><option v-for="p in fields.filter(f=>f.type==='image')" :value="p.key">{{p.label}} · {{p.key}}</option></select></label>
<button @click="save">发布配置</button><span role="status">{{notice}}</span><a href="/gallery/studio">打开图库合成台</a></main></template>
<style scoped>.config{display:grid;gap:16px;max-width:680px}.config label{display:grid;gap:4px}select,button{padding:8px;background:var(--v2-surface-soft);color:inherit;border:1px solid var(--v2-border)}</style>
