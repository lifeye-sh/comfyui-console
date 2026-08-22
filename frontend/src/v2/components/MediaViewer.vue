<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getAccessToken } from '@/api/client'
import { resourceApi, genTypeApi } from '@/api/modules'
import ImageEditor from './ImageEditor.vue'
import type { ResourceItem } from '@/v2/features/assets/model'
import type { TaskOutput, GenerationTypeItem } from '@/v2/features/tasks/model'
import { flattenGenerationMenu } from '@/v2/features/tasks/model'
import V2Button from './V2Button.vue'
import { formatDuration } from '@/v2/features/assets/model'
const props = defineProps<{ open: boolean; output: TaskOutput | null }>()
const emit = defineEmits<{ close: [] }>()
const router = useRouter()
const url = ref(''); const loading = ref(false); const scale = ref(1); const x = ref(0); const y = ref(0); const dragging = ref(false); const showInfo = ref(true); const metadata = ref<TaskOutput|null>(null)
const imgEl = ref<HTMLImageElement | null>(null)
const videoEl = ref<HTMLVideoElement | null>(null)
const videoTime = ref(0); const videoDuration = ref(0); const videoSeeking = ref(false); const frameExtracting = ref(false); const frameNotice = ref('')
const trimStart = ref(0); const trimEnd = ref(0); const trimProcessing = ref(false); const trimNotice = ref('')
let startX=0,startY=0,originX=0,originY=0
/** 双指缩放状态 */
let pinchDist=0, pinchScale=1, pinchCenterX=0, pinchCenterY=0, pinchOriginX=0, pinchOriginY=0
const isImage = computed(() => props.output?.media_type === 'image' || (!!props.output?.mime && props.output.mime.startsWith('image/')))
const isVideo = computed(() => props.output?.media_type === 'video' || (!!props.output?.mime && props.output.mime.startsWith('video/')))
const isAudio = computed(() => props.output?.media_type === 'audio' || (!!props.output?.mime && props.output.mime.startsWith('audio/')))
const mediaInfo = computed(() => { const output=metadata.value||props.output;if(!output)return[];const info:Array<{label:string;value:string}>=[];if(output.width&&output.height)info.push({label:output.media_type==='image'?'图片尺寸':'视频尺寸',value:`${output.width} × ${output.height}`});if((output.media_type==='video'||output.media_type==='audio')&&output.duration!=null)info.push({label:'时长',value:formatDuration(output.duration)});return info })

/** 图片操作菜单 */
const actionMenuOpen = ref(false)
const editorOpen = ref(false)
const editorResource = ref<ResourceItem | null>(null)
const actionType = ref<'image_ops' | 'gen_video'>('image_ops')
const genMenu = ref<GenerationTypeItem[]>([])
const filteredMenu = computed(() => {
  if (!genMenu.value.length) return []
  if (actionType.value === 'image_ops') {
    // 图片操作：排除文生图（t2i）
    return genMenu.value.filter(t => t.media_type === 'image' && t.code !== 't2i')
  } else {
    // 生成视频：排除文生视频（t2v）
    return genMenu.value.filter(t => t.media_type === 'video' && t.code !== 't2v')
  }
})

async function loadGenMenu() {
  if (genMenu.value.length) return
  try {
    const menu = await genTypeApi.menu()
    genMenu.value = flattenGenerationMenu(menu)
  } catch { /* ignore */ }
}

function openActionMenu(type: 'image_ops' | 'gen_video') {
  actionType.value = type
  actionMenuOpen.value = true
  void loadGenMenu()
}

function pickGenType(item: GenerationTypeItem) {
  if (!props.output) return
  actionMenuOpen.value = false
  emit('close')
  router.push({ path: `/v2/generate/${item.code}`, query: { resource_id: String(props.output.id) } })
}
async function openEditor() {
  if (!props.output) return
  editorResource.value = {
    id: props.output.id,
    owner_id: null,
    folder_id: null,
    media_type: 'image',
    direction: '',
    filename: props.output.filename || `image_${props.output.id}`,
    mime: props.output.mime || 'image/*',
    size: 0,
    width: props.output.width || null,
    height: props.output.height || null,
    duration: null,
    created_at: '',
  }
  editorOpen.value = true
}

