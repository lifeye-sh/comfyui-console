<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getAccessToken } from '@/api/client'
import { resourceApi, genTypeApi } from '@/api/modules'
import ImageEditor from './ImageEditor.vue'
import CopyButton from './CopyButton.vue'
import type { ResourceItem } from '@/v2/features/assets/model'
import type { TaskOutput, GenerationTypeItem } from '@/v2/features/tasks/model'
import { flattenGenerationMenu } from '@/v2/features/tasks/model'
import V2Button from './V2Button.vue'
import { formatDuration } from '@/v2/features/assets/model'
const props = withDefaults(defineProps<{ open: boolean; output: TaskOutput | null; outputs?: TaskOutput[] }>(),{outputs:()=>[]})
const emit = defineEmits<{ close: [] }>()
const router = useRouter()
const activeOutput = ref<TaskOutput|null>(null)
const viewMode = ref<'single'|'grid'|'compare'>('single')
const compareLeftId = ref<number|null>(null)
const compareRightId = ref<number|null>(null)
const multiUrls = ref<Record<number,string>>({})
const multiLoading = ref(false)
const url = ref(''); const loading = ref(false); const scale = ref(1); const x = ref(0); const y = ref(0); const dragging = ref(false); const showInfo = ref(true); const metadata = ref<TaskOutput|null>(null)
const imgEl = ref<HTMLImageElement | null>(null)
const videoEl = ref<HTMLVideoElement | null>(null)
const videoTime = ref(0); const videoDuration = ref(0); const videoSeeking = ref(false); const frameExtracting = ref(false); const frameNotice = ref('')
const trimStart = ref(0); const trimEnd = ref(0); const trimProcessing = ref(false); const trimNotice = ref('')
let startX=0,startY=0,originX=0,originY=0
/** 双指缩放状态 */
let pinchDist=0, pinchScale=1, pinchCenterX=0, pinchCenterY=0, pinchOriginX=0, pinchOriginY=0
function outputIsImage(output:TaskOutput|null|undefined){return output?.media_type==='image'||!!output?.mime?.startsWith('image/')}
const imageOutputs = computed(()=>{
  const images=props.outputs.filter(outputIsImage)
  if(outputIsImage(activeOutput.value)&&activeOutput.value&&!images.some(item=>item.id===activeOutput.value?.id))return [activeOutput.value,...images]
  return images
})
const activeImageIndex = computed(()=>imageOutputs.value.findIndex(item=>item.id===activeOutput.value?.id))
const compareLeft = computed(()=>imageOutputs.value.find(item=>item.id===compareLeftId.value)||imageOutputs.value[0]||null)
const compareRight = computed(()=>imageOutputs.value.find(item=>item.id===compareRightId.value)||imageOutputs.value[1]||imageOutputs.value[0]||null)
const isImage = computed(() => outputIsImage(activeOutput.value))
const isVideo = computed(() => activeOutput.value?.media_type === 'video' || (!!activeOutput.value?.mime && activeOutput.value.mime.startsWith('video/')))
const isAudio = computed(() => activeOutput.value?.media_type === 'audio' || (!!activeOutput.value?.mime && activeOutput.value.mime.startsWith('audio/')))
const isText = computed(() => activeOutput.value?.media_type === 'text' || (!!activeOutput.value?.mime && activeOutput.value.mime.startsWith('text/')))
const textContent = ref('')
const textLoading = ref(false)
async function loadTextContent() {
  if (!isText.value || !activeOutput.value) return
  textLoading.value = true
  textContent.value = ''
  try {
    const r = await fetch(resourceApi.fileUrl(activeOutput.value.id), { headers: { Authorization: `Bearer ${getAccessToken() || ''}` } })
    if (r.ok) textContent.value = await r.text()
  } catch { /* ignore */ }
  finally { textLoading.value = false }
}
watch(() => [props.open, activeOutput.value?.id, isText.value], () => { if (props.open && isText.value) loadTextContent() })
const mediaInfo = computed(() => { const output=metadata.value||activeOutput.value;if(!output)return[];const info:Array<{label:string;value:string}>=[];if(output.width&&output.height)info.push({label:output.media_type==='image'?'图片尺寸':'视频尺寸',value:`${output.width} × ${output.height}`});if((output.media_type==='video'||output.media_type==='audio')&&output.duration!=null)info.push({label:'时长',value:formatDuration(output.duration)});return info })

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
  if (!activeOutput.value) return
  actionMenuOpen.value = false
  emit('close')
  router.push({ path: `/v2/generate/${item.code}`, query: { resource_id: String(activeOutput.value.id) } })
}
async function openEditor() {
  if (!activeOutput.value) return
  editorResource.value = {
    id: activeOutput.value.id,
    owner_id: null,
    folder_id: null,
    media_type: 'image',
    direction: '',
    filename: activeOutput.value.filename || `image_${activeOutput.value.id}`,
    mime: activeOutput.value.mime || 'image/*',
    size: 0,
    width: activeOutput.value.width || null,
    height: activeOutput.value.height || null,
    duration: null,
    created_at: '',
  }
  editorOpen.value = true
}

