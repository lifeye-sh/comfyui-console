<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getAccessToken } from '@/api/client'
import V2Button from '@/v2/components/V2Button.vue'
import { useMaskCanvas, type Tool } from '@/v2/composables/useMaskCanvas'

const props = defineProps<{
  open: boolean
  imageUrl: string
  /** 已有遮罩图片 URL（带 alpha 通道的 PNG），传入则加载已有遮罩 */
  existingMaskUrl?: string
}>()
const emit = defineEmits<{
  save: [blob: Blob]
  cancel: []
}>()

const {
  imgCanvas, maskCanvas, previewCanvas,
  tool, brush, maskColor, maskOpacity,
  canUndo, canRedo, view, panning, moveMode, zoomPercent,
  loadImage, loadExistingMask, clearMask, fitToContainer, resetView,
  zoomAt, startPan, doPan, stopPan,
  startDrawing, drawTo, stopDrawing,
  onTouchStart, onTouchMove, onTouchEnd,
  undo, redo, exportMaskedPng, hasMask, clearPreview,
} = useMaskCanvas()

const loading = ref(true)
const saving = ref(false)
const errorMsg = ref('')
const imageLoaded = ref(false)
/** 空格键是否按下（用于平移模式切换） */
const spacePressed = ref(false)
/** 鼠标是否在 canvas 区域内 */
const mouseInCanvas = ref(false)

let originalImage: HTMLImageElement | null = null

function onResize() { fitToContainer() }

/** 从带认证的 URL 加载图片 */
function loadAuthImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    fetch(url, { headers: { Authorization: `Bearer ${getAccessToken() || ''}` } })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.blob()
      })
      .then((blob) => {
        const objUrl = URL.createObjectURL(blob)
        const img = new Image()
        img.onload = () => { URL.revokeObjectURL(objUrl); resolve(img) }
        img.onerror = () => { URL.revokeObjectURL(objUrl); reject(new Error('图片解码失败')) }
        img.src = objUrl
      })
      .catch(reject)
  })
}

async function initEditor() {
  if (!props.open || !props.imageUrl) return
  loading.value = true
  errorMsg.value = ''
  imageLoaded.value = false
  try {
    originalImage = await loadAuthImage(props.imageUrl)
    loading.value = false
    await nextTick()
    // canvas ref 可用了，初始化并绘制原图
    loadImage(originalImage)

    // 如果有已有遮罩，加载到 mask canvas
    if (props.existingMaskUrl) {
      try {
        const maskImg = await loadAuthImage(props.existingMaskUrl)
        loadExistingMask(maskImg)
      } catch {
        // 已有遮罩加载失败不阻断编辑
      }
    }

    // 等布局完成后再适配尺寸并显示
    requestAnimationFrame(() => {
      fitToContainer()
      requestAnimationFrame(() => {
        fitToContainer()
        imageLoaded.value = true
      })
    })
  } catch (e: any) {
    errorMsg.value = e?.message || '图片加载失败'
  } finally {
    loading.value = false
  }
}

watch(() => props.open, (open) => {
  if (open) initEditor()
}, { immediate: true })

function onContextMenu(e: Event) { e.preventDefault() }

/** 鼠标事件路由：平移模式下走 pan 逻辑，否则走绘制逻辑 */
function onMouseDown(e: MouseEvent) {
  if (spacePressed.value || e.button === 1) {
    e.preventDefault()
    startPan(e)
    return
  }
  if (e.button !== 0 && e.button !== 2) return
  startDrawing(e)
}

function onMouseMove(e: MouseEvent) {
  if (panning.value) { doPan(e); return }
  drawTo(e)
}

function onMouseUp(e: MouseEvent) {
  if (panning.value) { stopPan(); return }
  stopDrawing()
}

function onMouseLeave() {
  stopDrawing()
  stopPan()
  clearPreview()
  mouseInCanvas.value = false
}

function onMouseEnter() { mouseInCanvas.value = true }

/** 滚轮缩放 */
function onWheel(e: WheelEvent) {
  e.preventDefault()
  const delta = e.deltaY > 0 ? -0.1 : 0.1
  zoomAt(delta, e.clientX, e.clientY)
}

function handleSave() {
  saving.value = true
  exportMaskedPng()
    .then((blob) => emit('save', blob))
    .catch((e) => { errorMsg.value = e?.message || '导出失败' })
    .finally(() => { saving.value = false })
}

function handleCancel() {
  emit('cancel')
}

