/**
 * 遮罩绘制逻辑 — 管理 canvas 上下文、笔刷渲染、缩放平移、撤销重做和遮罩导出。
 *
 * 遮罩存储在 maskCanvas 的 alpha 通道中：
 *   - 用户画了的地方 alpha ≈ 255（笔刷不透明度 × 255）
 *   - 未画的地方 alpha = 0
 *
 * 导出时与 ComfyUI 保持一致：
 *   - 遮罩区域在输出 PNG 中 alpha = 0（透明）
 *   - 非遮罩区域 alpha = 255（不透明）
 *   - LoadImage 节点读取后 mask = 1.0 - alpha/255.0 → 遮罩区域 = 1.0
 */

import { reactive, ref } from 'vue'

export type Tool = 'brush' | 'eraser' | 'bucket'

export type BrushSettings = {
  size: number      // 1–250
  opacity: number   // 0–1
  hardness: number  // 0–1
}

export type MaskColor = 'black' | 'white'

export type ViewState = {
  scale: number     // 缩放比例，1 = 适配
  offsetX: number   // 平移 X（CSS px，相对于 canvas-area 中心）
  offsetY: number   // 平移 Y
}

const MAX_HISTORY = 20

/** Flood fill 容差判断 */
function toleranceMatch(a: number, b: number, tolerance: number): boolean {
  return Math.abs(a - b) <= tolerance
}