async function load() { if(url.value) URL.revokeObjectURL(url.value); url.value='';metadata.value=activeOutput.value;scale.value=1;x.value=0;y.value=0;loading.value=false;videoTime.value=0;videoDuration.value=0;frameNotice.value='';trimStart.value=0;trimEnd.value=0;trimNotice.value='';if(!props.open||!activeOutput.value)return;const output=activeOutput.value;loading.value=true;try{const [res,detail]=await Promise.all([fetch(resourceApi.fileUrl(output.id),{headers:{Authorization:`Bearer ${getAccessToken()||''}`}}),resourceApi.get(output.id).catch(()=>null)]);if(!res.ok)throw new Error();if(detail)metadata.value={...output,...detail};url.value=URL.createObjectURL(await res.blob())}finally{loading.value=false} }
function clearMultiUrls(){Object.values(multiUrls.value).forEach(URL.revokeObjectURL);multiUrls.value={}}
async function loadMultiUrls(){
  if(!props.open||imageOutputs.value.length<2)return
  multiLoading.value=true;let cursor=0;const images=[...imageOutputs.value]
  async function worker(){while(cursor<images.length){const output=images[cursor++];if(multiUrls.value[output.id])continue;try{const response=await fetch(resourceApi.fileUrl(output.id),{headers:{Authorization:`Bearer ${getAccessToken()||''}`}});if(!response.ok)continue;const objectUrl=URL.createObjectURL(await response.blob());if(!props.open){URL.revokeObjectURL(objectUrl);return}multiUrls.value={...multiUrls.value,[output.id]:objectUrl}}catch{}}}
  await Promise.all(Array.from({length:Math.min(4,images.length)},worker));multiLoading.value=false
}
function selectImage(output:TaskOutput){activeOutput.value=output;viewMode.value='single'}
function stepImage(step:number){if(imageOutputs.value.length<2)return;const index=activeImageIndex.value<0?0:activeImageIndex.value;activeOutput.value=imageOutputs.value[(index+step+imageOutputs.value.length)%imageOutputs.value.length]}
function setViewMode(mode:'single'|'grid'|'compare'){viewMode.value=mode;if(mode!=='single')void loadMultiUrls()}
watch(() => [props.open,props.output?.id],([open])=>{
  if(open){activeOutput.value=props.output;viewMode.value='single';compareLeftId.value=imageOutputs.value[0]?.id??null;compareRightId.value=imageOutputs.value[1]?.id??imageOutputs.value[0]?.id??null}
  else{activeOutput.value=null;clearMultiUrls();multiLoading.value=false}
},{immediate:true})
watch(() => [props.open,activeOutput.value?.id], () => { if(!props.open){if(url.value)URL.revokeObjectURL(url.value);url.value='';loading.value=false;return} void load() })
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
function download(){if(!url.value||!activeOutput.value)return;const link=document.createElement('a');link.href=url.value;link.download=activeOutput.value.filename||`resource-${activeOutput.value.id}`;document.body.appendChild(link);link.click();link.remove()}

