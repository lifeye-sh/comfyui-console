<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getAccessToken } from '@/api/client'
import { resourceApi } from '@/api/modules'
import type { ResourceItem } from '@/v2/features/assets/model'

const props = defineProps<{
  open: boolean
  resource: ResourceItem | null
}>()
const emit = defineEmits<{
  close: []
  saved: [resource: ResourceItem]
}>()

const srcUrl = ref('')
const editing = ref(false)
const saving = ref(false)
const error = ref('')

const rotation = ref(0)        // 0/90/180/270
const flipH = ref(false)
const flipV = ref(false)

const containerRef = ref<HTMLDivElement | null>(null)
const imgRef = ref<HTMLImageElement | null>(null)
const stageW = ref(0)
const stageH = ref(0)
const imgNatW = ref(0)
const imgNatH = ref(0)

/** 旋转后图片的有效显示尺寸 */
const rotatedSize = computed(() => {
  if (rotation.value === 90 || rotation.value === 270) {
    return { w: imgNatH.value, h: imgNatW.value }
  }
  return { w: imgNatW.value, h: imgNatH.value }
})

/** 裁剪框（像素坐标，相对于原图） */
const crop = ref({ x: 0, y: 0, w: 0, h: 0 })
const dragMode = ref<'' | 'move' | 'nw' | 'ne' | 'sw' | 'se' | 'n' | 's' | 'e' | 'w'>('')
let dragStart = { mx: 0, my: 0, crop: { x: 0, y: 0, w: 0, h: 0 } }

async function load() {
  srcUrl.value = ''
  rotation.value = 0; flipH.value = false; flipV.value = false
  crop.value = { x: 0, y: 0, w: 0, h: 0 }
  error.value = ''
  editing.value = false
  imgNatW.value = 0; imgNatH.value = 0
  stageW.value = 0; stageH.value = 0
  imgScale.value = 1; imgX.value = 0; imgY.value = 0
  currentAspect.value = '自由'
  if (!props.open || !props.resource || props.resource.media_type !== 'image') return
  try {
    const r = await fetch(resourceApi.fileUrl(props.resource.id), { headers: { Authorization: `Bearer ${getAccessToken() || ''}` } })
    if (!r.ok) throw new Error('HTTP ' + r.status)
    srcUrl.value = URL.createObjectURL(await r.blob())
  } catch (e: any) {
    error.value = e?.message || '图片加载失败'
  }
}

function onImageLoad(e: Event) {
  const img = e.target as HTMLImageElement
  if (!img.naturalWidth) return
  imgNatW.value = img.naturalWidth
  imgNatH.value = img.naturalHeight
  crop.value = { x: 0, y: 0, w: imgNatW.value, h: imgNatH.value }
  updateStageSize()
}

watch(() => [props.open, props.resource?.id], () => { if (props.open) load() })
watch(rotation, () => updateStageSize())
watch(() => containerRef.value, updateStageSize)

function updateStageSize() {
  const el = containerRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const padding = 32
  const maxW = Math.max(rect.width - padding, 100)
  const maxH = Math.max(rect.height - padding, 100)
  const ratio = rotatedSize.value.w / rotatedSize.value.h
  if (ratio >= 1) { stageW.value = maxW; stageH.value = maxW / ratio }
  else { stageH.value = maxH; stageW.value = maxH * ratio }
}

function rotate90() { rotation.value = (rotation.value + 90) % 360 }
function flip(horizontal: boolean) { if (horizontal) flipH.value = !flipH.value; else flipV.value = !flipV.value }
function resetEdit() {
  rotation.value = 0; flipH.value = false; flipV.value = false
  crop.value = { x: 0, y: 0, w: imgNatW.value, h: imgNatH.value }
  imgScale.value = 1; imgX.value = 0; imgY.value = 0
  currentAspect.value = '自由'
}

