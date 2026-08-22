import { onUnmounted, ref } from 'vue'
import { getAccessToken } from '@/api/client'
import { resourceApi } from '@/api/modules'
import type { ResourceItem } from './model'
export function useResourceThumbs(){
  const thumbs=ref<Record<number,string>>({});
  let generation = 0
  async function fetchBlob(url:string){
    const r=await fetch(url,{headers:{Authorization:`Bearer ${getAccessToken()||''}`}})
    if(!r.ok)throw new Error()
    return URL.createObjectURL(await r.blob())
  }
  async function load(items:ResourceItem[]){
    const gen = ++generation
    let cursor=0
    async function worker(){
      while(cursor<items.length){
        if(gen!==generation) return // 被更新的 load 调用取消
        const item=items[cursor++]
        if(thumbs.value[item.id]||item.media_type==='audio')continue
        try{
          const blob=await fetchBlob(resourceApi.thumbUrl(item.id))
          if(gen!==generation){URL.revokeObjectURL(blob);return} // 被取消，释放 blob
          thumbs.value[item.id]=blob
        }catch{}
      }
    }
    await Promise.all(Array.from({length:Math.min(6,items.length)},worker))
  }
  function clear(){
    generation++ // 使所有运行中的 worker 失效
    Object.values(thumbs.value).forEach(URL.revokeObjectURL)
    thumbs.value={}
  }
  onUnmounted(clear)
  return{thumbs,load,clear,fetchBlob}
}