// ======== 视频帧控制 ========
function onVideoTimeUpdate(){if(videoEl.value&&!videoSeeking.value)videoTime.value=videoEl.value.currentTime}
function onVideoLoaded(){if(videoEl.value)videoDuration.value=videoEl.value.duration||0}
function seekTo(t:number){if(videoEl.value){videoEl.value.currentTime=t;videoTime.value=t}}
function seekStart(){videoSeeking.value=true}
function seekEnd(){videoSeeking.value=false;if(videoEl.value)videoEl.value.currentTime=videoTime.value}
function fmtTime(t:number){const m=Math.floor(t/60);const s=Math.floor(t%60);const ms=Math.floor((t%1)*10);return `${m}:${String(s).padStart(2,'0')}.${ms}`}
async function extractFrame(timestamp:number,label:string){
  if(!activeOutput.value||frameExtracting.value)return
  frameExtracting.value=true;frameNotice.value=`正在截取${label}…`
  try{
    const result=await resourceApi.extractFrames(activeOutput.value.id,{timestamps:String(timestamp)})
    if(result&&result.length){frameNotice.value=`${label}已保存到素材库：${result[0].filename}`}
    else{frameNotice.value=`${label}截取失败`}
  }catch(e:any){frameNotice.value=`${label}截取失败：${e?.message||''}`}
  finally{frameExtracting.value=false;setTimeout(()=>{frameNotice.value=''},3000)}
}
async function doTrim(){
  if(!activeOutput.value||trimProcessing.value)return
  if(trimEnd.value>0&&trimEnd.value<=trimStart.value){trimNotice.value='结束时间必须大于开始时间';return}
  trimProcessing.value=true;trimNotice.value='正在剪辑视频…'
  try{
    const result=await resourceApi.trimVideo(activeOutput.value.id,trimStart.value,trimEnd.value||0)
    trimNotice.value=`剪辑完成，已保存：${result.filename}`
  }catch(e:any){trimNotice.value=`剪辑失败：${e?.response?.data?.detail||e?.message||''}`}
  finally{trimProcessing.value=false;setTimeout(()=>{trimNotice.value=''},4000)}
}
onUnmounted(()=>{if(url.value)URL.revokeObjectURL(url.value);clearMultiUrls()})

