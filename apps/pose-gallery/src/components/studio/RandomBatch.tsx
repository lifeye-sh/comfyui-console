import {useRef,useState} from 'react'
import {useQueryClient} from '@tanstack/react-query'
import {costumesQuery,portraitsQuery,posesQuery,isNsfwCostume,isNsfwPose} from '@/api/gallery'
import {poseThumbPath,referenceImageUrl} from '@/lib/recipeImages'
import {Button} from '@/components/ui/button'
import type {RecipeState} from '@/types/gallery'

type Slot='portrait'|'costume'|'pose'
const names={portrait:'人像',costume:'服装',pose:'姿势'}
type Row={key:string;recipe:RecipeState;task?:number}

// Draw without replacement until the eligible pool is exhausted.
function sampler<T>(pool:T[]){
  let bag:T[]=[]
  return ()=>{
    if(!bag.length)bag=pool.slice()
    if(!bag.length)throw Error('当前图库没有可随机选择的素材')
    const i=Math.floor(Math.random()*bag.length), value=bag[i]
    bag[i]=bag[bag.length-1];bag.pop()
    return value
  }
}

export function RandomBatch({recipe,slots,safe,depth,disabled,submit,onTask}:{
  recipe:RecipeState;slots:Slot[];safe:boolean;depth:boolean;disabled:boolean
  submit:(recipe:RecipeState,key:string)=>Promise<number>;onTask:(id:number)=>void
}){
  const qc=useQueryClient()
  const [count,setCount]=useState('6'),[random,setRandom]=useState({portrait:true,costume:true,pose:true})
  const [rows,setRows]=useState<Row[]>([]),[working,setWorking]=useState(false),[error,setError]=useState('')
  const lock=useRef(false)
  async function run(fn:()=>Promise<void>){
    if(lock.current)return
    lock.current=true;setWorking(true);setError('')
    try{await fn()}catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{lock.current=false;setWorking(false)}
  }
  async function draw(){
    const n=Number(count)
    if(!Number.isInteger(n)||n<1||n>50)throw Error('数量须为 1 至 50 的整数')
    if(!slots.some(s=>random[s]))throw Error('请至少开启一个随机项')
    for(const s of slots)if(!random[s]&&!recipe[s])throw Error('请先选定需要固定的'+names[s])
    const enabled=(s:Slot)=>slots.includes(s)&&random[s]
    const [people,clothes,poses]=await Promise.all([
      enabled('portrait')?qc.ensureQueryData(portraitsQuery):[],
      enabled('costume')?qc.ensureQueryData(costumesQuery):[],
      enabled('pose')?qc.ensureQueryData(posesQuery).then(data=>data.items):[],
    ])
    const person=sampler(people),outfit=sampler(clothes.filter(c=>c.source!=='charadb'&&(!safe||!isNsfwCostume(c)))),
      pose=sampler(poses.filter(p=>!safe||!isNsfwPose(p)))
    setRows(Array.from({length:n},()=>({key:crypto.randomUUID(),recipe:{...recipe,
      portrait:enabled('portrait')?person():recipe.portrait,
      costume:enabled('costume')?outfit():recipe.costume,
      pose:enabled('pose')?{...pose(),useDepth:depth}:recipe.pose,
    }})))
  }
  async function enqueue(){
    for(const row of rows){
      if(row.task)continue
      const task=await submit(row.recipe,row.key)
      setRows(prev=>prev.map(r=>r.key===row.key?{...r,task}:r))
      onTask(task)
    }
  }
  const pending=rows.filter(r=>!r.task).length
  return <details className="rounded-xl border bg-card p-4"><summary className="cursor-pointer font-semibold">批量随机捏人</summary>
    <fieldset disabled={working} className="mt-4 flex flex-wrap items-center gap-4">
      <label>数量 <input type="number" min="1" max="50" value={count} className="w-20" onChange={e=>{setCount(e.target.value);setRows([])}}/></label>
      {slots.map(s=><label key={s}><input type="checkbox" checked={random[s]} onChange={e=>{setRandom({...random,[s]:e.target.checked});setRows([])}}/> 随机{names[s]}</label>)}
      <Button variant="outline" onClick={()=>void run(draw)}>随机预览</Button>
    </fieldset>
    <p className="my-2 text-sm text-muted-foreground">取消勾选即固定当前素材。预览后再提交，每套配方创建一条生成任务。</p>
    {rows.length>0&&<><ol className="grid max-h-80 gap-2 overflow-auto sm:grid-cols-2">{rows.map((r,i)=><li key={r.key} className="flex items-center gap-2 rounded-lg bg-muted p-2">
      <b>{i+1}</b>{slots.map(s=>{const item=r.recipe[s];if(!item)return null
        return <img key={s} src={referenceImageUrl(s==='pose'?poseThumbPath(r.recipe.pose!):item.缩略图)} alt={names[s]+' '+item.id} title={names[s]+' '+item.id} loading="lazy" className="h-16 w-12 rounded object-contain"/>})}
      {r.task&&<small>任务 #{r.task}</small>}</li>)}</ol>
      <Button className="mt-3" disabled={disabled||working||!pending} onClick={()=>void run(enqueue)}>{working?'处理中…':pending?'提交剩余 '+pending+' 套':'已全部提交'}</Button></>}
    {error&&<p role="alert">{error}</p>}
  </details>
}
