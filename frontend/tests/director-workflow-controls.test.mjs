import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {parse,compileScript} from '@vue/compiler-sfc'
import ts from 'typescript'
import {createRenderer,h,ref,nextTick} from 'vue'
const moduleUrl=s=>`data:text/javascript;base64,${Buffer.from(s).toString('base64')}`
const transpile=s=>ts.transpileModule(s,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText
const helper=moduleUrl(transpile(readFileSync(new URL('../src/v2/features/generate/workflowParameters.ts',import.meta.url),'utf8')))
const {descriptor}=parse(readFileSync(new URL('../src/v2/features/short-drama/DirectorWorkflowControls.vue',import.meta.url),'utf8'))
let source=transpile(compileScript(descriptor,{id:'director-controls',inlineTemplate:true}).content)
source=source.replace(/from ['"]vue['"]/g,`from ${JSON.stringify(import.meta.resolve('vue'))}`)
 .replace(/import .* from ['"].*WorkflowParameterFields.vue['"];?/g,'')
 .replace(/import .* from ['"].\/directorApi['"];?/g,'')
 .replace(/import \{ videoPromptKey, withDefaultNegative \} from ['"].*directorGeneration['"];?/g,"const videoPromptKey=w=>w?.parameters.find(p=>w.mapping?.[p.key]==='prompt')?.key||w?.parameters.find(p=>p.key==='prompt')?.key||w?.parameters.find(p=>/prompt/i.test(p.key)&&!/negative/i.test(p.key))?.key;const withDefaultNegative=v=>String(v||'')")
 .replace(/from ['"].*\/workflowParameters['"]/g,`from ${JSON.stringify(helper)}`)
source='export const fieldProps=[];const WorkflowParameterFields={props:["parameters","excludeKeys"],setup(props){fieldProps.push(props);return()=>null}};const directorApi={bind:async()=>{}};'+source
const {default:Controls,fieldProps}=await import(moduleUrl(source))
const node=type=>({type,children:[],props:{},addEventListener(){},removeEventListener(){},get options(){return this.children.filter(n=>n.type==='option')}})
const renderer=createRenderer({createElement:node,createText:node,createComment:node,setText(){},setElementText(){},patchProp(n,k,a,b){n.props[k]=b;n[k]=b},parentNode:n=>n.parent,nextSibling:()=>null,insert(n,p){n.parent=p;p.children.push(n)},remove(n){n.parent.children=n.parent.children.filter(x=>x!==n)}})
const find=(n,p)=>p(n)?n:n.children.map(x=>find(x,p)).find(Boolean)
test('workflow switch restores manual references and excludes foreign fields',async()=>{
 const current=ref(11),params=ref({reference:17,prompt:'my frame'})
 const workflows=[11,12].map(id=>{const promptKey=id===11?'prompt':'positive_prompt';return {workflow_version_id:id,generation_type_id:1,generation_type_name:'Image',media_type:'image',mapping:{[promptKey]:'prompt'},parameters:[{key:promptKey,type:'textarea',default:'default'},{key:id===11?'reference':'other_reference',type:'image'}]}})
 const root=node('root');const app=renderer.createApp({setup:()=>()=>h(Controls,{projectId:1,workflows,mediaType:'image',versionId:current.value,params:params.value,settings:{},'onUpdate:versionId':v=>current.value=v,'onUpdate:params':v=>params.value=v})});app.mount(root)
 try{
  const select=find(root,n=>n.type==='select'&&n.props.onChange&&n.props.value===11)
  select.props.onChange({target:{value:'12'}});await nextTick()
  assert.equal(current.value,12);assert.deepEqual(params.value,{other_reference:null,positive_prompt:'my frame'})
  params.value={other_reference:23,positive_prompt:'alternate'};await nextTick()
  select.props.onChange({target:{value:'11'}});await nextTick()
  assert.deepEqual(params.value,{reference:17,prompt:'alternate'})
  select.props.onChange({target:{value:'12'}});await nextTick()
  assert.deepEqual(params.value,{other_reference:23,positive_prompt:'alternate'})
 }finally{app.unmount()}
})

test('video resource slot replaces media pickers without affecting frame inputs',async()=>{
 const root=node('root'),hide=ref(true);fieldProps.length=0
 const workflows=[{workflow_version_id:21,generation_type_id:2,generation_type_name:'Video',media_type:'video',mapping:{},parameters:[{key:'image',type:'image'},{key:'audio',type:'audio'},{key:'video',type:'video'},{key:'prompt',type:'textarea'}]}]
 const app=renderer.createApp({setup:()=>()=>h(Controls,{projectId:1,workflows,mediaType:'video',versionId:21,params:{},settings:{},hideMediaInputs:hide.value},{media:()=>h('h3',{'data-test':'resource-heading'},'工作流输入 · 来自已勾选的视频资源')})})
 app.mount(root)
 try{
  assert.deepEqual(fieldProps[0].excludeKeys,['image','audio','video'])
  assert.ok(find(root,n=>n.props['data-test']==='resource-heading'))
  hide.value=false;await nextTick()
  assert.deepEqual(fieldProps[0].excludeKeys,[])
 }finally{app.unmount()}
})


test('director prop cards render bound thumbnails with accessible alt text',()=>{
 const source=readFileSync(new URL('../src/v2/features/short-drama/DramaDirectorWorkspace.vue',import.meta.url),'utf8')
 assert.match(source,/v-if="propResourceId\(pid\)&&thumbs\[propResourceId\(pid\)!\]"/)
 assert.match(source,/:src="thumbs\[propResourceId\(pid\)!\]"/)
 assert.match(source,/:alt="propName\(pid\)"/)
 assert.match(source,/已绑定道具图片/)
})


test('director desktop layout keeps shell and side columns fixed while titles remain visible',()=>{
 const shell=readFileSync(new URL('../src/v2/features/short-drama/DramaProjectShell.vue',import.meta.url),'utf8')
 const page=readFileSync(new URL('../src/v2/features/short-drama/DramaDirectorWorkspace.vue',import.meta.url),'utf8')
 assert.match(shell,/height:100vh;min-height:0;overflow:hidden/)
 assert.match(shell,/grid-template-rows:64px minmax\(0,1fr\)/)
 assert.match(shell,/director-shell \.project-content\{overflow:hidden\}/)
 assert.match(page,/grid-template-columns:190px minmax\(0,1fr\) 340px/)
 assert.match(page,/\.shot-rail\{position:static/)
 assert.match(page,/\.inspector\{position:static/)
 assert.match(page,/grid-template-columns:42px minmax\(0,1fr\)/)
 assert.match(page,/\.make-canvas\{min-width:0;height:100%;overflow-y:auto/)
 assert.match(page,/visibility:visible/)
 assert.match(page,/\.make\{flex:1;min-width:0;width:100%;max-width:100%/)
 assert.match(page,/\.make-heading\{[^}]*max-width:100%;min-width:0;[^}]*overflow:hidden/)
 assert.match(page,/\.make-heading>div:first-child\{min-width:0;max-width:100%;flex:1;overflow:hidden/)
 assert.match(page,/\.make-heading h1\{[^}]*white-space:nowrap;text-overflow:ellipsis/)
})

test('director task errors open in a modal without rendering inline details',()=>{
 const page=readFileSync(new URL('../src/v2/features/short-drama/DramaDirectorWorkspace.vue',import.meta.url),'utf8')
 assert.match(page,/class="task-error-button" @click="openTaskError\(task\)"/)
 assert.match(page,/v-if="taskErrorDetail" class="plan-layer task-error-modal"/)
 assert.match(page,/<pre>\{\{taskErrorDetail\.message\}\}<\/pre>/)
 assert.doesNotMatch(page,/<details v-if="task\.error/)
 assert.match(page,/\.task-error-modal pre\{[^}]*max-height:65vh;overflow:auto/)
})




test('director can adopt the previous selected video tail as the current start frame',()=>{
 const page=readFileSync(new URL('../src/v2/features/short-drama/DramaDirectorWorkspace.vue',import.meta.url),'utf8')
 const api=readFileSync(new URL('../src/v2/features/short-drama/directorApi.ts',import.meta.url),'utf8')
 assert.match(page,/const previousSelectedVideo=computed/)
 assert.match(page,/resourceApi\.extractFrames\(video\.resource_id,\{timestamps:'-0\.05'\}\)/)
 assert.match(page,/directorApi\.importFrame\(projectId\.value,current\.id,'start',extracted\.id\)/)
 assert.match(page,/await directorApi\.adopt\(projectId\.value,take\.id\)/)
 assert.match(page,/>取上一镜尾帧<\/button>/)
 assert.match(api,/importFrame:.*\.then\(r=>r\.data as DirectorShot\)/)
})

test('director task parameters can be restored into video or frame editors',()=>{
 const page=readFileSync(new URL('../src/v2/features/short-drama/DramaDirectorWorkspace.vue',import.meta.url),'utf8')
 const api=readFileSync(new URL('../src/v2/features/short-drama/directorApi.ts',import.meta.url),'utf8')
 assert.match(page,/function applyTaskParams\(task:DirectorShot\['tasks'\]\[number\]\)/)
 assert.match(page,/draft\.value\.video_workflow_version_id=task\.workflow_version_id/)
 assert.match(page,/draft\.value\.video_params=params/)
 assert.match(page,/target\.gemini_params=params/)
 assert.match(page,/target\.params=params/)
 assert.match(page,/>应用此任务参数<\/button>/)
 assert.match(api,/workflow_version_id:number\|null;generation_service:'comfyui'\|'gemini_image'/)
})