export function useMaskCanvas() {
  const imgCanvas = ref<HTMLCanvasElement | null>(null)
  const maskCanvas = ref<HTMLCanvasElement | null>(null)
  const previewCanvas = ref<HTMLCanvasElement | null>(null)

  const tool = ref<Tool>('brush')
  const brush = reactive<BrushSettings>({ size: 30, opacity: 0.8, hardness: 1 })
  const maskColor = ref<MaskColor>('black')
  const maskOpacity = ref(0.7)
  const canUndo = ref(false)
  const canRedo = ref(false)
  const view = reactive<ViewState>({ scale: 1, offsetX: 0, offsetY: 0 })
  /** 是否处于平移模式（空格按住或中键拖拽） */
  const panning = ref(false)
  const zoomPercent = ref(100)
  /** 移动端"移动"工具模式：单指拖拽 = 平移而非绘制 */
  const moveMode = ref(false)

  let imgCtx: CanvasRenderingContext2D | null = null
  let maskCtx: CanvasRenderingContext2D | null = null
  let previewCtx: CanvasRenderingContext2D | null = null
  let drawing = false
  let lastX = 0
  let lastY = 0
  let shiftStartX: number | null = null
  let shiftStartY: number | null = null
  let history: ImageData[] = []
  let historyIndex = -1
  let imageWidth = 0
  let imageHeight = 0
  /** fitToContainer 计算出的基础显示尺寸（scale=1 时的 CSS px） */
  let baseDisplayW = 0
  let baseDisplayH = 0
  /** 平移拖拽起点 */
  let panStartX = 0
  let panStartY = 0
  let panStartOffsetX = 0
  let panStartOffsetY = 0

  /** 初始化 canvas 尺寸（必须与原图像素 1:1） */
  function setupCanvases(width: number, height: number) {
    imageWidth = width
    imageHeight = height
    for (const c of [imgCanvas.value, maskCanvas.value, previewCanvas.value]) {
      if (!c) continue
      c.width = width
      c.height = height
    }
    imgCtx = imgCanvas.value?.getContext('2d') || null
    maskCtx = maskCanvas.value?.getContext('2d', { willReadFrequently: true }) || null
    previewCtx = previewCanvas.value?.getContext('2d') || null
    history = []
    historyIndex = -1
    saveHistory()
  }

  /** 加载原图到 imgCanvas */
  function loadImage(image: HTMLImageElement) {
    setupCanvases(image.naturalWidth, image.naturalHeight)
    imgCtx?.drawImage(image, 0, 0)
    clearMask()
  }

  /** 加载已有纯遮罩 PNG（白色=遮罩区域，黑色=非遮罩，全不透明）到 maskCanvas。
   *  maskCanvas 格式：遮罩区域 alpha=255（画了的地方），非遮罩 alpha=0。
   *  从 RGB 亮度提取：白色(255)→alpha=255，黑色(0)→alpha=0。
   */
  function loadExistingMask(maskImg: HTMLImageElement) {
    if (!maskCtx) return
    const tmp = document.createElement('canvas')
    tmp.width = imageWidth
    tmp.height = imageHeight
    const tmpCtx = tmp.getContext('2d', { willReadFrequently: true })!
    tmpCtx.drawImage(maskImg, 0, 0)
    const srcData = tmpCtx.getImageData(0, 0, imageWidth, imageHeight)
    const maskData = maskCtx.createImageData(imageWidth, imageHeight)
    const [cr, cg, cb] = maskRGB()
    for (let i = 0; i < srcData.data.length; i += 4) {
      // 从 RGB 亮度判断是否为遮罩区域（白色=遮罩）
      const brightness = (srcData.data[i] + srcData.data[i + 1] + srcData.data[i + 2]) / 3
      maskData.data[i] = cr
      maskData.data[i + 1] = cg
      maskData.data[i + 2] = cb
      maskData.data[i + 3] = brightness > 128 ? 255 : 0 // 白色→255（遮罩），黑色→0
    }
    maskCtx.putImageData(maskData, 0, 0)
    saveHistory()
  }

  /** 清空遮罩层 */
  function clearMask() {
    if (!maskCtx) return
    maskCtx.clearRect(0, 0, imageWidth, imageHeight)
    saveHistory()
  }

  /** 计算 canvas 基础显示尺寸（contain 适配，不放大）并设置 CSS width/height */
  function fitToContainer() {
    const img = imgCanvas.value
    if (!img || !imageWidth || !imageHeight) return
    const stack = img.parentElement
    const area = stack?.parentElement
    if (!area) return
    const availW = area.clientWidth - 32
    const availH = area.clientHeight - 32
    if (availW <= 0 || availH <= 0) return
    const fitScale = Math.min(availW / imageWidth, availH / imageHeight, 1)
    baseDisplayW = Math.max(1, Math.round(imageWidth * fitScale))
    baseDisplayH = Math.max(1, Math.round(imageHeight * fitScale))
    view.scale = 1
    view.offsetX = 0
    view.offsetY = 0
    applyTransform()
  }

  /** 将当前 view 状态应用到所有 canvas 和 stack 的 CSS transform */
  function applyTransform() {
    const dw = Math.round(baseDisplayW * view.scale)
    const dh = Math.round(baseDisplayH * view.scale)
    const stack = imgCanvas.value?.parentElement
    for (const c of [imgCanvas.value, maskCanvas.value, previewCanvas.value]) {
      if (!c) continue
      c.style.width = `${dw}px`
      c.style.height = `${dh}px`
    }
    if (stack instanceof HTMLElement) {
      stack.style.width = `${dw}px`
      stack.style.height = `${dh}px`
      stack.style.transform = `translate(${view.offsetX}px, ${view.offsetY}px)`
    }
    zoomPercent.value = Math.round(view.scale * 100)
  }

  /** 缩放：以鼠标位置为中心 */
  function zoomAt(delta: number, centerX: number, centerY: number) {
    const oldScale = view.scale
    const newScale = Math.max(0.1, Math.min(10, oldScale * (1 + delta)))
    if (newScale === oldScale) return
    // 缩放中心相对于 canvas-stack 的位置，缩放后保持该点不动
    const stack = imgCanvas.value?.parentElement
    if (!stack) return
    const stackRect = stack.getBoundingClientRect()
    const px = centerX - stackRect.left - view.offsetX
    const py = centerY - stackRect.top - view.offsetY
    const ratio = newScale / oldScale
    view.offsetX = centerX - stackRect.left - px * ratio
    view.offsetY = centerY - stackRect.top - py * ratio
    view.scale = newScale
    applyTransform()
  }

  /** 开始平移 */
  function startPan(e: MouseEvent | PointerEvent) {
    panning.value = true
    panStartX = e.clientX
    panStartY = e.clientY
    panStartOffsetX = view.offsetX
    panStartOffsetY = view.offsetY
  }

  /** 平移中 */
  function doPan(e: MouseEvent | PointerEvent) {
    if (!panning.value) return
    view.offsetX = panStartOffsetX + (e.clientX - panStartX)
    view.offsetY = panStartOffsetY + (e.clientY - panStartY)
    applyTransform()
  }

  /** 结束平移 */
  function stopPan() {
    panning.value = false
  }

  /** 重置缩放和平移到适配状态 */
  function resetView() {
    fitToContainer()
  }

  /** 获取遮罩显示颜色 RGB */
  function maskRGB(): [number, number, number] {
    return maskColor.value === 'black' ? [0, 0, 0] : [255, 255, 255]
  }

  /** 将笔刷绘制到 mask canvas 的 alpha 通道 */
  function stampBrush(x: number, y: number) {
    if (!maskCtx) return
    const size = brush.size
    const r = size / 2
    const opacity = brush.opacity * 255
    const hardness = brush.hardness
    const [cr, cg, cb] = maskRGB()

    const px = Math.round(x)
    const py = Math.round(y)
    const x0 = Math.max(0, px - Math.ceil(r))
    const x1 = Math.min(imageWidth - 1, px + Math.ceil(r))
    const y0 = Math.max(0, py - Math.ceil(r))
    const y1 = Math.min(imageHeight - 1, py + Math.ceil(r))
    if (x1 < x0 || y1 < y0) return

    const region = maskCtx.getImageData(x0, y0, x1 - x0 + 1, y1 - y0 + 1)
    const data = region.data
    const effectiveRadius = r * (1 - hardness * 0.5)

    for (let py2 = 0; py2 < region.height; py2++) {
      for (let px2 = 0; px2 < region.width; px2++) {
        const dx = (x0 + px2) - px
        const dy = (y0 + py2) - py
        const dist = Math.sqrt(dx * dx + dy * dy)
        if (dist > r) continue
        let falloff: number
        if (dist <= effectiveRadius) {
          falloff = 1
        } else if (effectiveRadius < r) {
          falloff = 1 - (dist - effectiveRadius) / (r - effectiveRadius)
        } else {
          falloff = 0
        }
        const isEraser = tool.value === 'eraser'
        const idx = (py2 * region.width + px2) * 4
        if (isEraser) {
          data[idx + 3] = Math.max(0, data[idx + 3] - opacity * falloff)
        } else {
          data[idx] = cr
          data[idx + 1] = cg
          data[idx + 2] = cb
          data[idx + 3] = Math.min(255, data[idx + 3] + opacity * falloff)
        }
      }
    }
    maskCtx.putImageData(region, x0, y0)
  }

  /** 在两点间插值绘制 */
  function drawLine(x0: number, y0: number, x1: number, y1: number) {
    const dx = x1 - x0
    const dy = y1 - y0
    const dist = Math.sqrt(dx * dx + dy * dy)
    const step = Math.max(1, brush.size * 0.15)
    const steps = Math.max(1, Math.ceil(dist / step))
    for (let i = 1; i <= steps; i++) {
      const t = i / steps
      stampBrush(x0 + dx * t, y0 + dy * t)
    }
  }

  /** 油漆桶 flood fill */
  function paintBucket(startX: number, startY: number, tolerance = 32) {
    if (!maskCtx) return
    const px = Math.round(startX)
    const py = Math.round(startY)
    if (px < 0 || px >= imageWidth || py < 0 || py >= imageHeight) return

    const imageData = maskCtx.getImageData(0, 0, imageWidth, imageHeight)
    const data = imageData.data
    const startIdx = (py * imageWidth + px) * 4
    const targetA = data[startIdx + 3]
    const fillA = Math.round(brush.opacity * 255)
    const [cr, cg, cb] = maskRGB()

    if (Math.abs(targetA - fillA) < tolerance) return

    const stack: number[] = [px, py]
    const visited = new Uint8Array(imageWidth * imageHeight)

    while (stack.length) {
      const y = stack.pop()!
      const x = stack.pop()!
      if (x < 0 || x >= imageWidth || y < 0 || y >= imageHeight) continue
      const pos = y * imageWidth + x
      if (visited[pos]) continue
      const idx = pos * 4
      if (!toleranceMatch(data[idx + 3], targetA, tolerance)) continue
      visited[pos] = 1
      data[idx] = cr
      data[idx + 1] = cg
      data[idx + 2] = cb
      data[idx + 3] = fillA
      stack.push(x + 1, y, x - 1, y, x, y + 1, x, y - 1)
    }
    maskCtx.putImageData(imageData, 0, 0)
  }

  /** 笔刷预览（考虑缩放，笔刷在 canvas 像素空间绘制） */
  function drawPreview(x: number, y: number) {
    if (!previewCtx) return
    previewCtx.clearRect(0, 0, imageWidth, imageHeight)
    const r = brush.size / 2
    previewCtx.strokeStyle = tool.value === 'eraser' ? 'rgba(255,80,80,0.9)' : 'rgba(130,149,255,0.9)'
    previewCtx.lineWidth = 1.5
    previewCtx.beginPath()
    previewCtx.arc(x, y, r, 0, Math.PI * 2)
    previewCtx.stroke()
  }

  function clearPreview() {
    previewCtx?.clearRect(0, 0, imageWidth, imageHeight)
  }

  /**
   * 从 DOM 坐标转换为 canvas 像素坐标。
   * 考虑 CSS 缩放（canvas 显示尺寸 vs 内部分辨率）。
   * canvas 的 getBoundingClientRect 已包含 CSS transform，所以直接用即可。
   */
  function getCanvasCoords(e: MouseEvent | PointerEvent): { x: number; y: number } {
    const canvas = maskCanvas.value
    if (!canvas) return { x: 0, y: 0 }
    const rect = canvas.getBoundingClientRect()
    if (rect.width <= 0 || rect.height <= 0) return { x: 0, y: 0 }
    const scaleX = imageWidth / rect.width
    const scaleY = imageHeight / rect.height
    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top) * scaleY,
    }
  }

  /** 开始绘制（非平移模式） */
  function startDrawing(e: MouseEvent | PointerEvent) {
    const { x, y } = getCanvasCoords(e)
    drawing = true
    lastX = x
    lastY = y
    const isRightClick = 'buttons' in e && e.buttons === 2
    if (isRightClick && tool.value !== 'eraser') {
      const originalTool = tool.value
      tool.value = 'eraser'
      if (e.shiftKey && shiftStartX !== null && shiftStartY !== null) {
        drawLine(shiftStartX, shiftStartY, x, y)
      } else {
        stampBrush(x, y)
      }
      tool.value = originalTool
      shiftStartX = x
      shiftStartY = y
      return
    }
    if (tool.value === 'bucket') {
      paintBucket(x, y)
      drawing = false
      saveHistory()
      return
    }
    if (e.shiftKey && shiftStartX !== null && shiftStartY !== null) {
      drawLine(shiftStartX, shiftStartY, x, y)
    } else {
      stampBrush(x, y)
    }
    shiftStartX = x
    shiftStartY = y
  }

  /** 拖拽绘制 */
  function drawTo(e: MouseEvent | PointerEvent) {
    if (!drawing) {
      const { x, y } = getCanvasCoords(e)
      drawPreview(x, y)
      return
    }
    const { x, y } = getCanvasCoords(e)
    const isRightClick = 'buttons' in e && e.buttons === 2
    if (isRightClick && tool.value !== 'eraser') {
      const originalTool = tool.value
      tool.value = 'eraser'
      drawLine(lastX, lastY, x, y)
      tool.value = originalTool
    } else {
      drawLine(lastX, lastY, x, y)
    }
    lastX = x
    lastY = y
    drawPreview(x, y)
  }

  /** 结束绘制 */
  function stopDrawing() {
    if (drawing) saveHistory()
    drawing = false
  }

  // ======== 触摸事件处理 ========
  // 手势协议：
  //   单指拖拽 = 绘制（或平移，如果 moveMode 为 true）
  //   双指 = 缩放 + 平移
  //   双击 = 重置视图

  let touchPinchDist = 0
  let touchPinchScale = 1
  let touchCenterStartX = 0
  let touchCenterStartY = 0
  let touchPanStartX = 0
  let touchPanStartY = 0
  let touchPanOriginX = 0
  let touchPanOriginY = 0
  let touchDrawing = false
  let lastTapTime = 0

  /** 从 Touch 对象获取 canvas 像素坐标 */
  function touchToCanvas(t: Touch): { x: number; y: number } {
    const canvas = maskCanvas.value
    if (!canvas) return { x: 0, y: 0 }
    const rect = canvas.getBoundingClientRect()
    if (rect.width <= 0 || rect.height <= 0) return { x: 0, y: 0 }
    return {
      x: (t.clientX - rect.left) * (imageWidth / rect.width),
      y: (t.clientY - rect.top) * (imageHeight / rect.height),
    }
  }

  function onTouchStart(e: TouchEvent) {
    if (e.touches.length === 2) {
      // 双指：开始缩放+平移
      e.preventDefault()
      touchDrawing = false
      drawing = false
      const t1 = e.touches[0], t2 = e.touches[1]
      touchPinchDist = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY)
      touchPinchScale = view.scale
      touchCenterStartX = (t1.clientX + t2.clientX) / 2
      touchCenterStartY = (t1.clientY + t2.clientY) / 2
      touchPanStartX = touchCenterStartX
      touchPanStartY = touchCenterStartY
      touchPanOriginX = view.offsetX
      touchPanOriginY = view.offsetY
    } else if (e.touches.length === 1) {
      // 单指：绘制或平移
      if (moveMode.value) {
        e.preventDefault()
        const t = e.touches[0]
        touchPanStartX = t.clientX
        touchPanStartY = t.clientY
        touchPanOriginX = view.offsetX
        touchPanOriginY = view.offsetY
        panning.value = true
      } else {
        // 检查双击
        const now = Date.now()
        if (now - lastTapTime < 300) {
          // 双击 = 重置视图
          resetView()
          lastTapTime = 0
          return
        }
        lastTapTime = now
        e.preventDefault()
        const { x, y } = touchToCanvas(e.touches[0])
        touchDrawing = true
        drawing = true
        lastX = x
        lastY = y
        if (tool.value === 'bucket') {
          paintBucket(x, y)
          drawing = false
          touchDrawing = false
          saveHistory()
          return
        }
        stampBrush(x, y)
      }
    }
  }

  function onTouchMove(e: TouchEvent) {
    if (e.touches.length === 2 && touchPinchDist > 0) {
      e.preventDefault()
      const t1 = e.touches[0], t2 = e.touches[1]
      const dist = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY)
      const ratio = dist / touchPinchDist
      const newScale = Math.max(0.1, Math.min(10, touchPinchScale * ratio))
      view.scale = newScale
      // 平移：跟随双指中心移动
      const cx = (t1.clientX + t2.clientX) / 2
      const cy = (t1.clientY + t2.clientY) / 2
      view.offsetX = touchPanOriginX + (cx - touchPanStartX)
      view.offsetY = touchPanOriginY + (cy - touchPanStartY)
      applyTransform()
    } else if (e.touches.length === 1 && panning.value) {
      e.preventDefault()
      const t = e.touches[0]
      view.offsetX = touchPanOriginX + (t.clientX - touchPanStartX)
      view.offsetY = touchPanOriginY + (t.clientY - touchPanStartY)
      applyTransform()
    } else if (e.touches.length === 1 && touchDrawing) {
      e.preventDefault()
      const { x, y } = touchToCanvas(e.touches[0])
      drawLine(lastX, lastY, x, y)
      lastX = x
      lastY = y
    }
  }

  function onTouchEnd(e: TouchEvent) {
    if (e.touches.length === 0) {
      if (touchDrawing) { saveHistory(); touchDrawing = false; drawing = false }
      if (panning.value) { panning.value = false }
      touchPinchDist = 0
    } else if (e.touches.length === 1) {
      // 从双指变单指，停止缩放
      touchPinchDist = 0
      touchDrawing = false
      drawing = false
    }
  }

  /** 保存历史快照 */
  function saveHistory() {
    if (!maskCtx) return
    const snapshot = maskCtx.getImageData(0, 0, imageWidth, imageHeight)
    history = history.slice(0, historyIndex + 1)
    history.push(snapshot)
    if (history.length > MAX_HISTORY) history.shift()
    historyIndex = history.length - 1
    canUndo.value = historyIndex > 0
    canRedo.value = historyIndex < history.length - 1
  }

  function undo() {
    if (historyIndex <= 0 || !maskCtx) return
    historyIndex--
    maskCtx.putImageData(history[historyIndex], 0, 0)
    canUndo.value = historyIndex > 0
    canRedo.value = historyIndex < history.length - 1
  }

  function redo() {
    if (historyIndex >= history.length - 1 || !maskCtx) return
    historyIndex++
    maskCtx.putImageData(history[historyIndex], 0, 0)
    canUndo.value = historyIndex > 0
    canRedo.value = historyIndex < history.length - 1
  }

  /**
   * 导出纯遮罩 PNG Blob（不包含原图，避免透明区域被缩略图渲染为黑色）。
   *
   * 遮罩区域：RGB=白色(255,255,255)，alpha=255（不透明）
   * 非遮罩区域：RGB=黑色(0,0,0)，alpha=255（不透明）
   *
   * 全图不透明，缩略图不会出现黑色透明区域。
   * 后端用 LoadImageMask 节点的 channel="red" 提取遮罩：
   *   mask = R / 255.0 → 白色区域=1.0（遮罩生效），黑色区域=0.0（无遮罩）
   */
  async function exportMaskedPng(): Promise<Blob> {
    const outCanvas = document.createElement('canvas')
    outCanvas.width = imageWidth
    outCanvas.height = imageHeight
    const outCtx = outCanvas.getContext('2d')!
    const outData = outCtx.createImageData(imageWidth, imageHeight)
    if (maskCtx) {
      const maskData = maskCtx.getImageData(0, 0, imageWidth, imageHeight)
      for (let i = 0; i < outData.data.length; i += 4) {
        const maskAlpha = maskData.data[i + 3] // maskCanvas 上画了的地方 alpha 高
        const masked = maskAlpha > 0
        outData.data[i] = masked ? 255 : 0       // R
        outData.data[i + 1] = masked ? 255 : 0   // G
        outData.data[i + 2] = masked ? 255 : 0   // B
        outData.data[i + 3] = 255                // A: 全不透明
      }
    } else {
      // 无遮罩数据：全部不透明黑色
      for (let i = 0; i < outData.data.length; i += 4) {
        outData.data[i + 3] = 255
      }
    }
    outCtx.putImageData(outData, 0, 0)
    return new Promise((resolve, reject) => {
      outCanvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new Error('PNG 编码失败'))),
        'image/png',
      )
    })
  }

  /** 检查遮罩是否为空 */
  function hasMask(): boolean {
    if (!maskCtx) return false
    const data = maskCtx.getImageData(0, 0, imageWidth, imageHeight).data
    for (let i = 3; i < data.length; i += 4) {
      if (data[i] > 0) return true
    }
    return false
  }

  return {
    imgCanvas,
    maskCanvas,
    previewCanvas,
    tool,
    brush,
    maskColor,
    maskOpacity,
    canUndo,
    canRedo,
    view,
    panning,
    moveMode,
    zoomPercent,
    loadImage,
    loadExistingMask,
    clearMask,
    fitToContainer,
    resetView,
    zoomAt,
    startPan,
    doPan,
    stopPan,
    startDrawing,
    drawTo,
    stopDrawing,
    onTouchStart,
    onTouchMove,
    onTouchEnd,
    undo,
    redo,
    exportMaskedPng,
    hasMask,
    clearPreview,
  }
}
