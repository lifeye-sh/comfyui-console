<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { getAccessToken } from '@/api/client'
import { resourceApi } from '@/api/modules'
import AssetPicker from '@/v2/components/AssetPicker.vue'
import MaskEditor from '@/v2/components/MaskEditor.vue'
import MediaViewer from '@/v2/components/MediaViewer.vue'
import V2Button from '@/v2/components/V2Button.vue'
import type { ResourceItem } from '@/v2/features/assets/model'

const props = defineProps<{
  modelValue: number | number[] | null | undefined
  mediaType: 'image' | 'video' | 'audio'
  disabled?: boolean
  multiple?: boolean
  /** 遮罩 Resource ID（仅 image 类型使用） */
  maskResourceId?: number | null
}>()
const emit = defineEmits<{
  'update:modelValue': [number | number[] | null]
  'update:maskResourceId': [number | null]
  selected: [ResourceItem | ResourceItem[] | null]
}>()
const pickerOpen = ref(false)
const maskEditorOpen = ref(false)
const viewerOpen = ref(false)
const resource = ref<ResourceItem | null>(null)
const previewUrl = ref('')
const maskPreviewUrl = ref('')
let request = 0

const isImage = () => props.mediaType === 'image'
const currentResourceId = () => Number(Array.isArray(props.modelValue) ? props.modelValue[0] : (props.modelValue || 0))

/** MediaViewer 需要的 output 对象 */
const viewerOutput = computed(() => {
  const id = currentResourceId()
  if (!id || !resource.value) return null
  return {
    id,
    filename: resource.value.filename,
    media_type: props.mediaType as 'image' | 'video' | 'audio',
    mime: resource.value.mime || '',
    width: resource.value.width,
    height: resource.value.height,
    duration: resource.value.duration,
  }
})

function release() { if (previewUrl.value) URL.revokeObjectURL(previewUrl.value); previewUrl.value = '' }
function releaseMask() { if (maskPreviewUrl.value) URL.revokeObjectURL(maskPreviewUrl.value); maskPreviewUrl.value = '' }

async function load() {
  const id = currentResourceId(); const marker = ++request; release(); resource.value = null
  if (!id) return
  try {
    const item = await resourceApi.get(id) as ResourceItem
    if (marker !== request) return
    resource.value = item
    if (item.media_type !== 'audio') {
      const response = await fetch(resourceApi.thumbUrl(id), { headers: { Authorization: `Bearer ${getAccessToken() || ''}` } })
      if (response.ok && marker === request) previewUrl.value = URL.createObjectURL(await response.blob())
    }
  } catch { resource.value = null }
}

async function loadMaskPreview() {
  releaseMask()
  const mid = Number(props.maskResourceId || 0)
  if (!mid) return
  try {
    const response = await fetch(resourceApi.thumbUrl(mid), { headers: { Authorization: `Bearer ${getAccessToken() || ''}` } })
    if (response.ok) maskPreviewUrl.value = URL.createObjectURL(await response.blob())
  } catch { /* ignore */ }
}

function choose(items: ResourceItem[]) {
  const item = items[0] || null; resource.value = item
  emit('update:modelValue', props.multiple ? items.map(value=>value.id) : (item?.id || null))
  emit('selected', props.multiple ? items : item)
  // 切换图片时清空遮罩
  emit('update:maskResourceId', null)
}
function clear() {
  resource.value = null; release(); emit('update:modelValue', null)
  emit('selected', null); emit('update:maskResourceId', null)
}
function clearMask() { releaseMask(); emit('update:maskResourceId', null) }

function openMaskEditor() {
  if (!currentResourceId()) return
  maskEditorOpen.value = true
}

async function onMaskSaved(blob: Blob) {
  maskEditorOpen.value = false
  try {
    const file = new File([blob], 'mask.png', { type: 'image/png' })
    const saved = await resourceApi.upload(file, 'image', 'input')
    emit('update:maskResourceId', saved.id)
  } catch {
    // 上传失败时仍关闭编辑器，用户可重试
  }
}