/** ESC 关闭 */
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.open) emit('close')
  if(props.open&&viewMode.value==='single'&&imageOutputs.value.length>1&&e.key==='ArrowLeft'){e.preventDefault();stepImage(-1)}
  if(props.open&&viewMode.value==='single'&&imageOutputs.value.length>1&&e.key==='ArrowRight'){e.preventDefault();stepImage(1)}
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="mv-overlay" @click.self="emit('close')">
      <!-- 顶部栏 -->
      <header class="mv-header">
        <span class="mv-title">{{ activeOutput?.filename || '媒体预览' }}<i v-if="imageOutputs.length>1">{{ activeImageIndex+1 }} / {{ imageOutputs.length }}</i></span>
        <div class="mv-actions">
          <div v-if="isImage&&imageOutputs.length>1" class="mv-view-modes">
            <button type="button" :class="{active:viewMode==='single'}" @click="setViewMode('single')">顺序查看</button>
            <button type="button" :class="{active:viewMode==='grid'}" @click="setViewMode('grid')">全部显示</button>
            <button type="button" :class="{active:viewMode==='compare'}" @click="setViewMode('compare')">对比显示</button>
          </div>
          <V2Button v-if="isImage" variant="ghost" class="mobile-hidden" @click="zoom(-.25)">－</V2Button>
          <span v-if="isImage" class="mv-zoom mobile-hidden">{{ Math.round(scale*100) }}%</span>
          <V2Button v-if="isImage" variant="ghost" class="mobile-hidden" @click="zoom(.25)" aria-label="添加"><StudioIcon name="plus"/></V2Button>
          <V2Button v-if="isImage" variant="ghost" class="mobile-hidden" @click="reset">重置</V2Button>
          <V2Button v-if="isImage" @click="openActionMenu('image_ops')">图片操作</V2Button>
          <V2Button v-if="isImage" @click="openActionMenu('gen_video')">生成视频</V2Button>
          <V2Button v-if="isImage" @click="openEditor">编辑</V2Button>
          <V2Button variant="primary" @click="download">下载</V2Button>
          <button type="button" class="mv-close" @click="emit('close')" aria-label="关闭"><StudioIcon name="close"/></button>
        </div>
      </header>

      <div v-if="isImage&&imageOutputs.length>1&&viewMode==='grid'" class="mv-grid-view">
        <button v-for="(item,index) in imageOutputs" :key="item.id" type="button" @click="selectImage(item)">
          <img v-if="multiUrls[item.id]||item.thumbUrl" :src="multiUrls[item.id]||item.thumbUrl" :alt="item.filename"/>
          <span v-else>{{ multiLoading?'加载中…':'图片加载失败' }}</span>
          <b><i>{{ index+1 }}</i>{{ item.filename }}</b>
        </button>
      </div>
      <div v-else-if="isImage&&imageOutputs.length>1&&viewMode==='compare'" class="mv-compare-view">
        <div class="compare-selectors">
          <label>左侧<select v-model.number="compareLeftId"><option v-for="(item,index) in imageOutputs" :key="item.id" :value="item.id">{{ index+1 }} · {{ item.filename }}</option></select></label>
          <label>右侧<select v-model.number="compareRightId"><option v-for="(item,index) in imageOutputs" :key="item.id" :value="item.id">{{ index+1 }} · {{ item.filename }}</option></select></label>
        </div>
        <div class="compare-panels">
          <figure v-for="(item,side) in [compareLeft,compareRight]" :key="`${side}-${item?.id}`">
            <img v-if="item&&(multiUrls[item.id]||item.thumbUrl)" :src="multiUrls[item.id]||item.thumbUrl" :alt="item.filename"/>
            <div v-else class="compare-loading">{{ multiLoading?'加载中…':'图片加载失败' }}</div>
            <figcaption v-if="item"><span>{{ side===0?'左侧':'右侧' }}</span>{{ item.filename }}</figcaption>
          </figure>
        </div>
      </div>
      <div v-else-if="loading" class="mv-state">加载中…</div>
      <div v-else-if="url" class="mv-content">
        <!-- 图片：全屏可缩放拖拽 -->
        <div v-if="isImage" class="mv-stage"
          @wheel.prevent="zoom($event.deltaY<0?.2:-.2,$event.clientX,$event.clientY)"
          @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up"
          @touchstart="onTouchStart" @touchmove="onTouchMove" @touchend="onTouchEnd"
          @click="onTap"
        >
          <button v-if="imageOutputs.length>1" type="button" class="mv-image-nav previous" aria-label="上一张" @click.stop="stepImage(-1)"><StudioIcon name="back"/></button>
          <img ref="imgEl" :src="url" :alt="activeOutput?.filename" :style="{transform:`translate(${x}px,${y}px) scale(${scale})`}" draggable="false" />
          <button v-if="imageOutputs.length>1" type="button" class="mv-image-nav next" aria-label="下一张" @click.stop="stepImage(1)"><StudioIcon name="chevron"/></button>
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
              <button @click="seekTo(0);extractFrame(0,'首帧')" :disabled="frameExtracting"><StudioIcon name="camera"/>  首帧</button>
              <button @click="seekTo(Math.max(0,videoDuration-0.1));extractFrame(Math.max(0,videoDuration-0.1),'尾帧')" :disabled="frameExtracting"><StudioIcon name="camera"/>  尾帧</button>
              <button @click="extractFrame(videoTime,`第${fmtTime(videoTime)}秒帧`)" :disabled="frameExtracting"><StudioIcon name="camera"/>  当前帧</button>
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
        <div v-else-if="isText" class="mv-text"><div class="mv-text-header"><StudioIcon name="file"/>  {{ activeOutput?.filename }} <CopyButton v-if="textContent" :text="textContent" /></div><pre v-if="textLoading" class="mv-text-loading">加载中…</pre><pre v-else-if="textContent" class="mv-text-content">{{ textContent }}</pre><div v-else class="mv-text-empty">无内容</div></div>
        <div v-else class="mv-audio"><span><StudioIcon name="audio"/></span><audio :src="url" controls autoplay /></div>
      </div>
      <div v-else class="mv-state">资源加载失败</div>

      <!-- 底部信息 -->
      <footer v-if="showInfo && url && viewMode==='single'" class="mv-footer">
        <span><small>类型</small><b>{{ isImage?'图片':isVideo?'视频':isAudio?'音频':isText?'文本':'文件' }}</b></span>
        <span v-for="item in mediaInfo" :key="item.label"><small>{{ item.label }}</small><b>{{ item.value }}</b></span>
      </footer>

      <!-- 图片操作 / 生成视频 选择菜单 -->
      <div v-if="actionMenuOpen" class="action-menu-overlay" @click.self="actionMenuOpen=false">
        <div class="action-menu">
          <header><h3>{{ actionType==='image_ops'?'图片操作':'生成视频' }}</h3><button @click="actionMenuOpen=false" aria-label="关闭"><StudioIcon name="close"/></button></header>
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
  background: var(--ws-surface);
  display: flex; flex-direction: column;
}
.mv-header {
  flex-shrink: 0; padding: 10px 16px;
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px;
  background: rgba(0,0,0,0.4);
  border-bottom: 1px solid color-mix(in srgb, var(--ws-border) 8%, transparent);
}
.mv-title { color: var(--ws-text); font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }.mv-title i{margin-left:10px;color:var(--ws-text-muted);font-size:11px;font-style:normal}
.mv-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; flex-wrap: wrap; }
.mv-view-modes{display:flex;padding:2px;background:color-mix(in srgb, var(--ws-surface) 6%, transparent);border:1px solid color-mix(in srgb, var(--ws-border) 12%, transparent);border-radius:9px}.mv-view-modes button{height:28px;padding:0 10px;color:var(--ws-text-muted);background:transparent;border:0;border-radius:6px;font-size:11px;cursor:pointer}.mv-view-modes button:hover{color:var(--ws-text);background:color-mix(in srgb, var(--ws-selected) 14%, transparent)}.mv-view-modes button.active{color:var(--ws-primary);background:color-mix(in srgb, var(--ws-selected) 32%, transparent)}
.mv-actions :deep(.v2-button) { min-height: 32px; padding: 0 10px; font-size: 12px; color: var(--ws-text); background: color-mix(in srgb, var(--ws-surface-soft) 10%, transparent); border: 1px solid color-mix(in srgb, var(--ws-border) 25%, transparent); }
.mv-actions :deep(.v2-button.primary) { color: var(--ws-text); background:var(--ws-selected); }
.mv-zoom { min-width: 48px; text-align: center; color: var(--ws-text-muted); font-size: 12px; }
.mv-close { width: 34px; height: 34px; font-size: 16px; color: var(--ws-text); background: color-mix(in srgb, var(--ws-surface) 6%, transparent); border: 1px solid color-mix(in srgb, var(--ws-border) 12%, transparent); border-radius: 8px; cursor: pointer; }
.mv-close:hover { background: color-mix(in srgb, var(--ws-selected) 12%, transparent); }

