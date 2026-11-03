<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { getAccessToken } from '@/api/client'
import { resourceApi } from '@/api/modules'
import { formatSize, type ResourceItem } from './model'

const props=withDefaults(defineProps<{open:boolean;images:ResourceItem[];startId?:number|null;folders?:Array<{id:number;name:string;depth:number}>;folderId?:number|null;loading?:boolean}>(),{folders:()=>[],folderId:null,loading:false})
const emit=defineEmits<{close:[];folderChange:[folderId:number|null]}>()
const root=ref<HTMLElement|null>(null)
const imageFrame=ref<HTMLElement|null>(null)
const filmstrip=ref<HTMLElement|null>(null)
const currentIndex=ref(0)
const imageUrl=ref('')
const thumbUrls=ref<Record<number,string>>({})
const imageLoading=ref(false)
const imageError=ref('')
const playing=ref(false)
const intervalSeconds=ref(5)
const fullscreen=ref(false)
const zoom=ref(1)
const panX=ref(0)
const panY=ref(0)
const dragging=ref(false)
const controlsVisible=ref(true)
const current=computed(()=>props.images[currentIndex.value]||null)
const imageTransform=computed(()=>`translate(${panX.value}px, ${panY.value}px) scale(${zoom.value})`)
let imageRequest=0
let thumbRequest=0
let slideshowTimer:number|null=null
let controlsTimer:number|null=null
let controlsHovered=false
let dragOrigin={x:0,y:0,panX:0,panY:0}
let previousBodyOverflow=''

