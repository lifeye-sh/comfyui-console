import type { DirectorDraft, DirectorWorkflow } from './directorApi'
import { workflowPayload } from '../generate/workflowParameters'

export const DEFAULT_NEGATIVE_RULES=[
  '严禁多手多脚肢体穿模','严禁画面内出现字幕文字','不得改变服装','不得改变发型颜色',
]
export function withDefaultNegative(value:unknown='') {
  let result=String(value||'').replace(/^[ ，,。；;\n]+|[ ，,。；;\n]+$/g,'')
  for(const rule of DEFAULT_NEGATIVE_RULES)if(!result.includes(rule))result=result?result+'，'+rule:rule
  return result
}

function negativePromptKey(workflow:DirectorWorkflow|undefined) {
  return workflow?.parameters.find(p=>workflow.mapping?.[p.key]==='negative_prompt')?.key
    || workflow?.parameters.find(p=>['negative','negative_prompt'].includes(p.key.toLowerCase()))?.key
}

/** Video always follows ComfyUI; each frame retains independent provider settings. */
export function buildDirectorRequest(target:string,draft:DirectorDraft,workflows:DirectorWorkflow[]) {
  const frame=draft.frames.find(f=>f.id===target)
  const service=target==='video'?'comfyui':frame?.generation_service||'comfyui'
  const workflowId=service==='gemini_image'?null:target==='video'?draft.video_workflow_version_id:frame?.workflow_version_id
  const parameters=workflows.find(w=>w.workflow_version_id===workflowId)?.parameters||[]
  const params=service==='gemini_image'?frame?.gemini_params||{}:workflowPayload(parameters,target==='video'?draft.video_params:frame?.params||{})
  if(service==='comfyui'){
    const negativeKey=negativePromptKey(workflows.find(w=>w.workflow_version_id===workflowId))
    if(negativeKey)params[negativeKey]=withDefaultNegative(params[negativeKey])
  }
  if(target==='video')for(const p of parameters){
    if(['image','video','audio'].includes(p.type)&&(!params[p.key]||Array.isArray(params[p.key])&&!params[p.key].length))delete params[p.key]
  }
  return {
    scope:target,generation_service:service,workflow_version_id:workflowId,
    provider_config_id:service==='gemini_image'?frame?.gemini_provider_id:null,
    mode:target==='video'?draft.video_mode:'manual',
    params:JSON.parse(JSON.stringify(params)) as Record<string,any>,idempotency_key:crypto.randomUUID(),
  }
}

/** Resolve only positive text inputs; explicit workflow roles take precedence. */
export function videoPromptKey(workflow:DirectorWorkflow|undefined) {
  const text=workflow?.parameters.filter(p=>['text','textarea'].includes(p.type))||[]
  return text.find(p=>workflow?.mapping?.[p.key]==='prompt')?.key
    || text.find(p=>p.key==='prompt')?.key
    || text.find(p=>/prompt/i.test(p.key)&&!/negative/i.test(p.key))?.key
}
export function applyVideoPrompt(draft:DirectorDraft,workflow:DirectorWorkflow|undefined,prompt:string) {
  const key=videoPromptKey(workflow)
  if(!key)throw new Error('当前工作流没有视频提示词输入，请在生成类型配置中添加或绑定提示词用途')
  draft.video_params={...draft.video_params,[key]:prompt}
}


export function applyVideoDefaults(draft:DirectorDraft,workflow:DirectorWorkflow|undefined,duration:number,ratio:string,settings:any={}) {
 if(!workflow)return
 const values={...draft.video_params}
 const desired=ratio.startsWith('16:9')||ratio==='landscape'?'16:9':'9:16'
 for(const p of workflow.parameters){
  if(p.key==='duration'||workflow.mapping?.[p.key]==='duration')values[p.key]=duration
  if(p.key==='size'){
   const options=p.options?.length?p.options:settings[p.options_from||'video_size']?.options||[]
   const option=options.find((o:any)=>o.value===desired)||options.find((o:any)=>String(o.value).startsWith(desired+' '))||options.find((o:any)=>String(o.label).startsWith(desired))
   if(option)values[p.key]=option.value
   else if(!options.length)values[p.key]=desired
  }
 }
 const negativeKey=negativePromptKey(workflow)
 if(negativeKey)values[negativeKey]=withDefaultNegative(values[negativeKey])
 draft.video_params=values
}