async function load() { if(url.value) URL.revokeObjectURL(url.value); url.value='';metadata.value=props.output;scale.value=1;x.value=0;y.value=0;loading.value=false;videoTime.value=0;videoDuration.value=0;frameNotice.value='';trimStart.value=0;trimEnd.value=0;trimNotice.value='';if(!props.open||!props.output)return;loading.value=true;try{const [res,detail]=await Promise.all([fetch(resourceApi.fileUrl(props.output.id),{headers:{Authorization:`Bearer ${getAccessToken()||''}`}}),resourceApi.get(props.output.id).catch(()=>null)]);if(!res.ok)throw new Error();if(detail)metadata.value={...props.output,...detail};url.value=URL.createObjectURL(await res.blob())}finally{loading.value=false} }
watch(() => [props.open, props.output?.id], () => { if(!props.open){if(url.value)URL.revokeObjectURL(url.value);url.value='';loading.value=false;return} void load() })
function zoom(delta:number,cx?:number,cy?:number){
  const old=scale.value
  scale.value=Math.min(8,Math.max(.25,scale.value+delta))
  if(cx!==undefined&&cy!==undefined&&imgEl.value){
    const rect=imgEl.value.getBoundingClientRect()
    const ratio=scale.value/old
    // 保持鼠标位置在图片上的点不动：
    // x' = x + (cx - rect.left) * (1 - ratio)
    x.value=x.value+(cx-rect.left)*(1-ratio)
    y.value=y.value+(cy-rect.top)*(1-ratio)
  }
}
function reset(){scale.value=1;x.value=0;y.value=0}
function down(e:PointerEvent){if(!isImage.value)return;if(e.pointerType==='touch'&&e.isPrimary===false)return;dragging.value=true;startX=e.clientX;startY=e.clientY;originX=x.value;originY=y.value;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)}
function move(e:PointerEvent){if(dragging.value){x.value=originX+e.clientX-startX;y.value=originY+e.clientY-startY}}
function up(){dragging.value=false}
/** 触摸事件：双指缩放 */
function onTouchStart(e:TouchEvent){if(!isImage.value||e.touches.length!==2)return;e.preventDefault();dragging.value=false;const t1=e.touches[0],t2=e.touches[1];pinchDist=Math.hypot(t2.clientX-t1.clientX,t2.clientY-t1.clientY);pinchScale=scale.value;pinchCenterX=(t1.clientX+t2.clientX)/2;pinchCenterY=(t1.clientY+t2.clientY)/2;pinchOriginX=x.value;pinchOriginY=y.value}
function onTouchMove(e:TouchEvent){if(!isImage.value||e.touches.length!==2)return;e.preventDefault();const t1=e.touches[0],t2=e.touches[1];const dist=Math.hypot(t2.clientX-t1.clientX,t2.clientY-t1.clientY);const ratio=dist/pinchDist;if(ratio>0){scale.value=Math.min(8,Math.max(.25,pinchScale*ratio));// 保持双指中心点不动
  const cx=(t1.clientX+t2.clientX)/2,cy=(t1.clientY+t2.clientY)/2;x.value=pinchOriginX+(cx-pinchCenterX);y.value=pinchOriginY+(cy-pinchCenterY)}}
function onTouchEnd(e:TouchEvent){if(e.touches.length<2){pinchDist=0}}
/** 双击重置/放大 */
let lastTap=0
function onTap(){const now=Date.now();if(now-lastTap<350){if(scale.value>1.5){reset()}else{scale.value=2.5;lastTap=now};lastTap=0}else{lastTap=now;showInfo.value=!showInfo.value}}
function download(){if(!url.value||!props.output)return;const link=document.createElement('a');link.href=url.value;link.download=props.output.filename||`resource-${props.output.id}`;document.body.appendChild(link);link.click();link.remove()}

// ======== 视频帧控制 ========
function onVideoTimeUpdate(){if(videoEl.value&&!videoSeeking.value)videoTime.value=videoEl.value.currentTime}
function onVideoLoaded(){if(videoEl.value)videoDuration.value=videoEl.value.duration||0}
function seekTo(t:number){if(videoEl.value){videoEl.value.currentTime=t;videoTime.value=t}}
function seekStart(){videoSeeking.value=true}
function seekEnd(){videoSeeking.value=false;if(videoEl.value)videoEl.value.currentTime=videoTime.value}
function fmtTime(t:number){const m=Math.floor(t/60);const s=Math.floor(t%60);const ms=Math.floor((t%1)*10);return `${m}:${String(s).padStart(2,'0')}.${ms}`}
async function extractFrame(timestamp:number,label:string){
  if(!props.output||frameExtracting.value)return
  frameExtracting.value=true;frameNotice.value=`正在截取${label}…`
  try{
    const result=await resourceApi.extractFrames(props.output.id,{timestamps:String(timestamp)})
    if(result&&result.length){frameNotice.value=`${label}已保存到素材库：${result[0].filename}`}
    else{frameNotice.value=`${label}截取失败`}
  }catch(e:any){frameNotice.value=`${label}截取失败：${e?.message||''}`}
  finally{frameExtracting.value=false;setTimeout(()=>{frameNotice.value=''},3000)}
}
async function doTrim(){
  if(!props.output||trimProcessing.value)return
  if(trimEnd.value>0&&trimEnd.value<=trimStart.value){trimNotice.value='结束时间必须大于开始时间';return}
  trimProcessing.value=true;trimNotice.value='正在剪辑视频…'
  try{
    const result=await resourceApi.trimVideo(props.output.id,trimStart.value,trimEnd.value||0)
    trimNotice.value=`剪辑完成，已保存：${result.filename}`
  }catch(e:any){trimNotice.value=`剪辑失败：${e?.response?.data?.detail||e?.message||''}`}
  finally{trimProcessing.value=false;setTimeout(()=>{trimNotice.value=''},4000)}
}
onUnmounted(()=>{if(url.value)URL.revokeObjectURL(url.value)})