async function fetchObjectUrl(url:string){
  const token=getAccessToken()
  const response=await fetch(url,{headers:token?{Authorization:`Bearer ${token}`}:{}})
  if(!response.ok)throw new Error(`HTTP ${response.status}`)
  return URL.createObjectURL(await response.blob())
}
function revokeImage(){if(imageUrl.value){URL.revokeObjectURL(imageUrl.value);imageUrl.value=''}}
function clearThumbs(){
  thumbRequest++
  Object.values(thumbUrls.value).forEach(URL.revokeObjectURL)
  thumbUrls.value={}
}
async function loadCurrent(){
  const item=current.value
  const request=++imageRequest
  revokeImage();imageError.value=''
  if(!item)return
  imageLoading.value=true
  try{
    const url=await fetchObjectUrl(resourceApi.fileUrl(item.id))
    if(request!==imageRequest||!props.open){URL.revokeObjectURL(url);return}
    resetView()
    imageUrl.value=url
  }catch{if(request===imageRequest)imageError.value='原图加载失败'}
  finally{if(request===imageRequest)imageLoading.value=false}
}
async function loadThumbs(){
  clearThumbs()
  const request=thumbRequest
  let cursor=0
  async function worker(){
    while(cursor<props.images.length&&request===thumbRequest&&props.open){
      const item=props.images[cursor++]
      try{
        const url=await fetchObjectUrl(resourceApi.thumbUrl(item.id))
        if(request!==thumbRequest||!props.open){URL.revokeObjectURL(url);return}
        thumbUrls.value={...thumbUrls.value,[item.id]:url}
      }catch{}
    }
  }
  await Promise.all(Array.from({length:Math.min(6,props.images.length)},worker))
}
function scrollActiveThumb(){
  nextTick(()=>{
    const strip=filmstrip.value
    const thumb=document.getElementById(`gallery-thumb-${current.value?.id}`)
    if(!strip||!thumb)return
    const stripRect=strip.getBoundingClientRect()
    const thumbRect=thumb.getBoundingClientRect()
    const left=strip.scrollLeft+(thumbRect.left-stripRect.left)-(stripRect.width-thumbRect.width)/2
    strip.scrollTo({left:Math.max(0,left),behavior:'smooth'})
  })
}
function selectIndex(index:number,resetTimer=true){
  if(!props.images.length)return
  resetView()
  currentIndex.value=(index+props.images.length)%props.images.length
  if(resetTimer&&playing.value)restartSlideshow()
}
function move(step:number,resetTimer=true){selectIndex(currentIndex.value+step,resetTimer)}
function stopSlideshow(){if(slideshowTimer!==null){window.clearInterval(slideshowTimer);slideshowTimer=null}}
function restartSlideshow(){
  stopSlideshow()
  if(playing.value&&props.open&&props.images.length>1)slideshowTimer=window.setInterval(()=>move(1,false),intervalSeconds.value*1000)
}
function togglePlay(){playing.value=!playing.value}
function resetView(){dragging.value=false;zoom.value=1;panX.value=0;panY.value=0}
function setZoom(value:number,clientX?:number,clientY?:number){
  const previous=zoom.value
  const next=Math.min(8,Math.max(.25,Math.round(value*100)/100))
  if(next===previous)return
  if(clientX!==undefined&&clientY!==undefined&&imageFrame.value){
    const rect=imageFrame.value.getBoundingClientRect()
    const pointerX=clientX-(rect.left+rect.width/2)
    const pointerY=clientY-(rect.top+rect.height/2)
    const ratio=next/previous
    panX.value=pointerX-(pointerX-panX.value)*ratio
    panY.value=pointerY-(pointerY-panY.value)*ratio
  }
  zoom.value=next
  revealControls()
}
function zoomBy(factor:number){setZoom(zoom.value*factor)}
function onWheel(event:WheelEvent){
  setZoom(zoom.value*(event.deltaY<0?1.15:1/1.15),event.clientX,event.clientY)
}
function onPointerDown(event:PointerEvent){
  if(event.button!==0||!imageUrl.value)return
  dragging.value=true
  dragOrigin={x:event.clientX,y:event.clientY,panX:panX.value,panY:panY.value}
  imageFrame.value?.setPointerCapture(event.pointerId)
  revealControls()
}
function onPointerMove(event:PointerEvent){
  revealControls()
  if(!dragging.value)return
  panX.value=dragOrigin.panX+event.clientX-dragOrigin.x
  panY.value=dragOrigin.panY+event.clientY-dragOrigin.y
}
function onPointerUp(event:PointerEvent){
  if(!dragging.value)return
  dragging.value=false
  if(imageFrame.value?.hasPointerCapture(event.pointerId))imageFrame.value.releasePointerCapture(event.pointerId)
  scheduleControlsHide()
}
function clearControlsTimer(){if(controlsTimer!==null){window.clearTimeout(controlsTimer);controlsTimer=null}}
function scheduleControlsHide(){
  clearControlsTimer()
  if(!props.open||controlsHovered||dragging.value)return
  controlsTimer=window.setTimeout(()=>{controlsVisible.value=false},3000)
}
function revealControls(){controlsVisible.value=true;scheduleControlsHide()}
function holdControls(){controlsHovered=true;clearControlsTimer();controlsVisible.value=true}
function releaseControls(){controlsHovered=false;revealControls()}
async function toggleFullscreen(){
  try{
    if(document.fullscreenElement)await document.exitFullscreen()
    else await root.value?.requestFullscreen()
  }catch{}
}
function close(){emit('close')}
function changeFolder(event:Event){
  const value=(event.target as HTMLSelectElement).value
  emit('folderChange',value===''?null:Number(value))
}
function onKeydown(event:KeyboardEvent){
  if(!props.open)return
  if(event.key==='Escape'&&!document.fullscreenElement){event.preventDefault();close();return}
  if(event.key==='ArrowLeft'){event.preventDefault();move(-1);return}
  if(event.key==='ArrowRight'){event.preventDefault();move(1);return}
  if(event.key==='0'){event.preventDefault();resetView();revealControls();return}
  if(event.key==='+'||event.key==='='){event.preventDefault();zoomBy(1.2);return}
  if(event.key==='-'){event.preventDefault();zoomBy(1/1.2);return}
  if(event.code==='Space'&&(event.target as HTMLElement)?.tagName!=='SELECT'){event.preventDefault();togglePlay()}
}
function onFullscreenChange(){fullscreen.value=!!document.fullscreenElement}