.mv-state { flex: 1; display: grid; place-items: center; color: var(--ws-text-muted); font-size: 14px; }

.mv-content { flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; overflow: hidden; }
.mv-content:has(.video-wrapper) { overflow-y: auto; align-items: flex-start; padding-top: 20px; }

.mv-stage {
  position:relative; flex: 1; display: flex; align-items: center; justify-content: center;
  overflow: hidden; touch-action: none; cursor: grab;
  width: 100%; height: 100%;
}
.mv-image-nav{position:absolute;z-index:2;top:50%;width:48px;height:72px;transform:translateY(-50%);color:var(--ws-text);background:rgba(12,18,32,.55);border:1px solid color-mix(in srgb, var(--ws-border) 14%, transparent);border-radius:14px;font-size:44px;line-height:1;cursor:pointer;backdrop-filter:blur(10px)}.mv-image-nav:hover{background:color-mix(in srgb, var(--ws-selected) 52%, transparent)}.mv-image-nav.previous{left:16px}.mv-image-nav.next{right:16px}

.mv-grid-view{flex:1;min-height:0;overflow:auto;padding:18px;display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));grid-auto-rows:minmax(220px,1fr);gap:14px;align-content:start}.mv-grid-view button{min-width:0;min-height:220px;padding:10px;display:grid;grid-template-rows:minmax(0,1fr) auto;gap:8px;color:var(--ws-text);background:color-mix(in srgb, var(--ws-surface) 4%, transparent);border:1px solid color-mix(in srgb, var(--ws-border) 18%, transparent);border-radius:13px;cursor:pointer;overflow:hidden}.mv-grid-view button:hover{background:color-mix(in srgb, var(--ws-selected) 10%, transparent);border-color:color-mix(in srgb, var(--ws-border) 50%, transparent)}.mv-grid-view img{width:100%;height:100%;min-height:0;object-fit:contain;background:rgba(0,0,0,.18);border-radius:8px}.mv-grid-view button>span{display:grid;place-items:center;color:var(--ws-text-muted)}.mv-grid-view b{display:flex;align-items:center;gap:8px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:left;font-size:12px}.mv-grid-view b i{flex:none;width:22px;height:22px;display:grid;place-items:center;color:var(--ws-text);background:color-mix(in srgb, var(--ws-surface-soft) 40%, transparent);border-radius:50%;font-size:10px;font-style:normal}
.mv-compare-view{flex:1;min-height:0;display:flex;flex-direction:column;overflow:hidden}.compare-selectors{flex:none;padding:10px 16px;display:grid;grid-template-columns:1fr 1fr;gap:12px;background:color-mix(in srgb, var(--ws-surface) 2%, transparent);border-bottom:1px solid color-mix(in srgb, var(--ws-border) 8%, transparent)}.compare-selectors label{display:flex;align-items:center;gap:8px;color:var(--ws-text-muted);font-size:11px}.compare-selectors select{min-width:0;flex:1;height:34px;padding:0 10px;color:var(--ws-text);background:var(--ws-surface-soft);border:1px solid color-mix(in srgb, var(--ws-border) 22%, transparent);border-radius:8px}.compare-panels{flex:1;min-height:0;display:grid;grid-template-columns:1fr 1fr;gap:1px;background:color-mix(in srgb, var(--ws-surface) 10%, transparent)}.compare-panels figure{position:relative;min-width:0;min-height:0;margin:0;display:grid;place-items:center;overflow:hidden;background:var(--ws-surface)}.compare-panels img{position:absolute;inset:0;display:block;width:100%;height:100%;max-width:100%;max-height:100%;object-fit:contain;object-position:center}.compare-panels figcaption{position:absolute;left:12px;right:12px;bottom:12px;padding:8px 10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ws-text);background:rgba(10,14,25,.66);border:1px solid color-mix(in srgb, var(--ws-border) 12%, transparent);border-radius:8px;font-size:11px;backdrop-filter:blur(10px)}.compare-panels figcaption span{margin-right:8px;color:var(--ws-text);font-weight:700}.compare-loading{color:var(--ws-text-muted);font-size:13px}
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
.seek-bar input[type="range"] { flex: 1; height: 6px; -webkit-appearance: none; appearance: none; background: color-mix(in srgb, var(--ws-surface) 15%, transparent); border-radius: 3px; }
.seek-bar input[type="range"]::-webkit-slider-thumb { -webkit-appearance: none; width: 16px; height: 16px; background: var(--ws-surface-soft); border-radius: 50%; cursor: pointer; }
.time-label { color: var(--ws-text-muted); font-size: 12px; min-width: 55px; text-align: center; font-variant-numeric: tabular-nums; }
.frame-buttons { display: flex; gap: 6px; flex-wrap: wrap; }
.frame-buttons button { padding: 8px 14px; font-size: 12px; color: var(--ws-text); background: color-mix(in srgb, var(--ws-surface-soft) 10%, transparent); border: 1px solid color-mix(in srgb, var(--ws-border) 25%, transparent); border-radius: 8px; cursor: pointer; white-space: nowrap; }
.frame-buttons button:hover:not(:disabled) { background: color-mix(in srgb, var(--ws-selected) 20%, transparent); }
.frame-buttons button:disabled { opacity: 0.45; cursor: not-allowed; }
.frame-notice { padding: 6px 12px; font-size: 12px; color: var(--ws-text-muted); background: color-mix(in srgb, var(--ws-surface-soft) 8%, transparent); border-radius: 8px; }
.video-trim-controls { width: min(680px,92vw); display: flex; flex-direction: column; gap: 8px; padding: 10px 14px; background: color-mix(in srgb, var(--ws-surface) 3%, transparent); border: 1px solid color-mix(in srgb, var(--ws-border) 12%, transparent); border-radius: 10px; }
.trim-title { font-size: 13px; color: var(--ws-text); font-weight: 600; }
.trim-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.trim-row label { display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--ws-text-muted); }
.trim-row label span { white-space: nowrap; }
.trim-row input[type="number"] { width: 70px; padding: 4px 6px; font-size: 12px; color: var(--ws-text); background: rgba(3,8,17,0.72); border: 1px solid color-mix(in srgb, var(--ws-border) 18%, transparent); border-radius: 6px; }
.trim-row button { padding: 6px 10px; font-size: 11px; color: var(--ws-text); background: color-mix(in srgb, var(--ws-surface-soft) 8%, transparent); border: 1px solid color-mix(in srgb, var(--ws-border) 18%, transparent); border-radius: 7px; cursor: pointer; white-space: nowrap; }
.trim-row button:hover:not(:disabled) { background: color-mix(in srgb, var(--ws-selected) 16%, transparent); }
.trim-row .trim-btn { color: var(--ws-text); background:var(--ws-surface-soft); border: 0; }
.trim-row .trim-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.mv-audio { display: grid; place-items: center; gap: 20px; color: var(--ws-text-muted); font-size: 60px; }
.mv-audio audio { max-width: 400px; width: 90vw; }
.mv-text { width: min(820px, 92vw); max-height: 70vh; background: var(--ws-surface); border: 1px solid color-mix(in srgb, var(--ws-border) 20%, transparent); border-radius: 14px; display: flex; flex-direction: column; overflow: hidden; }
.mv-text-header { padding: 12px 16px; display: flex; align-items: center; justify-content: space-between; gap: 12px; color: var(--ws-text); font-size: 13px; border-bottom: 1px solid color-mix(in srgb, var(--ws-border) 15%, transparent); }
.mv-text-loading, .mv-text-empty { padding: 40px; text-align: center; color: var(--ws-text-muted); }
.mv-text-content { margin: 0; padding: 18px; white-space: pre-wrap; word-break: break-word; color: var(--ws-text); font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; line-height: 1.7; overflow-y: auto; max-height: calc(70vh - 56px); }

