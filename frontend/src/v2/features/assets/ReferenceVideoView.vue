<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { resourceApi } from '@/api/modules'
import GlassCard from '@/v2/components/GlassCard.vue'
import MediaViewer from '@/v2/components/MediaViewer.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'
import V2Field from '@/v2/components/V2Field.vue'
import ResourceCard from './ResourceCard.vue'
import { type ResourceItem } from './model'
import { useResourceThumbs } from './useResourceThumbs'
const videos=ref<ResourceItem[]>([]);const interval=ref(1);const preview=ref<ResourceItem|null>(null);const extracting=ref<number|null>(null);const input=ref<HTMLInputElement|null>(null);const {thumbs,load:loadThumbs}=useResourceThumbs()
async function load(){videos.value=await resourceApi.list({media_type:'video',limit:100});void loadThumbs(videos.value)}async function upload(files:FileList|null){if(!files?.[0])return;await resourceApi.upload(files[0],'video','input');await load();if(input.value)input.value.value=''}async function extract(item:ResourceItem){extracting.value=item.id;try{const frames=await resourceApi.extractFrames(item.id,{interval:interval.value});alert(`已生成 ${frames.length} 张参考图`)}catch(e:any){alert(e.response?.data?.detail||'抽帧失败，请检查 ffmpeg')}finally{extracting.value=null}}
onMounted(load)
</script>
<template><div class="v2-page"><div class="v2-page-heading heading"><div><StatusBadge tone="info">参考内容</StatusBadge><h1>参考视频</h1><p>上传视频、预览首帧，并按时间间隔提取参考图。</p></div><input ref="input" hidden type="file" accept="video/*" @change="upload(($event.target as HTMLInputElement).files)"/><V2Button variant="primary" @click="input?.click()">上传视频</V2Button></div><GlassCard padding="sm"><div class="controls"><V2Field label="抽帧间隔（秒）"><input v-model.number="interval" type="number" min="0.1" step="0.5"/></V2Field><span>抽取的帧会作为图片素材保存到素材库</span></div></GlassCard><div class="video-grid"><div v-for="video in videos" :key="video.id" class="video-item"><ResourceCard :item="video" :thumb="thumbs[video.id]" @open="preview=video" @select="preview=video"/><V2Button :disabled="extracting===video.id" @click="extract(video)">{{ extracting===video.id?'抽帧中…':'按间隔抽帧' }}</V2Button></div><p v-if="!videos.length">暂无参考视频</p></div><MediaViewer :open="!!preview" :output="preview?{id:preview.id,filename:preview.filename,media_type:'video',mime:preview.mime}:null" @close="preview=null"/></div></template>
<style scoped>.heading{display:flex;align-items:flex-end;justify-content:space-between}.heading h1{margin-top:14px}.controls{display:flex;align-items:end;gap:16px}.controls .v2-field{width:180px}.controls span{padding-bottom:10px;color:var(--v2-text-muted)}.video-grid{margin-top:15px;display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.video-item{display:grid;gap:7px}.video-grid>p{color:var(--v2-text-muted)}@media(max-width:1050px){.video-grid{grid-template-columns:repeat(3,1fr)}}@media(max-width:700px){.video-grid{grid-template-columns:repeat(2,1fr)}.controls{align-items:flex-start;flex-direction:column}.controls .v2-field{width:100%}}</style>