const aspectPresets: Array<{ label: string; ratio: number }> = [
  { label: '自由', ratio: 0 },
  { label: '1:1', ratio: 1 },
  { label: '4:3', ratio: 4 / 3 },
  { label: '3:2', ratio: 3 / 2 },
  { label: '16:9', ratio: 16 / 9 },
  { label: '9:16', ratio: 9 / 16 },
  { label: '2:3', ratio: 2 / 3 },
  { label: '3:4', ratio: 3 / 4 },
]
const currentAspect = ref('自由')
function applyAspect(preset: { label: string; ratio: number }) {
  if (!imgNatW.value) return
  if (preset.ratio === 0) { resetEdit(); return }
  const srcRatio = preset.ratio
  const imgRatio = imgNatW.value / imgNatH.value
  let cw = imgNatW.value, ch = imgNatH.value
  if (srcRatio >= imgRatio) { ch = Math.round(cw / srcRatio) } else { cw = Math.round(ch * srcRatio) }
  cw = Math.min(cw, imgNatW.value); ch = Math.min(ch, imgNatH.value)
  const cx = Math.round((imgNatW.value - cw) / 2)
  const cy = Math.round((imgNatH.value - ch) / 2)
  crop.value = { x: cx, y: cy, w: cw, h: ch }
}

/** 图片缩放与平移 */
const imgScale = ref(1)
const imgX = ref(0)
const imgY = ref(0)
const imgDragging = ref(false)
let imgDragStart = { mx: 0, my: 0, ox: 0, oy: 0 }

function zoomImage(delta: number, cx?: number, cy?: number) {
  const stage = containerRef.value?.querySelector('.img-stage') as HTMLElement | null
  if (!stage) return
  const rect = stage.getBoundingClientRect()
  const ccx = cx ?? rect.width / 2
  const ccy = cy ?? rect.height / 2
  const old = imgScale.value
  const next = Math.max(0.25, Math.min(8, old * (1 + delta)))
  if (next === old) return
  const ratio = next / old
  imgX.value = ccx - (ccx - imgX.value) * ratio
  imgY.value = ccy - (ccy - imgY.value) * ratio
  imgScale.value = next
}

function onStageWheel(event: WheelEvent) {
  const stage = event.currentTarget as HTMLElement | null
  if (!stage) return
  const rect = stage.getBoundingClientRect()
  zoomImage(
    event.deltaY < 0 ? 0.15 : -0.15,
    event.clientX - rect.left,
    event.clientY - rect.top,
  )
}
function startImgDrag(e: PointerEvent) {
  const target = e.target as HTMLElement
  if (target.closest('.crop-overlay, .crop-handle, button, a, input, select, textarea')) return
  imgDragging.value = true
  imgDragStart = { mx: e.clientX, my: e.clientY, ox: imgX.value, oy: imgY.value }
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
}
function moveImgDrag(e: PointerEvent) {
  if (!imgDragging.value) return
  imgX.value = imgDragStart.ox + (e.clientX - imgDragStart.mx)
  imgY.value = imgDragStart.oy + (e.clientY - imgDragStart.my)
}
function endImgDrag() { imgDragging.value = false }
function resetZoom() { imgScale.value = 1; imgX.value = 0; imgY.value = 0 }

/**
 * 把鼠标坐标转回原图像素坐标。
 * CSS transform = rotate(R) scale(fx, fy)
 * 逆变换：先反旋转，再反翻转。
 */
function eventToImagePx(e: MouseEvent | PointerEvent): { x: number; y: number } {
  const img = imgRef.value
  if (!img) return { x: 0, y: 0 }
  const rect = img.getBoundingClientRect()
  if (rect.width <= 0 || rect.height <= 0) return { x: 0, y: 0 }
  // 归一化到 [0, 1]（在旋转后的视觉空间）
  let nx = (e.clientX - rect.left) / rect.width
  let ny = (e.clientY - rect.top) / rect.height
  // 反旋转（CSS 先 scale 后 rotate，逆变换先反 rotate）
  const rot = rotation.value
  if (rot === 90) { const t = nx; nx = ny; ny = 1 - t }
  else if (rot === 180) { nx = 1 - nx; ny = 1 - ny }
  else if (rot === 270) { const t = nx; nx = 1 - ny; ny = t }
  // 反翻转（scale 是最先应用的，逆变换最后撤）
  if (flipH.value) nx = 1 - nx
  if (flipV.value) ny = 1 - ny
  return { x: nx * imgNatW.value, y: ny * imgNatH.value }
}

