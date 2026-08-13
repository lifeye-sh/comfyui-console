import { onUnmounted, ref } from 'vue'
import { getAccessToken } from '@/api/client'
import { resourceApi } from '@/api/modules'
import type { ResourceItem } from './model'
export function useResourceThumbs(){const thumbs=ref<Record<number,string>>({});async function fetchBlob(url:string){const r=await fetch(url,{headers:{Authorization:`Bearer ${getAccessToken()||''}`}});if(!r.ok)throw new Error();return URL.createObjectURL(await r.blob())}async function load(items:ResourceItem[]){let cursor=0;async function worker(){while(cursor<items.length){const item=items[cursor++];if(thumbs.value[item.id]||item.media_type==='audio')continue;try{thumbs.value[item.id]=await fetchBlob(resourceApi.thumbUrl(item.id))}catch{}}}await Promise.all(Array.from({length:Math.min(6,items.length)},worker))}function clear(){Object.values(thumbs.value).forEach(URL.revokeObjectURL);thumbs.value={}}onUnmounted(clear);return{thumbs,load,clear,fetchBlob}}