watch(()=>props.open,(open)=>{
  if(open){
    previousBodyOverflow=document.body.style.overflow
    document.body.style.overflow='hidden'
    const startIndex=props.images.findIndex(item=>item.id===props.startId)
    currentIndex.value=startIndex>=0?startIndex:0
    playing.value=false
    resetView();revealControls()
    void loadCurrent();void loadThumbs();scrollActiveThumb()
  }else{
    playing.value=false;stopSlideshow();clearControlsTimer();imageRequest++;revokeImage();clearThumbs();resetView()
    document.body.style.overflow=previousBodyOverflow
    if(document.fullscreenElement&&root.value?.contains(document.fullscreenElement))void document.exitFullscreen()
  }
})
watch(()=>current.value?.id,()=>{if(props.open){resetView();void loadCurrent();scrollActiveThumb()}})
watch(()=>props.images.map(item=>item.id).join(','),()=>{
  if(!props.open)return
  const startIndex=props.images.findIndex(item=>item.id===props.startId)
  currentIndex.value=startIndex>=0?startIndex:0
  resetView();void loadCurrent();void loadThumbs();scrollActiveThumb()
})
watch([playing,intervalSeconds],restartSlideshow)
onMounted(()=>{window.addEventListener('keydown',onKeydown);document.addEventListener('fullscreenchange',onFullscreenChange)})
onUnmounted(()=>{
  window.removeEventListener('keydown',onKeydown);document.removeEventListener('fullscreenchange',onFullscreenChange)
  stopSlideshow();clearControlsTimer();imageRequest++;revokeImage();clearThumbs();document.body.style.overflow=previousBodyOverflow
})
</script>

<template>
  <Teleport to="body">
    <Transition name="gallery-fade">
      <section v-if="open" ref="root" class="image-gallery" :class="{'controls-hidden':!controlsVisible,'is-dragging':dragging}" role="dialog" aria-modal="true" aria-label="图片浏览" @pointermove="onPointerMove" @pointerup="onPointerUp" @pointercancel="onPointerUp">
        <header class="gallery-header" @pointerenter="holdControls" @pointerleave="releaseControls">
          <div class="gallery-title">
            <strong>{{ current?.filename||'图片浏览' }}</strong>
            <span>{{ images.length?currentIndex+1:0 }} / {{ images.length }}</span>
          </div>
          <div class="gallery-controls">
            <div class="folder-control">
              <span>浏览目录</span>
              <select :value="folderId??''" aria-label="选择图片浏览目录" @change="changeFolder">
                <option value="">全部目录</option>
                <option v-for="folder in folders" :key="folder.id" :value="folder.id">{{ '　'.repeat(folder.depth) }}{{ folder.name }}</option>
              </select>
            </div>
            <label>间隔
              <select v-model.number="intervalSeconds" aria-label="幻灯片播放间隔">
                <option :value="2">2 秒</option><option :value="3">3 秒</option><option :value="5">5 秒</option><option :value="8">8 秒</option><option :value="10">10 秒</option>
              </select>
            </label>
            <div class="zoom-controls" aria-label="图片缩放">
              <button type="button" aria-label="缩小" @click="zoomBy(1/1.2)"><StudioIcon name="minus"/></button>
              <button type="button" class="zoom-value" title="恢复适应屏幕" @click="resetView">{{ Math.round(zoom*100) }}%</button>
              <button type="button" aria-label="放大" @click="zoomBy(1.2)"><StudioIcon name="plus"/></button>
            </div>
            <button type="button" class="play-button" :disabled="images.length<2" @click="togglePlay">{{ playing?'暂停':'幻灯片播放' }}</button>
            <button type="button" @click="toggleFullscreen">{{ fullscreen?'退出全屏':'全屏' }}</button>
            <button type="button" class="close-button" aria-label="关闭图片浏览" @click="close"><StudioIcon name="close"/></button>
          </div>
        </header>
        <main class="gallery-stage">
          <button type="button" class="nav-button previous" :disabled="images.length<2" aria-label="上一张" @click.stop="move(-1)"><StudioIcon name="back"/></button>
          <div ref="imageFrame" class="image-frame" @wheel.prevent="onWheel" @pointerdown="onPointerDown" @dblclick.stop="resetView">
            <div v-if="imageUrl" :key="current?.id" class="image-canvas" :style="{transform:imageTransform}">
              <img :src="imageUrl" :alt="current?.filename||'图片'" draggable="false"/>
            </div>
            <div v-if="loading" class="image-status"><span class="spinner"></span>正在读取目录图片…</div>
            <div v-else-if="imageLoading" class="image-status"><span class="spinner"></span>正在加载原图…</div>
            <div v-else-if="imageError" class="image-status error">{{ imageError }}</div>
            <div v-else-if="!images.length" class="image-status">当前目录没有图片，请从上方选择其他目录</div>
          </div>
          <button type="button" class="nav-button next" :disabled="images.length<2" aria-label="下一张" @click.stop="move(1)"><StudioIcon name="chevron"/></button>
        </main>
        <footer class="gallery-footer" @pointerenter="holdControls" @pointerleave="releaseControls">
          <div class="image-meta">
            <span v-if="current?.width&&current?.height">{{ current.width }} × {{ current.height }}</span>
            <span v-if="current">{{ formatSize(current.size) }}</span>
            <span class="shortcut-hint">滚轮缩放 · 拖动移动 · 双击或 0 复位</span>
          </div>
          <div ref="filmstrip" class="filmstrip" aria-label="图片缩略图导航">
            <button v-for="(image,index) in images" :id="`gallery-thumb-${image.id}`" :key="image.id" type="button" :class="{active:index===currentIndex}" :title="image.filename" @click="selectIndex(index)">
              <img v-if="thumbUrls[image.id]" :src="thumbUrls[image.id]" :alt="image.filename" loading="lazy"/><span v-else>{{ index+1 }}</span>
            </button>
          </div>
        </footer>
      </section>
    </Transition>
  </Teleport>