/** 裁剪框 CSS 位置（基于原图坐标系百分比，img-wrap 内坐标） */
const cropStageStyle = computed(() => {
  if (!imgNatW.value) return { left: '0%', top: '0%', width: '0%', height: '0%' }
  return {
    left: `${(crop.value.x / imgNatW.value) * 100}%`,
    top: `${(crop.value.y / imgNatH.value) * 100}%`,
    width: `${(crop.value.w / imgNatW.value) * 100}%`,
    height: `${(crop.value.h / imgNatH.value) * 100}%`,
  }
})

function startDrag(e: PointerEvent, mode: typeof dragMode.value) {
  const { x: ix, y: iy } = eventToImagePx(e)
  dragMode.value = mode
  dragStart = { mx: ix, my: iy, crop: { ...crop.value } }
  ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
  e.preventDefault()
}

function onDrag(e: PointerEvent) {
  if (!dragMode.value) return
  const { x: ix, y: iy } = eventToImagePx(e)
  const dx = ix - dragStart.mx, dy = iy - dragStart.my
  const ox = dragStart.crop.x, oy = dragStart.crop.y, ow = dragStart.crop.w, oh = dragStart.crop.h
  let x = ox, y = oy, w = ow, h = oh
  switch (dragMode.value) {
    case 'move': x = clamp(ox + dx, 0, imgNatW.value - ow); y = clamp(oy + dy, 0, imgNatH.value - oh); break
    case 'nw': x = clamp(ix, 0, ox + ow - 10); y = clamp(iy, 0, oy + oh - 10); w = ox + ow - x; h = oy + oh - y; break
    case 'ne': y = clamp(iy, 0, oy + oh - 10); w = clamp(ix - ox, 10, imgNatW.value - ox); h = oy + oh - y; break
    case 'sw': x = clamp(ix, 0, ox + ow - 10); w = ox + ow - x; h = clamp(iy - oy, 10, imgNatH.value - oy); break
    case 'se': w = clamp(ix - ox, 10, imgNatW.value - ox); h = clamp(iy - oy, 10, imgNatH.value - oy); break
    case 'n': y = clamp(iy, 0, oy + oh - 10); h = oy + oh - y; break
    case 's': h = clamp(iy - oy, 10, imgNatH.value - oy); break
    case 'e': w = clamp(ix - ox, 10, imgNatW.value - ox); break
    case 'w': x = clamp(ix, 0, ox + ow - 10); w = ox + ow - x; break
  }
  crop.value = { x, y, w, h }
}

function endDrag() { dragMode.value = '' }
function clamp(v: number, lo: number, hi: number) { return Math.max(lo, Math.min(hi, v)) }

/** 导出：裁剪原图 → 旋转/翻转裁剪结果 */
async function exportEditedPng(): Promise<Blob> {
  // 1. 从原图裁剪 crop 区域（原图坐标系，无旋转）
  const croppedCanvas = document.createElement('canvas')
  croppedCanvas.width = Math.round(crop.value.w)
  croppedCanvas.height = Math.round(crop.value.h)
  const croppedCtx = croppedCanvas.getContext('2d')!
  croppedCtx.drawImage(
    imgRef.value!,
    Math.round(crop.value.x), Math.round(crop.value.y), Math.round(crop.value.w), Math.round(crop.value.h),
    0, 0, croppedCanvas.width, croppedCanvas.height,
  )

  // 2. 创建输出画布，应用旋转和翻转（与 CSS transform 顺序一致：先 scale 后 rotate）
  const outW = croppedCanvas.width
  const outH = croppedCanvas.height
  const swap = rotation.value === 90 || rotation.value === 270
  const outCanvas = document.createElement('canvas')
  outCanvas.width = swap ? outH : outW
  outCanvas.height = swap ? outW : outH
  const outCtx = outCanvas.getContext('2d')!
  outCtx.translate(outCanvas.width / 2, outCanvas.height / 2)
  outCtx.rotate((rotation.value * Math.PI) / 180)
  outCtx.scale(flipH.value ? -1 : 1, flipV.value ? -1 : 1)
  outCtx.drawImage(croppedCanvas, -outW / 2, -outH / 2)

  return new Promise((resolve, reject) => {
    outCanvas.toBlob((b) => b ? resolve(b) : reject(new Error('PNG 编码失败')), 'image/png')
  })
}

