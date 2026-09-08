<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import WorkflowParameterFields from '../generate/WorkflowParameterFields.vue'
import { workflowDefaults } from '../generate/workflowParameters'
import { videoPromptKey, withDefaultNegative } from './directorGeneration'
import type { DirectorWorkflow } from './directorApi'
const props=defineProps<{projectId:number;workflows:DirectorWorkflow[];mediaType:'image'|'video';versionId:number|null;params:Record<string,any>;settings:any;disabled?:boolean;hideMediaInputs?:boolean}>()
const emit=defineEmits<{'update:versionId':[number|null];'update:params':[Record<string,any>];refresh:[];autofill:[]}>()
const typeId=ref<number|null>(null)
const types=computed(()=>[...new Map(props.workflows.filter(w=>w.media_type===props.mediaType).map(w=>[w.generation_type_id,{id:w.generation_type_id,name:w.generation_type_name}])).values()])
const workflow=computed(()=>props.workflows.find(w=>w.workflow_version_id===props.versionId))
const choices=computed(()=>props.workflows.filter(w=>w.media_type===props.mediaType&&w.generation_type_id===typeId.value))
const excludedKeys=computed(()=>props.hideMediaInputs?workflow.value?.parameters.filter(p=>['image','video','audio'].includes(p.type)).map(p=>p.key)||[]:[])
const parameterCache=new Map<number,Record<string,any>>()
function negativeKey(w:DirectorWorkflow|undefined){return w?.parameters.find(p=>w.mapping?.[p.key]==='negative_prompt')?.key||w?.parameters.find(p=>['negative','negative_prompt'].includes(p.key.toLowerCase()))?.key}
function ensureNegative(w:DirectorWorkflow|undefined,values:Record<string,any>){const key=negativeKey(w);if(key)values[key]=withDefaultNegative(values[key]);return values}
watch(()=>[props.versionId,props.workflows],()=>{if(workflow.value){typeId.value=workflow.value.generation_type_id;const key=negativeKey(workflow.value);if(key&&props.params[key]!==withDefaultNegative(props.params[key]))emit('update:params',ensureNegative(workflow.value,{...props.params}))}else if(!typeId.value)typeId.value=types.value[0]?.id||null},{immediate:true})
function choose(id:number|null){
 const previous=workflow.value,previousPromptKey=videoPromptKey(previous)
 const carriedPrompt=previousPromptKey?props.params[previousPromptKey]:undefined
 if(props.versionId)parameterCache.set(props.versionId,JSON.parse(JSON.stringify(props.params)))
 const w=props.workflows.find(v=>v.workflow_version_id===id);emit('update:versionId',id)
 if(w){
  const cached=parameterCache.has(id!)
  const values=cached?JSON.parse(JSON.stringify(parameterCache.get(id!))):workflowDefaults(w,props.settings,props.mediaType==='video'?'video_size':'image_size')
  if(!cached)for(const key of Object.keys(w.mapping))delete values[key]
  const nextPromptKey=videoPromptKey(w)
  if(nextPromptKey&&typeof carriedPrompt==='string'&&carriedPrompt.trim())values[nextPromptKey]=carriedPrompt
  emit('update:params',ensureNegative(w,values))
 }else emit('update:params',{})
}
function changeType(){choose(choices.value.find(w=>w.is_default)?.workflow_version_id||choices.value[0]?.workflow_version_id||null)}
</script>
<template><section class="workflow-controls"><label>ComfyUI 生成类型<select v-model.number="typeId" :disabled="disabled" @change="changeType"><option v-for="type in types" :key="type.id" :value="type.id">{{type.name}}</option></select></label><label>工作流版本<select :value="versionId||''" :disabled="disabled" @change="choose(Number(($event.target as HTMLSelectElement).value)||null)"><option value="">请选择工作流</option><option v-for="w in choices" :key="w.workflow_version_id" :value="w.workflow_version_id">{{w.name}} · v{{w.version}}</option></select></label><p v-if="!types.length" class="muted">暂无可用工作流，请先在工作流中心配置。</p><template v-if="workflow"><button :disabled="disabled" @click="emit('autofill')">按当前镜头刷新用途参数</button><slot name="media"/><WorkflowParameterFields :exclude-keys="excludedKeys" :parameters="workflow.parameters" :model-value="params" :settings="settings" :size-key="mediaType==='video'?'video_size':'image_size'" :disabled="disabled" @update:model-value="emit('update:params',$event)"/><slot name="after-parameters"/></template></section></template>
<style scoped>.workflow-controls{display:grid;gap:12px}.workflow-controls label{display:grid;gap:6px;font-size:12px}.workflow-controls select,.workflow-controls button{width:100%;min-height:36px;padding:8px;border:1px solid #ddd5c8;border-radius:7px;background:#fff;color:#3b3429}.muted{font-size:11px;color:#8b806e}.error{font-size:12px;color:#b34940}</style>