.mv-footer {
  flex-shrink: 0; padding: 8px 16px;
  display: flex; flex-wrap: wrap; gap: 16px;
  background: rgba(0,0,0,0.4);
  border-top: 1px solid color-mix(in srgb, var(--ws-border) 8%, transparent);
}
.mv-footer span { display: grid; gap: 2px; }
.mv-footer small { color: var(--ws-text-muted); font-size: 10px; }
.mv-footer b { color: var(--ws-text); font-size: 12px; }

/* 操作菜单 */
.action-menu-overlay {
  position: absolute; inset: 0; z-index: 10;
  background: rgba(0,0,0,0.5);
  display: flex; align-items: center; justify-content: center;
}
.action-menu {
  width: min(400px, 90vw); max-height: 70vh;
  background: var(--ws-surface-soft);
  border: 1px solid color-mix(in srgb, var(--ws-border) 25%, transparent);
  border-radius: 14px;
  display: flex; flex-direction: column;
  overflow: hidden;
}
.action-menu header {
  padding: 14px 18px;
  display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid color-mix(in srgb, var(--ws-border) 15%, transparent);
}
.action-menu header h3 { margin: 0; font-size: 15px; color: var(--ws-text); }
.action-menu header button { color: var(--ws-text-muted); background: none; border: 0; font-size: 16px; cursor: pointer; }
.action-list { padding: 8px; overflow-y: auto; display: grid; gap: 4px; }
.action-item {
  padding: 12px 14px;
  display: flex; align-items: center; justify-content: space-between;
  color: var(--ws-text); background: color-mix(in srgb, var(--ws-surface-soft) 6%, transparent);
  border: 1px solid color-mix(in srgb, var(--ws-border) 12%, transparent);
  border-radius: 10px; cursor: pointer; transition: 0.15s;
  text-align: left;
}
.action-item:hover { background: color-mix(in srgb, var(--ws-selected) 16%, transparent); border-color: color-mix(in srgb, var(--ws-border) 30%, transparent); }
.action-name { font-size: 13px; }
.action-code { font-size: 10px; color: var(--ws-text-muted); }
.action-empty { padding: 30px; text-align: center; color: var(--ws-text-muted); font-size: 13px; }

@media (max-width: 700px) {
  .mv-header { padding: 8px 10px; flex-wrap: wrap; gap: 6px; }
  .mv-title { font-size: 11px; max-width: 40vw; }
  .mv-actions { gap: 4px; }
  .mv-actions :deep(.v2-button) { min-height: 28px; padding: 0 8px; font-size: 11px; }
  /* 移动端隐藏缩放按钮和重置，保留图片操作/生成视频/编辑/下载/关闭 */
  .mv-actions :deep(.mobile-hidden) { display: none; }
  .mv-close { width: 32px; height: 32px; font-size: 16px; }
  .mv-footer { padding: 6px 10px; gap: 10px; }
  .mv-view-modes{order:10;width:100%;display:grid;grid-template-columns:repeat(3,1fr)}
  .mv-grid-view{padding:10px;grid-template-columns:1fr 1fr;grid-auto-rows:180px;gap:8px}.mv-image-nav{width:38px;height:58px;font-size:34px}.mv-image-nav.previous{left:5px}.mv-image-nav.next{right:5px}
  .compare-selectors{padding:8px;grid-template-columns:1fr}.compare-panels{grid-template-columns:1fr;grid-template-rows:1fr 1fr}
}
</style>