async function save() {
  if (!props.resource) return
  saving.value = true
  try {
    const blob = await exportEditedPng()
    const file = new File([blob], `${props.resource.filename.replace(/\.[^.]+$/, '')}_edited_${Date.now()}.png`, { type: 'image/png' })
    const saved = await resourceApi.upload(file, 'image', 'output') as ResourceItem
    emit('saved', saved)
    emit('close')
  } catch (e: any) {
    error.value = `保存失败：${typeof e === 'string' ? e : (e?.message || '')}`
  } finally {
    saving.value = false
  }
}

onBeforeUnmount(() => {
  if (srcUrl.value) URL.revokeObjectURL(srcUrl.value)
})
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="ie-overlay" @click.self="emit('close')">
      <div class="ie-panel">
        <header>
          <div>
            <b>{{ resource?.filename || '图片编辑' }}</b>
            <small v-if="imgNatW">原始 {{ imgNatW }} × {{ imgNatH }}px · 输出 {{ Math.round(crop.w) }} × {{ Math.round(crop.h) }}px</small>
          </div>
          <button class="close-btn" @click="emit('close')">✕</button>
        </header>

        <div v-if="error" class="ie-error">{{ error }}</div>

        <div class="ie-body">
          <!-- 工具栏 -->
          <aside class="ie-tools">
            <div class="tool-section">
              <label>旋转</label>
              <div class="tool-buttons">
                <button @click="rotate90" title="旋转 90°">↺ 旋转</button>
                <button @click="flip(true)" :class="{ active: flipH }">⇋ 水平翻转</button>
                <button @click="flip(false)" :class="{ active: flipV }">⇅ 垂直翻转</button>
              </div>
            </div>
            <div class="tool-section">
              <label>比例</label>
              <div class="aspect-grid">
                <button v-for="preset in aspectPresets" :key="preset.label"
                  :class="{ active: currentAspect === preset.label }"
                  @click="currentAspect = preset.label; applyAspect(preset)">{{ preset.label }}</button>
              </div>
            </div>
            <div class="tool-section">
              <label>视图缩放</label>
              <div class="tool-buttons tool-buttons-row">
                <button @click="zoomImage(-0.2)">－</button>
                <span class="zoom-label">{{ Math.round(imgScale * 100) }}%</span>
                <button @click="zoomImage(0.2)">＋</button>
              </div>
              <button class="reset-btn" @click="resetZoom">重置视图</button>
            </div>
            <div class="tool-section">
              <label>裁剪</label>
              <div class="crop-tip">点击比例按钮快速裁剪，或拖动裁剪框边缘/四角调整大小</div>
              <button class="tool-btn-wide" @click="editing = !editing">{{ editing ? '完成裁剪' : '开始裁剪' }}</button>
            </div>
            <div class="tool-section">
              <button class="primary-btn" :disabled="saving" @click="save">{{ saving ? '保存中…' : '💾 保存为新素材' }}</button>
              <small class="hint">编辑后的图片另存为新素材，不修改原图</small>
            </div>
          </aside>

          <!-- 编辑画布 -->
          <div ref="containerRef" class="ie-stage">
            <div class="img-stage" :style="{ width: stageW + 'px', height: stageH + 'px' }"
              @wheel.prevent="onStageWheel"
              @pointerdown="startImgDrag" @pointermove="moveImgDrag" @pointerup="endImgDrag" @pointercancel="endImgDrag">
              <!-- img-wrap 应用旋转+翻转+视图缩放/平移 -->
              <div class="img-wrap" :style="{ width: rotatedSize.w * imgScale + 'px', height: rotatedSize.h * imgScale + 'px', transform: `translate(${imgX}px, ${imgY}px) rotate(${rotation}deg) scale(${flipH ? -1 : 1}, ${flipV ? -1 : 1})` }">
                <div class="img-content" :style="{ width: imgNatW * imgScale + 'px', height: imgNatH * imgScale + 'px' }">
                  <img v-if="srcUrl" ref="imgRef" :src="srcUrl" :alt="resource?.filename" :width="imgNatW" :height="imgNatH" :style="{ width: '100%', height: '100%' }" draggable="false" @load="onImageLoad" />
                  <div v-if="imgNatW && editing" class="crop-overlay" :style="cropStageStyle"
                    @pointerdown="startDrag($event, 'move')" @pointermove="onDrag" @pointerup="endDrag" @pointercancel="endDrag">
                    <i class="handle nw" @pointerdown.stop="startDrag($event, 'nw')" @pointermove.stop="onDrag" @pointerup.stop="endDrag" @pointercancel="endDrag"></i>
                    <i class="handle ne" @pointerdown.stop="startDrag($event, 'ne')" @pointermove.stop="onDrag" @pointerup.stop="endDrag" @pointercancel="endDrag"></i>
                    <i class="handle sw" @pointerdown.stop="startDrag($event, 'sw')" @pointermove.stop="onDrag" @pointerup.stop="endDrag" @pointercancel="endDrag"></i>
                    <i class="handle se" @pointerdown.stop="startDrag($event, 'se')" @pointermove.stop="onDrag" @pointerup.stop="endDrag" @pointercancel="endDrag"></i>
                    <i class="handle n" @pointerdown.stop="startDrag($event, 'n')" @pointermove.stop="onDrag" @pointerup.stop="endDrag" @pointercancel="endDrag"></i>
                    <i class="handle s" @pointerdown.stop="startDrag($event, 's')" @pointermove.stop="onDrag" @pointerup.stop="endDrag" @pointercancel="endDrag"></i>
                    <i class="handle e" @pointerdown.stop="startDrag($event, 'e')" @pointermove.stop="onDrag" @pointerup.stop="endDrag" @pointercancel="endDrag"></i>
                    <i class="handle w" @pointerdown.stop="startDrag($event, 'w')" @pointermove.stop="onDrag" @pointerup.stop="endDrag" @pointercancel="endDrag"></i>
                  </div>
                </div>
              </div>
            </div>
            <div v-if="!srcUrl && !error" class="ie-loading">加载图片中…</div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.ie-overlay { position: fixed; inset: 0; z-index: 9999; background: rgba(0,0,0,.85); display: flex; align-items: center; justify-content: center; padding: 12px; }