/** ESC 关闭 */
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.open) emit('close')
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="mv-overlay" @click.self="emit('close')">
      <!-- 顶部栏 -->
      <header class="mv-header">
        <span class="mv-title">{{ output?.filename || '媒体预览' }}</span>
        <div class="mv-actions">
          <V2Button v-if="isImage" variant="ghost" @click="zoom(-.25)">－</V2Button>
          <span v-if="isImage" class="mv-zoom">{{ Math.round(scale*100) }}%</span>
          <V2Button v-if="isImage" variant="ghost" @click="zoom(.25)">＋</V2Button>
          <V2Button v-if="isImage" variant="ghost" @click="reset">重置</V2Button>
          <V2Button v-if="isImage" @click="openActionMenu('image_ops')">图片操作</V2Button>
          <V2Button v-if="isImage" @click="openActionMenu('gen_video')">生成视频</V2Button>
          <V2Button v-if="isImage" @click="openEditor">编辑</V2Button>
          <V2Button variant="primary" @click="download">下载</V2Button>
          <button type="button" class="mv-close" @click="emit('close')">✕</button>
        </div>
      </header>

      <div v-if="loading" class="mv-state">加载中…</div>
      <div v-else-if="url" class="mv-content">
        <!-- 图片：全屏可缩放拖拽 -->
        <div v-if="isImage" class="mv-stage"
          @wheel.prevent="zoom($event.deltaY<0?.2:-.2,$event.clientX,$event.clientY)"
          @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up"
          @touchstart="onTouchStart" @touchmove="onTouchMove" @touchend="onTouchEnd"
          @click="onTap"
        >
          <img ref="imgEl" :src="url" :alt="output?.filename" :style="{transform:`translate(${x}px,${y}px) scale(${scale})`}" draggable="false" />
        </div>
        <!-- 视频 -->
        <div v-else-if="isVideo" class="video-wrapper">
          <video ref="videoEl" :src="url" controls autoplay playsinline class="mv-video" @timeupdate="onVideoTimeUpdate" @loadedmetadata="onVideoLoaded" />
          <div class="video-frame-controls">
            <div class="seek-bar">
              <span class="time-label">{{ fmtTime(videoTime) }}</span>
              <input type="range" min="0" :max="videoDuration||1" step="0.01" v-model.number="videoTime" @pointerdown="seekStart" @pointerup="seekEnd" @change="seekTo(videoTime)" />
              <span class="time-label">{{ fmtTime(videoDuration) }}</span>
            </div>
            <div class="frame-buttons">
              <button @click="seekTo(0);extractFrame(0,'首帧')" :disabled="frameExtracting">📸 首帧</button>
              <button @click="seekTo(Math.max(0,videoDuration-0.1));extractFrame(Math.max(0,videoDuration-0.1),'尾帧')" :disabled="frameExtracting">📸 尾帧</button>
              <button @click="extractFrame(videoTime,`第${fmtTime(videoTime)}秒帧`)" :disabled="frameExtracting">📸 当前帧</button>
            </div>
            <div v-if="frameNotice" class="frame-notice">{{ frameNotice }}</div>
          </div>
          <div class="video-trim-controls">
            <div class="trim-title">视频剪辑</div>
            <div class="trim-row">
              <label><span>开始</span><input type="number" v-model.number="trimStart" min="0" :max="videoDuration" step="0.1" />秒</label>
              <label><span>结束</span><input type="number" v-model.number="trimEnd" min="0" :max="videoDuration" step="0.1" placeholder="0=到结尾" />秒</label>
              <button @click="trimStart=videoTime" title="设为当前时间">⏱开始</button>
              <button @click="trimEnd=videoTime" title="设为当前时间">⏱结束</button>
              <button class="trim-btn" @click="doTrim" :disabled="trimProcessing">{{ trimProcessing?'剪辑中…':'剪辑保存' }}</button>
            </div>
            <div v-if="trimNotice" class="frame-notice">{{ trimNotice }}</div>
          </div>
        </div>
        <!-- 音频 -->
        <div v-else class="mv-audio"><span>♪</span><audio :src="url" controls autoplay /></div>
      </div>
      <div v-else class="mv-state">资源加载失败</div>

      <!-- 底部信息 -->
      <footer v-if="showInfo && url" class="mv-footer">
        <span><small>类型</small><b>{{ isImage?'图片':isVideo?'视频':'音频' }}</b></span>
        <span v-for="item in mediaInfo" :key="item.label"><small>{{ item.label }}</small><b>{{ item.value }}</b></span>
      </footer>

      <!-- 图片操作 / 生成视频 选择菜单 -->
      <div v-if="actionMenuOpen" class="action-menu-overlay" @click.self="actionMenuOpen=false">
        <div class="action-menu">
          <header><h3>{{ actionType==='image_ops'?'图片操作':'生成视频' }}</h3><button @click="actionMenuOpen=false">✕</button></header>
          <div class="action-list">
            <button v-for="item in filteredMenu" :key="item.id" class="action-item" @click="pickGenType(item)">
              <span class="action-name">{{ item.name }}</span>
              <span class="action-code">{{ item.code }}</span>
            </button>
            <p v-if="!filteredMenu.length" class="action-empty">暂无可用的{{ actionType==='image_ops'?'图片操作':'视频生成' }}类型</p>
          </div>
        </div>
      </div>
    </div>
    <ImageEditor :open="editorOpen" :resource="editorResource" @close="editorOpen=false" />
  </Teleport>