const imageUrl = () => currentResourceId() ? resourceApi.fileUrl(currentResourceId()) : ''
const maskUrl = () => Number(props.maskResourceId || 0) ? resourceApi.fileUrl(Number(props.maskResourceId)) : ''

watch(() => props.modelValue, () => { load(); if (isImage()) loadMaskPreview() }, { immediate: true })
watch(() => props.maskResourceId, () => { if (isImage()) loadMaskPreview() }, { immediate: true })
onUnmounted(() => { release(); releaseMask() })
</script>

<template>
  <div class="media-input" :class="{ filled: !!modelValue }">
    <div class="preview-row">
      <div class="preview">
        <button type="button" class="thumb-area" :disabled="disabled" @click="modelValue && !disabled ? viewerOpen=true : pickerOpen=true">
          <img v-if="previewUrl" :src="previewUrl" :alt="resource?.filename" />
          <span v-else class="media-icon">{{ mediaType==='image'?'▧':mediaType==='video'?'▶':'♪' }}</span>
        </button>
        <button type="button" class="text-area" :disabled="disabled" @click="pickerOpen=true">
          <b>{{ resource?.filename || `选择${mediaType==='image'?'图片':mediaType==='video'?'视频':'音频'}` }}</b>
          <small>{{ Array.isArray(modelValue) ? `已选择 ${modelValue.length} 个素材` : modelValue ? `素材 #${modelValue}` : '从素材库选择或上传' }}</small>
        </button>
      </div>
      <div class="side-buttons">
        <V2Button v-if="modelValue" variant="ghost" :disabled="disabled" @click="viewerOpen=true">预览</V2Button>
        <V2Button v-if="modelValue" variant="ghost" :disabled="disabled" @click="clear">清除</V2Button>
        <template v-if="isImage() && modelValue">
          <V2Button variant="ghost" :disabled="disabled" @click="openMaskEditor">
            {{ maskResourceId ? '编辑遮罩' : '画遮罩' }}
          </V2Button>
          <V2Button v-if="maskResourceId" variant="ghost" :disabled="disabled" @click="clearMask">清除遮罩</V2Button>
        </template>
      </div>
    </div>
    <div v-if="isImage() && maskResourceId" class="mask-badge">
      <span class="mask-indicator">◐</span>
      <small>已设置遮罩 #{{ maskResourceId }}</small>
    </div>
    <AssetPicker :open="pickerOpen" :media-type="mediaType" :multiple="multiple" @close="pickerOpen=false" @select="choose" />
    <MaskEditor
      v-if="isImage()"
      :open="maskEditorOpen"
      :image-url="imageUrl()"
      :existing-mask-url="maskUrl()"
      @save="onMaskSaved"
      @cancel="maskEditorOpen=false"
    />
    <MediaViewer :open="viewerOpen" :output="viewerOutput" @close="viewerOpen=false" />
  </div>
</template>

<style scoped>
.media-input{display:grid;gap:6px}
.preview-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:start}
.preview{min-height:76px;display:flex;align-items:center;gap:11px;min-width:0}.thumb-area{width:60px;height:58px;flex:0 0 auto;padding:0;display:grid;place-items:center;background:rgba(255,255,255,.04);border:1px dashed var(--v2-border-strong);border-radius:9px;cursor:pointer;overflow:hidden}.thumb-area:disabled{opacity:.55;cursor:not-allowed}.thumb-area img{width:100%;height:100%;object-fit:contain}.media-icon{font-size:24px;color:var(--v2-primary)}.text-area{flex:1;min-width:0;display:grid;gap:6px;padding:0;color:var(--v2-text);text-align:left;background:transparent;border:0;cursor:pointer}.text-area:disabled{opacity:.55;cursor:not-allowed}.text-area b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px}.text-area small{color:var(--v2-text-subtle)}
.side-buttons{display:flex;flex-direction:column;gap:4px}
.mask-badge{display:flex;align-items:center;gap:5px;padding:4px 10px;background:rgba(130,149,255,.12);border:1px solid rgba(130,149,255,.22);border-radius:8px}
.mask-badge small{color:#dfe5ff;font-size:11px}
.mask-indicator{color:#8295ff;font-size:14px}
</style>
