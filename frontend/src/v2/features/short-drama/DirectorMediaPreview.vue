<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import { getAccessToken } from '@/api/client'
import { resourceApi } from '@/api/modules'
const props=defineProps<{resourceId?:number|null;mediaType?:string;label?:string}>()
const url=ref(''),error=ref('');let marker=0
function release(){if(url.value)URL.revokeObjectURL(url.value);url.value=''}
watch(()=>[props.resourceId,props.mediaType],async()=>{const request=++marker;release();error.value='';if(!props.resourceId)return;try{const response=await fetch(resourceApi.fileUrl(props.resourceId),{headers:{Authorization:`Bearer ${getAccessToken()||''}`}});if(!response.ok)throw new Error('预览加载失败');const blob=URL.createObjectURL(await response.blob());if(request!==marker){URL.revokeObjectURL(blob);return}url.value=blob}catch{if(request===marker)error.value='预览不可用，请检查素材或重试'}},{immediate:true})
onUnmounted(()=>{marker++;release()})
</script>
<template><div class="director-preview"><video v-if="url&&mediaType==='video'" :src="url" controls playsinline preload="metadata" :aria-label="label||'视频预览'"/><img v-else-if="url" :src="url" :alt="label||'关键帧预览'"/><div v-else class="preview-empty"><span>{{ mediaType==='video'?'▷':'▧' }}</span><p>{{ error||(resourceId?'正在加载…':label||'生成或选择候选后在这里预览') }}</p></div></div></template>
<style scoped>.director-preview{display:grid;place-items:center;min-height:240px;aspect-ratio:16/9;background:#eae6de;border-radius:12px;overflow:hidden}.director-preview img,.director-preview video{width:100%;height:100%;max-height:52vh;object-fit:contain}.preview-empty{text-align:center;color:#938673}.preview-empty span{font-size:42px}.preview-empty p{font-size:13px}</style>