function onKeydown(e: KeyboardEvent) {
  if (!props.open) return
  if (e.code === 'Space') { e.preventDefault(); spacePressed.value = true; return }
  if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) { e.preventDefault(); undo() }
  else if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) { e.preventDefault(); redo() }
  else if (e.key === 'Escape') handleCancel()
  else if ((e.ctrlKey || e.metaKey) && e.key === '0') { e.preventDefault(); resetView() }
  else if ((e.ctrlKey || e.metaKey) && e.key === '=' ) { e.preventDefault(); zoomAt(0.2, window.innerWidth / 2, window.innerHeight / 2) }
  else if ((e.ctrlKey || e.metaKey) && e.key === '-' ) { e.preventDefault(); zoomAt(-0.2, window.innerWidth / 2, window.innerHeight / 2) }
}

function onKeyup(e: KeyboardEvent) {
  if (e.code === 'Space') spacePressed.value = false
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('keyup', onKeyup)
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('keyup', onKeyup)
  window.removeEventListener('resize', onResize)
})

const toolLabels: Record<Tool, string> = { brush: '画笔', eraser: '橡皮擦', bucket: '油漆桶' }
const cursorStyle = () => spacePressed.value || moveMode.value ? 'grab' : panning.value ? 'grabbing' : 'crosshair'
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="mask-editor-overlay" @contextmenu="onContextMenu">
      <div class="mask-editor-panel">
        <header class="me-header">
          <div class="me-title">
            <h2>遮罩编辑器</h2>
            <small v-if="imageLoaded">{{ imgCanvas?.width }} × {{ imgCanvas?.height }}px · {{ zoomPercent }}%</small>
          </div>
          <div class="me-actions">
            <V2Button variant="ghost" :disabled="!canUndo" @click="undo">撤销</V2Button>
            <V2Button variant="ghost" :disabled="!canRedo" @click="redo">重做</V2Button>
            <V2Button variant="ghost" @click="resetView" :disabled="loading">重置视图</V2Button>
            <V2Button variant="ghost" @click="clearMask" :disabled="loading">清空遮罩</V2Button>
            <V2Button variant="ghost" @click="handleCancel">取消</V2Button>
            <V2Button variant="primary" :disabled="loading || saving" @click="handleSave">
              {{ saving ? '保存中…' : '保存遮罩' }}
            </V2Button>
          </div>
        </header>

        <div v-if="errorMsg" class="me-error">{{ errorMsg }}</div>

        <div class="me-body" v-if="!loading">
          <!-- 工具栏 -->
          <aside class="me-toolbar">
            <div class="tool-section">
              <label>工具</label>
              <div class="tool-buttons">
                <button v-for="t in (['brush','eraser','bucket'] as Tool[])" :key="t"
                  :class="['tool-btn', { active: tool === t && !moveMode }]"
                  @click="tool = t; moveMode = false">{{ toolLabels[t] }}</button>
                <button :class="['tool-btn', { active: moveMode }]" @click="moveMode = !moveMode">移动</button>
              </div>
            </div>

            <div class="tool-section">
              <label>笔刷大小 <span>{{ brush.size }}px</span></label>
              <input type="range" min="1" max="250" v-model.number="brush.size" />
            </div>

            <div class="tool-section">
              <label>不透明度 <span>{{ Math.round(brush.opacity * 100) }}%</span></label>
              <input type="range" min="0" max="100" :value="Math.round(brush.opacity * 100)"
                @input="brush.opacity = Number(($event.target as HTMLInputElement).value) / 100" />
            </div>

            <div class="tool-section">
              <label>硬度 <span>{{ Math.round(brush.hardness * 100) }}%</span></label>
              <input type="range" min="0" max="100" :value="Math.round(brush.hardness * 100)"
                @input="brush.hardness = Number(($event.target as HTMLInputElement).value) / 100" />
            </div>

            <div class="tool-section">
              <label>遮罩颜色</label>
              <div class="tool-buttons">
                <button :class="['tool-btn', { active: maskColor === 'black' }]" @click="maskColor = 'black'">黑色</button>
                <button :class="['tool-btn', { active: maskColor === 'white' }]" @click="maskColor = 'white'">白色</button>
              </div>
            </div>

            <div class="tool-section">
              <label>遮罩透明度 <span>{{ Math.round(maskOpacity * 100) }}%</span></label>
              <input type="range" min="0" max="100" :value="Math.round(maskOpacity * 100)"
                @input="maskOpacity = Number(($event.target as HTMLInputElement).value) / 100" />
            </div>

            <div class="tool-hint">
              <p>滚轮缩放 · 空格+拖拽平移</p>
              <p>双指缩放 · 移动工具单指平移</p>
              <p>双击重置视图 · Ctrl+0</p>
              <p>Shift+点击画直线</p>
              <p>右键拖拽擦除</p>
              <p>Ctrl+Z 撤销 / Ctrl+Y 重做</p>
            </div>
          </aside>

          <!-- 移动端底部浮动工具栏 -->
          <div class="mobile-toolbar">
            <div class="mt-tools">
              <button :class="{ active: tool === 'brush' && !moveMode }" @click="tool='brush'; moveMode=false">画笔</button>
              <button :class="{ active: tool === 'eraser' && !moveMode }" @click="tool='eraser'; moveMode=false">橡皮</button>
              <button :class="{ active: tool === 'bucket' && !moveMode }" @click="tool='bucket'; moveMode=false">填充</button>
              <button :class="{ active: moveMode }" @click="moveMode=!moveMode">移动</button>
            </div>
            <div class="mt-sliders">
              <label>大小<span>{{ brush.size }}</span></label>
              <input type="range" min="1" max="250" v-model.number="brush.size" />
              <label>透明<span>{{ Math.round(brush.opacity*100) }}%</span></label>
              <input type="range" min="0" max="100" :value="Math.round(brush.opacity*100)" @input="brush.opacity=Number(($event.target as HTMLInputElement).value)/100" />
            </div>
            <div class="mt-actions">
              <button @click="undo" :disabled="!canUndo">↶</button>
              <button @click="redo" :disabled="!canRedo">↷</button>
              <button @click="clearMask">清空</button>
              <button @click="resetView">重置</button>
            </div>
          </div>

          <!-- Canvas 区域 -->
          <div class="me-canvas-area" @wheel="onWheel">
            <div class="canvas-stack" :class="{ hidden: !imageLoaded }" :style="{ cursor: cursorStyle() }"
              @mousedown="onMouseDown"
              @mousemove="onMouseMove"
              @mouseup="onMouseUp"
              @mouseleave="onMouseLeave"
              @mouseenter="onMouseEnter"
              @touchstart="onTouchStart"
              @touchmove="onTouchMove"
              @touchend="onTouchEnd"
            >
              <canvas ref="imgCanvas" class="layer img-layer" />
              <canvas ref="maskCanvas" class="layer mask-layer"
                :style="{ opacity: maskOpacity }"
              />
              <canvas ref="previewCanvas" class="layer preview-layer" />
            </div>
          </div>
        </div>
        <div v-else class="me-loading">
          <span>正在加载图片…</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.mask-editor-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0, 0, 0, 0.85);
  display: flex; align-items: center; justify-content: center;
}