</template>

<style scoped>
.image-gallery{position:fixed;inset:0;z-index:10060;width:100vw;height:100vh;height:100dvh;overflow:hidden;color:var(--ws-text);background:var(--ws-surface);backdrop-filter:blur(20px)}
.gallery-header{position:absolute;z-index:5;top:0;left:0;right:0;display:flex;align-items:center;justify-content:space-between;gap:18px;padding:14px 18px;border-bottom:1px solid color-mix(in srgb, var(--ws-border) 12%, transparent);background:rgba(12,15,27,.52);box-shadow:0 8px 24px rgba(0,0,0,.16);backdrop-filter:blur(16px);transition:opacity .25s ease,transform .25s ease}
.gallery-title{min-width:0;display:flex;align-items:baseline;gap:12px}.gallery-title strong{max-width:min(52vw,720px);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.gallery-title span,.image-meta{color:color-mix(in srgb, var(--ws-text) 62%, transparent);font-size:12px}
.gallery-controls{display:flex;align-items:center;gap:8px}.gallery-controls label,.folder-control{display:flex;align-items:center;gap:6px;color:color-mix(in srgb, var(--ws-text) 72%, transparent);font-size:12px}.gallery-controls select,.gallery-controls button{height:36px;padding:0 12px;color:var(--ws-text);background:color-mix(in srgb, var(--ws-surface) 9%, transparent);border:1px solid color-mix(in srgb, var(--ws-border) 18%, transparent);border-radius:9px}.gallery-controls select{outline:none}.gallery-controls option{color:var(--ws-text)}.folder-control select{width:190px;max-width:22vw}.gallery-controls button{cursor:pointer}.gallery-controls button:hover:not(:disabled){background:color-mix(in srgb, var(--ws-selected) 28%, transparent);border-color:color-mix(in srgb, var(--ws-border) 65%, transparent)}.gallery-controls button:disabled,.nav-button:disabled{opacity:.35;cursor:not-allowed}.gallery-controls .play-button{min-width:100px;color:var(--ws-text);background:color-mix(in srgb, var(--ws-surface-soft) 30%, transparent);border-color:color-mix(in srgb, var(--ws-border) 55%, transparent)}.gallery-controls .close-button{width:38px;padding:0;font-size:24px;line-height:1}.zoom-controls{display:flex}.gallery-controls .zoom-controls button{min-width:36px;padding:0;border-radius:0;border-right:0}.gallery-controls .zoom-controls button:first-child{border-radius:9px 0 0 9px}.gallery-controls .zoom-controls button:last-child{border-right:1px solid color-mix(in srgb, var(--ws-border) 18%, transparent);border-radius:0 9px 9px 0}.gallery-controls .zoom-controls .zoom-value{min-width:58px;font-size:11px}
.gallery-stage{position:absolute;inset:0;min-width:0;min-height:0;overflow:hidden}.image-frame{position:absolute;inset:0;min-width:0;min-height:0;overflow:hidden;cursor:grab;touch-action:none}.is-dragging .image-frame{cursor:grabbing}.image-canvas{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;transform-origin:center center;transition:transform .12s ease;will-change:transform}.image-canvas img{display:block;width:auto;height:auto;max-width:100%;max-height:100%;object-fit:contain;object-position:center;user-select:none;pointer-events:none}.is-dragging .image-canvas{transition:none}.image-status{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:10px;color:color-mix(in srgb, var(--ws-text) 68%, transparent);font-size:13px}.image-status.error{color:var(--ws-danger)}.spinner{width:18px;height:18px;border:2px solid color-mix(in srgb, var(--ws-border) 18%, transparent);border-top-color:#8295ff;border-radius:50%;animation:gallery-spin .8s linear infinite}
.nav-button{position:absolute;z-index:4;top:50%;width:48px;height:72px;transform:translateY(-50%);color:var(--ws-text);background:rgba(18,23,40,.46);border:1px solid color-mix(in srgb, var(--ws-border) 15%, transparent);border-radius:14px;font-size:46px;line-height:1;cursor:pointer;backdrop-filter:blur(12px);transition:opacity .25s ease,transform .25s ease,background .2s ease}.nav-button:hover:not(:disabled){background:color-mix(in srgb, var(--ws-selected) 55%, transparent)}.nav-button.previous{left:16px}.nav-button.next{right:16px}
.gallery-footer{position:absolute;z-index:5;left:0;right:0;bottom:0;padding:9px 14px 13px;border-top:1px solid color-mix(in srgb, var(--ws-border) 12%, transparent);background:rgba(12,15,27,.5);box-shadow:0 -8px 24px rgba(0,0,0,.16);backdrop-filter:blur(16px);transition:opacity .25s ease,transform .25s ease}.image-meta{display:flex;justify-content:center;gap:14px;margin-bottom:8px}.shortcut-hint{margin-left:auto}.filmstrip{display:flex;gap:7px;overflow-x:auto;padding:2px 2px 5px;scrollbar-width:thin}.filmstrip button{flex:0 0 72px;height:54px;padding:2px;display:grid;place-items:center;overflow:hidden;color:color-mix(in srgb, var(--ws-text) 65%, transparent);background:color-mix(in srgb, var(--ws-surface) 7%, transparent);border:2px solid transparent;border-radius:8px;cursor:pointer}.filmstrip button.active{border-color:var(--ws-border);background:color-mix(in srgb, var(--ws-selected) 25%, transparent);box-shadow:0 0 0 2px rgba(130,149,255,.15)}.filmstrip img{width:100%;height:100%;object-fit:cover;border-radius:5px}
.controls-hidden .gallery-header,.controls-hidden .gallery-footer{opacity:0;pointer-events:none}.controls-hidden .nav-button{opacity:0;pointer-events:none}
.gallery-fade-enter-active,.gallery-fade-leave-active{transition:opacity .2s ease}.gallery-fade-enter-from,.gallery-fade-leave-to{opacity:0}@keyframes gallery-spin{to{transform:rotate(360deg)}}
@media(max-width:1100px){.gallery-title{display:none}.gallery-controls{width:100%;justify-content:flex-end}.folder-control span{display:none}.folder-control select{max-width:210px}}
@media(max-width:760px){.gallery-header{padding:10px;gap:6px}.gallery-controls{width:100%;justify-content:flex-end;gap:5px}.gallery-controls label{display:none}.folder-control{min-width:0;flex:1}.folder-control select{width:100%;max-width:none;min-width:80px}.gallery-controls button{padding:0 8px}.gallery-controls .play-button{min-width:auto}.gallery-controls .zoom-controls button{padding:0;min-width:32px}.gallery-controls .zoom-controls .zoom-value{min-width:48px}.nav-button{width:38px;height:60px;font-size:36px}.nav-button.previous{left:5px}.nav-button.next{right:5px}.shortcut-hint{display:none}.filmstrip button{flex-basis:62px;height:48px}}
</style>
