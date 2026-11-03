import {RandomBatch} from '@/components/studio/RandomBatch'
import type {RecipeState} from '@/types/gallery'
import {createFileRoute, Link} from '@tanstack/react-router'
import {useEffect, useRef, useState} from 'react'
import {useStudio} from '@/store/studioStore'
import {buildRecipePrompt, fileToDataUrl, stitchRecipeCanvas, STYLE_PRESETS} from '@/services/aiGenerator'
import {poseImagePath, referenceImageUrl, uploadedReferences} from '@/lib/recipeImages'
import {Button} from '@/components/ui/button'

export const Route=createFileRoute('/studio')({component:Studio,staticData:{title:'AI 角色合成台'}})
const roles=['portrait','costume','pose'] as const
const labels={portrait:'人像',costume:'服装',pose:'姿势',extras:'附加图',composite:'拼图'}
type Role=keyof typeof labels
type Field={key:string;label:string;type:string;default?:string|number|boolean;options?:{label:string;value:string|number}[];options_from?:string}
type Config={revision:string;name:string;workflow_version_id:number;prompt_key:string;mapping:Partial<Record<Role,string>>;parameters:Field[]}

async function api(path:string,init:RequestInit={}){
  const headers=new Headers(init.headers)
  headers.set('Authorization','Bearer '+(localStorage.getItem('cc_access_token')||''))
  const res=await fetch('/api/'+path,{...init,headers})
  if(res.status===401){sessionStorage.setItem('gallery-login-return','/gallery/studio');location.assign('/login');throw Error('请登录 Console')}
  if(!res.ok){const detail=await res.json().catch(()=>({}));throw Error(typeof detail.detail==='string'?detail.detail:'请求失败 HTTP '+res.status)}
  return res
}
async function upload(src:string){
  const response=await fetch(referenceImageUrl(src))
  if(!response.ok)throw Error('参考图片读取失败')
  const blob=await response.blob()
  if(!blob.type.startsWith('image/'))throw Error('参考资源不是可用图片')
  const data=new FormData();data.append('file',blob,'gallery.'+blob.type.split('/')[1])
  return (await (await api('v1/resources',{method:'POST',body:data})).json()).id as number
}
function imageSources(recipe:RecipeState){return {portrait:recipe.portrait?.原图,costume:recipe.costume?.原图||recipe.costume?.预览图,pose:recipe.pose&&poseImagePath(recipe.pose)}}
function Studio(){
  const {recipe:original,safeMode,poseDepthMode,setPortrait,setCostume,setPose,toggleRecipePoseDepth,addExtraImage,removeExtraImage}=useStudio()
  const [mode,setMode]=useState(()=>sessionStorage.getItem('gallery-mode')||'all')
  const activeRoles=roles.filter(r=>!(r==='costume'&&mode==='pose')&&!(r==='pose'&&mode==='outfit'))
  const recipe={...original,costume:mode==='pose'?null:original.costume,pose:mode==='outfit'?null:original.pose}
  const [picker,setPicker]=useState<typeof roles[number]|null>(null)
  const frame=useRef<HTMLIFrameElement>(null)
  const [cfg,setCfg]=useState<Config|null>(null),[style,setStyle]=useState('realistic'),[custom,setCustom]=useState<string|null>(null)
  const [options,setOptions]=useState<Record<string,string|number|boolean>>({})
  const [provider,setProvider]=useState(0)
  const [providers,setProviders]=useState<{id:number;name:string;model:string;enabled:boolean}[]>([])
  const [size,setSize]=useState('')
  useEffect(()=>{api('v2/image-providers').then(r=>r.json()).then(rows=>setProviders(rows.filter((p:{enabled:boolean})=>p.enabled))).catch(e=>setError(e.message))},[])
  const [settings,setSettings]=useState<Record<string,{options:Field['options']}>>({})
  const [status,setStatus]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[image,setImage]=useState(''),[stitch,setStitch]=useState('')
  const [task,setTask]=useState(Number(sessionStorage.getItem('gallery-task'))||0)
  const [recent,setRecent]=useState<{id:number;status:string;version:number|null;recipe:{provider_id?:number;prompt:string;selection:Record<string,string>}}[]>([])
  useEffect(()=>{let active=true;api('v2/gallery/generations').then(r=>r.json()).then(rows=>{if(active)setRecent(rows)}).catch(()=>{});return()=>{active=false}},[task])
  const guard=useRef(false),retry=useRef({signature:'',id:''})
  const prompt=custom??buildRecipePrompt(recipe,style)
  const sources=imageSources(recipe)
  useEffect(()=>{let active=true;setCfg(null);setError('');setOptions({})
    api('v2/gallery/config?mode='+mode).then(r=>r.json()).then(c=>{if(active)setCfg(c)}).catch(e=>{if(active)setError(e.message)})
    return()=>{active=false}
  },[mode])
  useEffect(()=>{api('v1/settings/select-options').then(r=>r.json()).then(s=>{
    setSettings(s);setSize(s.image_size?.default_value||s.image_size?.options?.[0]?.value||'')
  }).catch(e=>setError(e.message))},[])
  useEffect(()=>{setStitch('')},[original,mode])
  useEffect(()=>{
    if(!picker)return
    let loading=false
    async function receive(e:MessageEvent){
      if(loading||e.origin!==location.origin||e.source!==frame.current?.contentWindow||e.data?.type!=='gallery-resource-picked')return
      const item=e.data.item
      if(!item){setPicker(null);return}
      if(!Number.isSafeInteger(item.id)||item.id<=0)return
      loading=true
      try{
        const blob=await (await api('v1/resources/'+item.id+'/file')).blob()
        await pick(new File([blob],item.name,{type:blob.type}),picker!,item.id)
      }catch(err){setError(String(err))}finally{setPicker(null)}
    }
    window.addEventListener('message',receive);return()=>window.removeEventListener('message',receive)
  },[picker])
  useEffect(()=>{
    if(!task)return
    let active=true,timer:ReturnType<typeof setTimeout>,url=''
    setImage('')
    async function refresh(){
      try{
        const t=await (await api('v1/tasks/'+task)).json()
        if(!active)return
        setStatus('#'+task+' · '+t.status+(t.error?' · '+t.error:''))
        if(t.status==='SUCCESS'){
          const outputs=await (await api('v1/tasks/'+task+'/outputs')).json()
          const out=outputs.find((o:{media_type:string})=>o.media_type==='image')
          if(out){const blob=await (await api('v1/resources/'+out.id+'/file')).blob();if(active){url=URL.createObjectURL(blob);setImage(url)}}
        }else if(!['FAILED','CANCELLED','DRAFT'].includes(t.status))timer=setTimeout(refresh,2500)
      }catch(e){if(active)setError(String(e))}
    }
    void refresh();return()=>{active=false;clearTimeout(timer);if(url)URL.revokeObjectURL(url)}
  },[task])
  async function submitRecipe(recipe:RecipeState, requestKey?:string){
      const sources=imageSources(recipe),prompt=custom??buildRecipePrompt(recipe,style)
      if(!prompt.trim())throw Error('请输入提示词')
      for(const r of activeRoles)if(!sources[r])throw Error('请选择'+labels[r]+'参考图')
      const refs:Partial<Record<Role,number[]>>={}, selection:Record<string,string>={}
      for(const role of roles)if(sources[role]){
        if(!provider&&!cfg?.mapping[role]&&!cfg?.mapping.composite)throw Error(labels[role]+'未绑定工作流输入')
        selection[role]=recipe[role]!.id
      }
      if(recipe.pose){selection.angle=recipe.pose.角度;selection.variant=recipe.pose.useDepth?'depth':'original'}
      const extras=recipe.extraImages||[]
      if(extras.length&&!provider&&!cfg?.mapping.extras)throw Error('当前工作流未绑定附加图输入')
      if(!provider&&cfg?.mapping.composite&&roles.some(r=>sources[r]))refs.composite=[await upload(await stitchRecipeCanvas(recipe))]
      else for(const r of activeRoles){
        const id=recipe[r]!.id.match(/^console:(\d+)$/)
        refs[r]=[id?Number(id[1]):await upload(sources[r]!)]
      }
      if(extras.length)refs.extras=await Promise.all(extras.map(x=>upload(x.url)))
      const payload={mode,provider_id:provider||null,revision:provider?'':cfg!.revision,prompt,refs,options:provider?{size}:options,selection}
      const signature=JSON.stringify(payload)
      if(!requestKey&&retry.current.signature!==signature)retry.current={signature,id:crypto.randomUUID()}
      const result=await (await api('v2/gallery/generations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...payload,request_id:requestKey||retry.current.id})})).json()
      return result.task_id as number
  }
  function trackTask(id:number){sessionStorage.setItem('gallery-task',String(id));setTask(id);setStatus('已提交')}
  async function generate(){
    if((!cfg&&!provider)||guard.current)return
    guard.current=true;setBusy(true);setError('')
    try{trackTask(await submitRecipe(recipe));retry.current.signature=''
    }catch(e){setError(e instanceof Error?e.message:String(e))}finally{guard.current=false;setBusy(false)}
  }
  async function pick(file:File,role:Role,resourceId?:number){
    const url=await fileToDataUrl(file)
    if(role==='extras'){addExtraImage({name:file.name,url});return}
    const r=uploadedReferences(file.name,url,0,0,file.size)
    if(resourceId)for(const k of roles)r[k].id='console:'+resourceId
    if(role==='portrait')setPortrait(r.portrait);if(role==='costume')setCostume(r.costume);if(role==='pose')setPose(r.pose)
  }
  return <div className="studio-page space-y-5"><h1 className="text-2xl font-bold">AI 角色合成台</h1>
    <p className="studio-links"><a href="/v2">返回控制台</a>　<a href="/v2/tasks?source=gallery">图库任务中心</a>　<a href="/v2/settings/gallery">工作流配置</a></p>
    <section className="rounded-xl border p-4 space-y-3">
      <fieldset><legend className="font-semibold">生图组合</legend><div className="mt-2 flex flex-wrap gap-2">
      {Object.entries({all:'人像 + 服装 + 姿势',outfit:'人像 + 服装',pose:'人像 + 姿势'}).map(([key,label])=><Button key={key} variant={mode===key?'default':'outline'} aria-pressed={mode===key} disabled={busy} onClick={()=>{if(mode!==key){setCfg(null);setMode(key);sessionStorage.setItem('gallery-mode',key)}}}>{label}</Button>)}
      </div></fieldset>
      <label className="studio-model font-semibold">生图模型　<select className="rounded border px-2 py-1" value={provider} disabled={busy} onChange={e=>setProvider(Number(e.target.value))}>
        <option value={0}>ComfyUI 工作流</option>{providers.map(p=><option key={p.id} value={p.id}>{p.name} · {p.model}</option>)}
      </select></label>
      {!!provider&&<label className="studio-model">图片尺寸　<select value={size} onChange={e=>setSize(e.target.value)}>{settings.image_size?.options?.map(o=><option key={String(o.value)} value={String(o.value)}>{o.label}</option>)}</select></label>}
    </section>
    <RandomBatch key={[mode,provider,cfg?.revision,safeMode].join(':')} recipe={recipe} slots={activeRoles} safe={safeMode} depth={poseDepthMode} disabled={(provider?!size:!cfg)||busy} submit={submitRecipe} onTask={trackTask} />
    {picker&&<dialog open className="fixed inset-0 z-50 m-auto h-[92vh] w-[94vw] rounded-lg border bg-background p-2 shadow-xl" aria-label="Console 素材库">
      <button onClick={()=>setPicker(null)}>关闭素材库</button><iframe ref={frame} title="Console 素材选择器" src="/gallery-resource-picker" className="h-[95%] w-full"/></dialog>}
    <div className="studio-slots grid gap-3">{activeRoles.map(r=><section key={r} className="rounded-xl border p-3 space-y-2">
      <h2 className="font-semibold">{labels[r]}参考</h2><div className="studio-preview">{sources[r]?<img src={referenceImageUrl(sources[r]!)} alt={labels[r]+'参考图'}/>:<><img src={{portrait:'/gallery/thumbs/portrait/f71f980dde3.webp',costume:'/gallery/thumbs/costume/SPR-0001.webp',pose:'/gallery/thumbs/full_single_P001_front.jpg'}[r]} alt={labels[r]+'示例图'}/><span className="empty-caption">示例 · 尚未选择</span></>}</div>
      <Link className="block underline" to={{portrait:'/portraits',costume:'/costumes',pose:'/poses'}[r] as '/poses'}>从图库选择</Link>
      <Button variant="outline" onClick={()=>setPicker(r)}>从 Console 素材库选择</Button>
      <input aria-label={'上传'+labels[r]} type="file" accept="image/*" onChange={e=>{const f=e.target.files?.[0];if(f)void pick(f,r).catch(e=>setError(String(e)))}}/>
      {sources[r]&&<Button variant="outline" onClick={()=>({portrait:setPortrait,costume:setCostume,pose:setPose}[r])(null)}>移除</Button>}
      {r==='pose'&&recipe.pose&&recipe.pose.source!=='upload'&&<Button onClick={()=>toggleRecipePoseDepth()}>切换白模 / 深度</Button>}
    </section>)}</div>
    <Button variant="outline" onClick={()=>stitchRecipeCanvas(recipe).then(setStitch).catch(e=>setError(String(e)))}>预览拼图</Button>
    {stitch&&<img className="max-h-72" src={stitch}/>}
    <label className="block">附加参考图 <input type="file" accept="image/*" multiple onChange={e=>{for(const f of Array.from(e.target.files||[]))void pick(f,'extras').catch(e=>setError(String(e)))}}/></label>
    {recipe.extraImages?.map(x=><Button key={x.id} variant="outline" onClick={()=>removeExtraImage(x.id)}>{x.name} ×</Button>)}
    <div>画风 <select value={style} onChange={e=>setStyle(e.target.value)}>{Object.entries(STYLE_PRESETS).map(([v,p])=><option key={v} value={v}>{p.label}</option>)}</select></div>
    <label className="block font-semibold" htmlFor="studio-prompt">画面提示词</label><textarea id="studio-prompt" className="w-full rounded border p-3" rows={5} aria-label="提示词" value={prompt} onChange={e=>setCustom(e.target.value)}/><button onClick={()=>setCustom(null)}>重新按配方生成提示词</button>
    {!provider&&<section className="space-y-2 rounded border p-3"><b>Console 工作流 · {cfg?.name||'待配置'}</b>
    {cfg&&Object.entries(cfg.mapping).map(([r,k])=><small key={r} className="block">{labels[r as Role]} → {k}</small>)}
    {cfg?.parameters.filter(p=>p.key!==cfg.prompt_key&&!['image','audio','video'].includes(p.type)).map(p=>{
      const opts=p.options||settings[p.options_from||'']?.options
      const v=options[p.key]??p.default??''
      return <label className="block" key={p.key}>{p.label}　{opts?.length?<select value={String(v)} onChange={e=>setOptions({...options,[p.key]:opts.find(o=>String(o.value)===e.target.value)!.value})}><option value="" disabled>请选择</option>{opts.map(o=><option key={String(o.value)} value={String(o.value)}>{o.label}</option>)}</select>:<input className="border" value={String(v)} onChange={e=>setOptions({...options,[p.key]:['seed','int','float','slider'].includes(p.type)?Number(e.target.value):p.type==='bool'?e.target.value==='true':e.target.value})}/>}</label>
    })}</section>}
    <Button onClick={generate} disabled={(provider?!size:!cfg)||busy}>{busy?'正在提交…':'生成角色图'}</Button> <span>{status}</span>
    {error&&<p role="alert">{error}</p>}{image&&<img className="max-h-[65vh]" src={image} alt="生成结果"/>}
    <details><summary>最近的图库任务（{recent.length}）</summary>{recent.map(t=><article key={t.id} className="border-b py-2">
      <b>#{t.id} · {t.recipe.provider_id?(providers.find(p=>p.id===t.recipe.provider_id)?.name||'第三方模型 #'+t.recipe.provider_id):'工作流版本 #'+t.version}</b><p>{Object.values(t.recipe.selection||{}).join(' · ')}</p><p>{t.recipe.prompt}</p>
      <Button variant="outline" onClick={()=>{sessionStorage.setItem('gallery-task',String(t.id));setTask(t.id)}}>查看任务结果</Button>
    </article>)}</details>
  </div>
}