.ie-panel { width: min(1200px, 100%); height: 92vh; background: #0d1424; border: 1px solid rgba(130,149,255,.25); border-radius: 16px; display: flex; flex-direction: column; overflow: hidden; }
.ie-panel > header { padding: 12px 18px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--v2-border); flex-shrink: 0; }
.ie-panel > header b { display: block; color: #e8edff; font-size: 14px; }
.ie-panel > header small { color: #7a85a8; font-size: 11px; }
.close-btn { width: 34px; height: 34px; font-size: 16px; color: #c8d0ee; background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.12); border-radius: 8px; cursor: pointer; }
.ie-error { padding: 10px 16px; color: #ffdce1; background: rgba(255,127,145,.1); font-size: 13px; }
.ie-body { flex: 1; display: flex; min-height: 0; min-width: 0; }
.ie-tools { width: 220px; flex-shrink: 0; padding: 16px; display: flex; flex-direction: column; gap: 16px; border-right: 1px solid var(--v2-border); background: rgba(3,12,25,.4); overflow-y: auto; }
.tool-section { display: flex; flex-direction: column; gap: 8px; }
.tool-section label { font-size: 12px; color: #a0abc8; }
.tool-buttons { display: flex; flex-direction: column; gap: 6px; }
.tool-buttons-row { flex-direction: row; align-items: center; }
.tool-buttons-row .zoom-label { flex: 1; text-align: center; font-size: 12px; color: #c8d0ee; }
.tool-buttons button { padding: 8px 12px; font-size: 12px; color: #c8d0ee; background: rgba(130,149,255,.08); border: 1px solid rgba(130,149,255,.18); border-radius: 8px; cursor: pointer; text-align: left; }
.tool-buttons button:hover { background: rgba(130,149,255,.16); }
.tool-buttons button.active { color: #fff; background: rgba(130,149,255,.35); }
.aspect-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 5px; }
.aspect-grid button { padding: 6px 4px; font-size: 11px; color: #c8d0ee; background: rgba(130,149,255,.08); border: 1px solid rgba(130,149,255,.18); border-radius: 7px; cursor: pointer; }
.aspect-grid button:hover { background: rgba(130,149,255,.16); }
.aspect-grid button.active { color: #fff; background: rgba(130,149,255,.35); border-color: rgba(130,149,255,.6); }
.crop-tip { font-size: 11px; color: #7a85a8; padding: 6px 8px; background: rgba(255,255,255,.03); border-radius: 6px; }
.reset-btn { padding: 6px 10px; font-size: 11px; color: #7a85a8; background: transparent; border: 1px solid rgba(130,149,255,.15); border-radius: 7px; cursor: pointer; }
.tool-btn-wide { padding: 8px 12px; font-size: 12px; color: #c8d0ee; background: rgba(130,149,255,.1); border: 1px solid rgba(130,149,255,.2); border-radius: 8px; cursor: pointer; text-align: center; }
.tool-btn-wide:hover { background: rgba(130,149,255,.2); }
.reset-btn:hover { color: #c8d0ee; }
.primary-btn { padding: 10px; font-size: 13px; color: #fff; background: linear-gradient(135deg, #8295ff, #865fee); border: 0; border-radius: 10px; cursor: pointer; }
.primary-btn:hover:not(:disabled) { filter: brightness(1.1); }
.primary-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.hint { display: block; font-size: 11px; color: #7a85a8; }
.ie-stage { flex: 1; display: flex; align-items: center; justify-content: center; overflow: hidden; padding: 16px; position: relative; background: repeating-conic-gradient(rgba(255,255,255,.02) 0% 25%, transparent 0% 50%) 50% / 24px 24px; min-height: 0; }
.img-stage { position: relative; display: flex; align-items: center; justify-content: center; }
.img-stage img { display: block; }
.img-wrap { position: relative; transform-origin: center; flex-shrink: 0; display: flex; align-items: center; justify-content: center; }
.img-content { position: relative; flex-shrink: 0; }
.img-content img { display: block; }
.crop-overlay { position: absolute; border: 2px solid #8295ff; box-shadow: 0 0 0 9999px rgba(0,0,0,.45); cursor: move; touch-action: none; }
.crop-overlay .handle { position: absolute; width: 16px; height: 16px; background: #8295ff; border: 2px solid #fff; border-radius: 50%; }
.crop-overlay .handle.nw { top: -8px; left: -8px; cursor: nwse-resize; }
.crop-overlay .handle.ne { top: -8px; right: -8px; cursor: nesw-resize; }
.crop-overlay .handle.sw { bottom: -8px; left: -8px; cursor: nesw-resize; }
.crop-overlay .handle.se { bottom: -8px; right: -8px; cursor: nwse-resize; }
.crop-overlay .handle.n { top: -8px; left: 50%; margin-left: -8px; cursor: ns-resize; }
.crop-overlay .handle.s { bottom: -8px; left: 50%; margin-left: -8px; cursor: ns-resize; }
.crop-overlay .handle.e { right: -8px; top: 50%; margin-top: -8px; cursor: ew-resize; }
.crop-overlay .handle.w { left: -8px; top: 50%; margin-top: -8px; cursor: ew-resize; }
.ie-loading { color: #7a85a8; font-size: 14px; }

@media (max-width: 760px) {
  .ie-body { flex-direction: column; }
  .ie-tools { width: 100%; max-height: 220px; flex-direction: row; overflow-x: auto; }
  .tool-section { min-width: 180px; }
}
</style>