</template>

<style scoped>
.mv-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0, 0, 0, 0.92);
  display: flex; flex-direction: column;
}
.mv-header {
  flex-shrink: 0; padding: 10px 16px;
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px;
  background: rgba(0,0,0,0.4);
  border-bottom: 1px solid rgba(255,255,255,0.08);
}
.mv-title { color: #e8edff; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.mv-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; flex-wrap: wrap; }
.mv-actions :deep(.v2-button) { min-height: 32px; padding: 0 10px; font-size: 12px; color: #c8d0ee; background: rgba(130,149,255,0.1); border: 1px solid rgba(130,149,255,0.25); }
.mv-actions :deep(.v2-button.primary) { color: #fff; background: linear-gradient(135deg, #8295ff, #865fee); }
.mv-zoom { min-width: 48px; text-align: center; color: #a0abc8; font-size: 12px; }
.mv-close { width: 34px; height: 34px; font-size: 16px; color: #c8d0ee; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); border-radius: 8px; cursor: pointer; }
.mv-close:hover { background: rgba(255,255,255,0.12); }

.mv-state { flex: 1; display: grid; place-items: center; color: #7a85a8; font-size: 14px; }

.mv-content { flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; overflow: hidden; }
.mv-content:has(.video-wrapper) { overflow-y: auto; align-items: flex-start; padding-top: 20px; }

.mv-stage {
  flex: 1; display: flex; align-items: center; justify-content: center;
  overflow: hidden; touch-action: none; cursor: grab;
  width: 100%; height: 100%;
}
.mv-stage:active { cursor: grabbing; }
.mv-stage img {
  max-width: 90%; max-height: 90%; object-fit: contain;
  transform-origin: 0 0; user-select: none;
  -webkit-user-drag: none; transition: transform 0.05s linear;
}

.mv-video { max-width: 92%; max-height: 60vh; border-radius: 8px; }
.video-wrapper { display: flex; flex-direction: column; align-items: center; gap: 12px; max-height: 100%; padding-bottom: 20px; }
.video-frame-controls { width: min(680px, 92vw); display: flex; flex-direction: column; gap: 8px; }
.seek-bar { display: flex; align-items: center; gap: 8px; }
.seek-bar input[type="range"] { flex: 1; height: 6px; -webkit-appearance: none; appearance: none; background: rgba(255,255,255,0.15); border-radius: 3px; }
.seek-bar input[type="range"]::-webkit-slider-thumb { -webkit-appearance: none; width: 16px; height: 16px; background: #8295ff; border-radius: 50%; cursor: pointer; }
.time-label { color: #a0abc8; font-size: 12px; min-width: 55px; text-align: center; font-variant-numeric: tabular-nums; }
.frame-buttons { display: flex; gap: 6px; flex-wrap: wrap; }
.frame-buttons button { padding: 8px 14px; font-size: 12px; color: #c8d0ee; background: rgba(130,149,255,0.1); border: 1px solid rgba(130,149,255,0.25); border-radius: 8px; cursor: pointer; white-space: nowrap; }
.frame-buttons button:hover:not(:disabled) { background: rgba(130,149,255,0.2); }
.frame-buttons button:disabled { opacity: 0.45; cursor: not-allowed; }
.frame-notice { padding: 6px 12px; font-size: 12px; color: #8295ff; background: rgba(130,149,255,0.08); border-radius: 8px; }
.video-trim-controls { width: min(680px,92vw); display: flex; flex-direction: column; gap: 8px; padding: 10px 14px; background: rgba(255,255,255,0.03); border: 1px solid rgba(130,149,255,0.12); border-radius: 10px; }
.trim-title { font-size: 13px; color: #c8d0ee; font-weight: 600; }
.trim-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.trim-row label { display: flex; align-items: center; gap: 4px; font-size: 11px; color: #a0abc8; }
.trim-row label span { white-space: nowrap; }
.trim-row input[type="number"] { width: 70px; padding: 4px 6px; font-size: 12px; color: #c8d0ee; background: rgba(3,8,17,0.72); border: 1px solid rgba(130,149,255,0.18); border-radius: 6px; }
.trim-row button { padding: 6px 10px; font-size: 11px; color: #c8d0ee; background: rgba(130,149,255,0.08); border: 1px solid rgba(130,149,255,0.18); border-radius: 7px; cursor: pointer; white-space: nowrap; }
.trim-row button:hover:not(:disabled) { background: rgba(130,149,255,0.16); }
.trim-row .trim-btn { color: #fff; background: linear-gradient(135deg, #8295ff, #865fee); border: 0; }
.trim-row .trim-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.mv-audio { display: grid; place-items: center; gap: 20px; color: #7a85a8; font-size: 60px; }
.mv-audio audio { max-width: 400px; width: 90vw; }

.mv-footer {
  flex-shrink: 0; padding: 8px 16px;
  display: flex; flex-wrap: wrap; gap: 16px;
  background: rgba(0,0,0,0.4);
  border-top: 1px solid rgba(255,255,255,0.08);
}
.mv-footer span { display: grid; gap: 2px; }
.mv-footer small { color: #7a85a8; font-size: 10px; }
.mv-footer b { color: #c8d0ee; font-size: 12px; }

/* 操作菜单 */
.action-menu-overlay {
  position: absolute; inset: 0; z-index: 10;
  background: rgba(0,0,0,0.5);
  display: flex; align-items: center; justify-content: center;
}
.action-menu {
  width: min(400px, 90vw); max-height: 70vh;
  background: #1a2238;
  border: 1px solid rgba(130,149,255,0.25);
  border-radius: 14px;
  display: flex; flex-direction: column;
  overflow: hidden;
}
.action-menu header {
  padding: 14px 18px;
  display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid rgba(130,149,255,0.15);
}
.action-menu header h3 { margin: 0; font-size: 15px; color: #e8edff; }
.action-menu header button { color: #7a85a8; background: none; border: 0; font-size: 16px; cursor: pointer; }
.action-list { padding: 8px; overflow-y: auto; display: grid; gap: 4px; }
.action-item {
  padding: 12px 14px;
  display: flex; align-items: center; justify-content: space-between;
  color: #c8d0ee; background: rgba(130,149,255,0.06);
  border: 1px solid rgba(130,149,255,0.12);
  border-radius: 10px; cursor: pointer; transition: 0.15s;
  text-align: left;
}
.action-item:hover { background: rgba(130,149,255,0.16); border-color: rgba(130,149,255,0.3); }
.action-name { font-size: 13px; }
.action-code { font-size: 10px; color: #7a85a8; }
.action-empty { padding: 30px; text-align: center; color: #7a85a8; font-size: 13px; }

@media (max-width: 700px) {
  .mv-header { padding: 8px 10px; flex-wrap: wrap; gap: 6px; }
  .mv-title { font-size: 11px; max-width: 40vw; }
  .mv-actions { gap: 4px; }
  .mv-actions :deep(.v2-button) { min-height: 28px; padding: 0 8px; font-size: 11px; }
  .mv-footer { padding: 6px 10px; gap: 10px; }
}
</style>