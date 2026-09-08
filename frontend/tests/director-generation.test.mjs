import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'
const url=s=>`data:text/javascript;base64,${Buffer.from(s).toString('base64')}`
const transpile=s=>ts.transpileModule(s,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText
const helper=url(transpile(readFileSync(new URL('../src/v2/features/generate/workflowParameters.ts',import.meta.url),'utf8')))
const source=transpile(readFileSync(new URL('../src/v2/features/short-drama/directorGeneration.ts',import.meta.url),'utf8')).replace(/from ['"].*\/workflowParameters['"]/g,`from ${JSON.stringify(helper)}`)
const {buildDirectorRequest,applyVideoPrompt,videoPromptKey,applyVideoDefaults}=await import(url(source))
const draft=()=>({frames:[{id:'start',generation_service:'gemini_image',workflow_version_id:11,params:{prompt:'Comfy prompt',image:8},gemini_provider_id:9,gemini_params:{size:'1024x1024',reference_resource_ids:[3,2]}}],video_workflow_version_id:22,video_params:{prompt:'Video prompt',first:7},video_mode:'first'})
const workflows=[{workflow_version_id:11,parameters:[{key:'prompt',type:'textarea'},{key:'image',type:'image'}]},{workflow_version_id:22,parameters:[{key:'prompt',type:'textarea'},{key:'first',type:'image'}]}]
test('Gemini frame submission does not require or leak ComfyUI workflow parameters',()=>{
 const d=draft(),body=buildDirectorRequest('start',d,workflows)
 assert.equal(body.workflow_version_id,null);assert.equal(body.provider_config_id,9)
 assert.equal(body.generation_service,'gemini_image')
 assert.deepEqual(body.params,{size:'1024x1024',reference_resource_ids:[3,2]})
 body.params.reference_resource_ids.push(99)
 assert.deepEqual(d.frames[0].gemini_params.reference_resource_ids,[3,2])
})
test('video always submits through ComfyUI even when current frame uses Gemini',()=>{
 const body=buildDirectorRequest('video',draft(),workflows)
 assert.equal(body.generation_service,'comfyui');assert.equal(body.provider_config_id,null)
 assert.equal(body.workflow_version_id,22);assert.equal(body.mode,'first')
 assert.deepEqual(body.params,{prompt:'Video prompt',first:7})
})
test('returning to ComfyUI keeps its independent frame parameters',()=>{
 const d=draft();d.frames[0].generation_service='comfyui'
 const body=buildDirectorRequest('start',d,workflows)
 assert.equal(body.workflow_version_id,11);assert.equal(body.provider_config_id,null)
 assert.deepEqual(body.params,{prompt:'Comfy prompt',image:8})
 assert.equal(d.frames[0].gemini_params.size,'1024x1024')
})

test('AI prompt fills mapped workflow input, preserving action/camera and negative prompt',()=>{
 const d=draft();d.video_prompt='原动作与运镜不变';d.video_params={negative_prompt:'no blur',reference:17}
 const w={...workflows[1],mapping:{text:'prompt'},parameters:[{key:'negative_prompt',type:'textarea'},{key:'text',type:'textarea'},{key:'reference',type:'image'}]}
 const prompt='detailed_description:\n<d>[中文] "甲：别走！"</d>'
 applyVideoPrompt(d,w,prompt)
 assert.equal(d.video_prompt,'原动作与运镜不变')
 assert.deepEqual(d.video_params,{negative_prompt:'no blur',reference:17,text:prompt})
 assert.equal(buildDirectorRequest('video',d,[w]).params.text,prompt)
})
test('AI prompt uses positive input and refuses a workflow without prompt',()=>{
 const d=draft();d.video_prompt='保持';const before=structuredClone(d)
 assert.equal(videoPromptKey({parameters:[{key:'negative_prompt',type:'textarea'},{key:'positive_prompt',type:'textarea'}]}),'positive_prompt')
 assert.throws(()=>applyVideoPrompt(d,{parameters:[{key:'negative_prompt',type:'textarea'}]},'new'),/没有视频提示词/)
 assert.deepEqual(d,before)
})


test('empty video media controls do not overwrite server automatic assignments',()=>{
 const d=draft();d.video_params={first:0,refs:[],sound:null,prompt:'保持提示词'}
 const w={workflow_version_id:22,parameters:[{key:'first',type:'image'},{key:'refs',type:'image',multiple:true},{key:'sound',type:'audio'},{key:'prompt',type:'textarea'}]}
 assert.deepEqual(buildDirectorRequest('video',d,[w]).params,{prompt:'保持提示词'})
 d.video_params.refs=[9,3]
 assert.deepEqual(buildDirectorRequest('video',d,[w]).params.refs,[9,3])
 assert.deepEqual(d.video_params.first,0)
})


test('standard video defaults use total duration and actual ratio option values',()=>{
 for(const [ratio,values,expected] of [['16:9',['9:16','16:9'],'16:9'],['16:9',['9:16 (Portrait Widescreen)','16:9 (Widescreen)'],'16:9 (Widescreen)'],['9:16',['16:9 (Widescreen)','9:16 (Portrait Widescreen)'],'9:16 (Portrait Widescreen)']]){
  const d=draft();d.video_params={prompt:'keep',duration:5,size:'wrong'}
  const w={parameters:[{key:'duration',type:'float'},{key:'size',type:'select',options:values.map(value=>({label:value,value}))}],mapping:{}}
  applyVideoDefaults(d,w,18.5,ratio)
  assert.deepEqual(d.video_params,{prompt:'keep',duration:18.5,size:expected})
 }
})