.mask-editor-panel {
  width: 96vw; height: 92vh;
  background: #0d1424;
  border: 1px solid rgba(130, 149, 255, 0.25);
  border-radius: 16px;
  display: flex; flex-direction: column;
  overflow: hidden;
}

.me-header {
  padding: 12px 18px;
  display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid var(--v2-border, rgba(130,149,255,0.15));
  flex-shrink: 0;
}
.me-title { display: flex; align-items: baseline; gap: 10px; }
.me-title h2 { font-size: 16px; margin: 0; color: #e8edff; }
.me-title small { color: #7a85a8; font-size: 11px; }
.me-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.me-actions :deep(.v2-button) {
  min-height: 34px; padding: 0 12px;
  font-size: 12px; color: #c8d0ee;
  background: rgba(130, 149, 255, 0.1);
  border: 1px solid rgba(130, 149, 255, 0.25);
}
.me-actions :deep(.v2-button:hover:not(:disabled)) {
  background: rgba(130, 149, 255, 0.2);
  border-color: rgba(130, 149, 255, 0.4);
}
.me-actions :deep(.v2-button.primary) {
  color: #fff;
  background: linear-gradient(135deg, #8295ff, #865fee);
  border-color: transparent;
}
.me-actions :deep(.v2-button.primary:hover:not(:disabled)) {
  background: linear-gradient(135deg, #92a5ff, #966fee);
}

.me-error {
  padding: 8px 16px; color: #ffdce1;
  background: rgba(255, 127, 145, 0.1);
  border-bottom: 1px solid rgba(255, 127, 145, 0.2);
  font-size: 13px;
}

.me-body { flex: 1; display: flex; min-height: 0; min-width: 0; }

.me-toolbar {
  width: 200px; flex-shrink: 0;
  padding: 16px 14px;
  display: flex; flex-direction: column; gap: 18px;
  border-right: 1px solid var(--v2-border, rgba(130,149,255,0.15));
  overflow-y: auto;
  background: rgba(3, 12, 25, 0.4);
}
.tool-section { display: flex; flex-direction: column; gap: 7px; }
.tool-section label {
  font-size: 12px; color: #a0abc8;
  display: flex; justify-content: space-between; align-items: center;
}
.tool-section label span { color: #dfe5ff; font-weight: 600; }
.tool-section input[type="range"] {
  width: 100%; height: 6px;
  -webkit-appearance: none; appearance: none;
  background: rgba(130, 149, 255, 0.15);
  border-radius: 3px; outline: none;
}
.tool-section input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none;
  width: 16px; height: 16px;
  background: #8295ff; border-radius: 50%; cursor: pointer;
}
.tool-section input[type="range"]::-moz-range-thumb {
  width: 16px; height: 16px;
  background: #8295ff; border-radius: 50%; cursor: pointer; border: none;
}

.tool-buttons { display: grid; grid-template-columns: repeat(auto-fit, minmax(56px, 1fr)); gap: 4px; }
.tool-btn {
  padding: 7px 4px; font-size: 12px;
  color: #c8d0ee;
  background: rgba(130, 149, 255, 0.08);
  border: 1px solid rgba(130, 149, 255, 0.18);
  border-radius: 8px; cursor: pointer; transition: 0.15s;
}
.tool-btn:hover { background: rgba(130, 149, 255, 0.16); }
.tool-btn.active {
  color: #fff; background: rgba(130, 149, 255, 0.35);
  border-color: rgba(130, 149, 255, 0.6);
}

.tool-hint { margin-top: auto; padding-top: 12px; border-top: 1px solid rgba(130,149,255,0.12); }
.tool-hint p { font-size: 11px; color: #7a85a8; margin: 3px 0; }

.me-canvas-area {
  flex: 1; display: flex; align-items: center; justify-content: center;
  overflow: hidden; padding: 16px; min-width: 0; min-height: 0;
  background:
    repeating-conic-gradient(rgba(255,255,255,0.02) 0% 25%, transparent 0% 50%) 50% / 24px 24px;
}

.canvas-stack {
  position: relative;
  /* 尺寸和 transform 由 JS applyTransform() 设置 */
  transform-origin: 0 0;
  touch-action: none; /* 阻止浏览器默认触摸手势 */
}
.canvas-stack.hidden { visibility: hidden; }
.canvas-stack canvas {
  position: absolute; top: 0; left: 0;
  display: block;
}
.canvas-stack canvas.img-layer {
  position: relative; /* 撑开容器 */
}
.canvas-stack canvas.mask-layer { pointer-events: none; }
.canvas-stack canvas.preview-layer { pointer-events: none; }
/* canvas-stack 自身处理所有鼠标事件 */

/* 移动端底部浮动工具栏：默认隐藏 */
.mobile-toolbar { display: none; }

.me-loading { flex: 1; display: grid; place-items: center; color: #7a85a8; font-size: 14px; }

@media (max-width: 700px) {
  .me-body { flex-direction: column; }
  .me-toolbar { display: none; } /* 隐藏侧边工具栏 */
  .me-canvas-area { flex: 1; min-height: 0; }
  .me-header { padding: 8px 12px; }
  .me-title h2 { font-size: 14px; }
  .me-title small { display: none; }
  .me-actions :deep(.v2-button) { min-height: 30px; padding: 0 8px; font-size: 11px; }
  /* 底部浮动工具栏 */
  .mobile-toolbar {
    display: flex; flex-direction: column; gap: 8px;
    flex-shrink: 0;
    padding: 10px 12px;
    background: rgba(13, 20, 36, 0.95);
    border-top: 1px solid rgba(130, 149, 255, 0.2);
    flex-shrink: 0;
  }
  .mt-tools { display: flex; gap: 4px; }
  .mt-tools button {
    flex: 1; padding: 8px 0; font-size: 12px;
    color: #c8d0ee; background: rgba(130, 149, 255, 0.08);
    border: 1px solid rgba(130, 149, 255, 0.18);
    border-radius: 8px; cursor: pointer;
  }
  .mt-tools button.active {
    color: #fff; background: rgba(130, 149, 255, 0.35);
    border-color: rgba(130, 149, 255, 0.6);
  }
  .mt-sliders { display: grid; grid-template-columns: auto 1fr auto 1fr; align-items: center; gap: 6px; }
  .mt-sliders label { font-size: 10px; color: #a0abc8; display: flex; gap: 3px; }
  .mt-sliders label span { color: #dfe5ff; font-weight: 600; }
  .mt-sliders input[type="range"] {
    height: 6px; -webkit-appearance: none; appearance: none;
    background: rgba(130, 149, 255, 0.15); border-radius: 3px;
  }
  .mt-sliders input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none; width: 18px; height: 18px;
    background: #8295ff; border-radius: 50%;
  }
  .mt-actions { display: flex; gap: 4px; }
  .mt-actions button {
    flex: 1; padding: 7px 0; font-size: 12px;
    color: #c8d0ee; background: rgba(130, 149, 255, 0.08);
    border: 1px solid rgba(130, 149, 255, 0.18);
    border-radius: 8px; cursor: pointer;
  }
  .mt-actions button:disabled { opacity: 0.35; }
}
</style>