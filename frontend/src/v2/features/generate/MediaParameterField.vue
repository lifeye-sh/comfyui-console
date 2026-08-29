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
const viewerResourceId = ref(0)
const resources = ref<ResourceItem[]>([])
const previewUrls = ref<Record<number, string>>({})
const maskPreviewUrl = ref('')
let request = 0

const isImage = () => props.mediaType === 'image'
const orderedIds = computed(() => {
  const values = Array.isArray(props.modelValue) ? props.modelValue : props.modelValue ? [props.modelValue] : []
  return values.map(Number).filter((value, index, all) => value > 0 && all.indexOf(value) === index)
})
const hasValue = computed(() => orderedIds.value.length > 0)
const currentResourceId = () => orderedIds.value[0] || 0
const resource = computed(() => resources.value.find(item => item.id === currentResourceId()) || null)

/** MediaViewer 需要的 output 对象 */
const viewerOutput = computed(() => {
  const id = viewerResourceId.value || currentResourceId()
  const item = resources.value.find(value => value.id === id)
  if (!id || !item) return null
  return {
    id,
    filename: item.filename,
    media_type: props.mediaType as 'image' | 'video' | 'audio',
    mime: item.mime || '',
    width: item.width,
    height: item.height,
    duration: item.duration,
  }
})

function release() { Object.values(previewUrls.value).forEach(value => URL.revokeObjectURL(value)); previewUrls.value = {} }
function releaseMask() { if (maskPreviewUrl.value) URL.revokeObjectURL(maskPreviewUrl.value); maskPreviewUrl.value = '' }

async function load() {
  const ids = [...orderedIds.value]; const marker = ++request; release(); resources.value = []
  if (!ids.length) return
  const loaded = await Promise.all(ids.map(async id => { try { return await resourceApi.get(id) as ResourceItem } catch { return null } }))
  if (marker !== request) return
  resources.value = loaded.filter((item): item is ResourceItem => !!item)
  const entries = await Promise.all(resources.value.map(async item => {
    if (item.media_type === 'audio') return null
    try { const response = await fetch(resourceApi.thumbUrl(item.id), { headers: { Authorization: `Bearer ${getAccessToken() || ''}` } }); return response.ok ? [item.id, URL.createObjectURL(await response.blob())] as const : null } catch { return null }
  }))
  if (marker !== request) { entries.forEach(entry => { if (entry) URL.revokeObjectURL(entry[1]) }); return }
  previewUrls.value = Object.fromEntries(entries.filter((entry): entry is readonly [number,string] => !!entry))
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
  const item = items[0] || null
  emit('update:modelValue', props.multiple ? items.map(value=>value.id) : (item?.id || null))
  emit('selected', props.multiple ? items : item)
  // 切换图片时清空遮罩
  emit('update:maskResourceId', null)
}
function clear() {
  resources.value = []; release(); emit('update:modelValue', props.multiple ? [] : null)
  emit('selected', null); emit('update:maskResourceId', null)
}
function removeAt(index:number){const next=orderedIds.value.filter((_,position)=>position!==index);emit('update:modelValue',next);emit('selected',resources.value.filter(item=>next.includes(item.id)))}
function openViewer(id:number){viewerResourceId.value=id;viewerOpen.value=true}
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
  <div class="media-input" :class="{ filled: hasValue }">
    <div v-if="multiple" class="multiple-input">
      <div class="multiple-toolbar">
        <div>
          <b>参考图片顺序</b>
          <small>按第 1 张到第 {{ orderedIds.length || 'N' }} 张的顺序发送给模型</small>
        </div>
        <div class="multiple-actions">
          <V2Button variant="ghost" :disabled="disabled" @click="pickerOpen=true">
            {{ hasValue ? '重新选择图片' : '选择图片' }}
          </V2Button>
          <V2Button v-if="hasValue" variant="ghost" :disabled="disabled" @click="clear">清除全部</V2Button>
        </div>
      </div>

      <div v-if="hasValue" class="ordered-media-list">
        <article v-for="(id, index) in orderedIds" :key="id" class="ordered-media-item">
          <button type="button" class="ordered-thumb" :disabled="disabled" @click="openViewer(id)">
            <img v-if="previewUrls[id]" :src="previewUrls[id]" :alt="resources.find(item => item.id === id)?.filename || `素材 ${id}`" />
            <span v-else class="media-icon">▧</span>
            <span class="order-badge">{{ index + 1 }}</span>
          </button>
          <button type="button" class="ordered-copy" :disabled="disabled" @click="openViewer(id)">
            <b>第 {{ index + 1 }} 张</b>
            <small>{{ resources.find(item => item.id === id)?.filename || `素材 #${id}` }}</small>
          </button>
          <button type="button" class="remove-item" :disabled="disabled" :aria-label="`移除第 ${index + 1} 张图片`" @click="removeAt(index)">×</button>
        </article>
      </div>
      <button v-else type="button" class="multiple-empty" :disabled="disabled" @click="pickerOpen=true">
        <span class="media-icon">▧</span>
        <b>选择多张参考图片</b>
        <small>选择后将在这里按顺序逐张显示</small>
      </button>
    </div>

    <div v-else class="preview-row">
      <div class="preview">
        <button type="button" class="thumb-area" :disabled="disabled" @click="hasValue ? openViewer(currentResourceId()) : pickerOpen=true">
          <img v-if="previewUrls[currentResourceId()]" :src="previewUrls[currentResourceId()]" :alt="resource?.filename" />
          <span v-else class="media-icon">{{ mediaType==='image'?'▧':mediaType==='video'?'▶':'♪' }}</span>
        </button>
        <button type="button" class="text-area" :disabled="disabled" @click="pickerOpen=true">
          <b>{{ resource?.filename || `选择${mediaType==='image'?'图片':mediaType==='video'?'视频':'音频'}` }}</b>
          <small>{{ hasValue ? `素材 #${currentResourceId()}` : '从素材库选择或上传' }}</small>
        </button>
      </div>
      <div class="side-buttons">
        <V2Button v-if="hasValue" variant="ghost" :disabled="disabled" @click="openViewer(currentResourceId())">预览</V2Button>
        <V2Button v-if="hasValue" variant="ghost" :disabled="disabled" @click="clear">清除</V2Button>
        <template v-if="isImage() && hasValue">
          <V2Button variant="ghost" :disabled="disabled" @click="openMaskEditor">
            {{ maskResourceId ? '编辑遮罩' : '画遮罩' }}
          </V2Button>
          <V2Button v-if="maskResourceId" variant="ghost" :disabled="disabled" @click="clearMask">清除遮罩</V2Button>
        </template>
      </div>
    </div>
    <div v-if="!multiple && isImage() && maskResourceId" class="mask-badge">
      <span class="mask-indicator">◐</span>
      <small>已设置遮罩 #{{ maskResourceId }}</small>
    </div>
    <AssetPicker :open="pickerOpen" :media-type="mediaType" :multiple="multiple" @close="pickerOpen=false" @select="choose" />
    <MaskEditor
      v-if="!multiple && isImage()"
      :open="maskEditorOpen"
      :image-url="imageUrl()"
      :existing-mask-url="maskUrl()"
      @save="onMaskSaved"
      @cancel="maskEditorOpen=false"
    />
    <MediaViewer :open="viewerOpen" :output="viewerOutput" @close="viewerOpen=false; viewerResourceId=0" />
  </div>
</template>

<style scoped>
.media-input{display:grid;gap:6px}
.multiple-input{display:grid;gap:10px;padding:11px;background:rgba(255,255,255,.025);border:1px solid var(--v2-border);border-radius:12px}
.multiple-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px}.multiple-toolbar>div:first-child{display:grid;gap:4px}.multiple-toolbar b{font-size:13px}.multiple-toolbar small{color:var(--v2-text-subtle);font-size:11px}.multiple-actions{display:flex;gap:6px;flex:0 0 auto}
.ordered-media-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(205px,1fr));gap:8px}.ordered-media-item{min-width:0;display:grid;grid-template-columns:62px minmax(0,1fr) 28px;align-items:center;gap:9px;padding:7px;background:rgba(255,255,255,.035);border:1px solid var(--v2-border);border-radius:10px}.ordered-thumb{position:relative;width:62px;height:62px;padding:0;display:grid;place-items:center;overflow:hidden;cursor:pointer;background:rgba(0,0,0,.18);border:1px solid var(--v2-border-strong);border-radius:8px}.ordered-thumb:disabled,.ordered-copy:disabled,.remove-item:disabled,.multiple-empty:disabled{opacity:.55;cursor:not-allowed}.ordered-thumb img{width:100%;height:100%;object-fit:contain}.order-badge{position:absolute;top:4px;left:4px;min-width:21px;height:21px;padding:0 5px;display:grid;place-items:center;color:#fff;font-size:11px;font-weight:800;background:var(--v2-primary);border:1px solid rgba(255,255,255,.42);border-radius:999px;box-shadow:0 2px 7px rgba(0,0,0,.32)}.ordered-copy{min-width:0;display:grid;gap:5px;padding:0;text-align:left;color:var(--v2-text);cursor:pointer;background:transparent;border:0}.ordered-copy b{font-size:12px}.ordered-copy small{overflow:hidden;color:var(--v2-text-subtle);font-size:11px;text-overflow:ellipsis;white-space:nowrap}.remove-item{width:28px;height:28px;padding:0;color:var(--v2-text-muted);font-size:18px;cursor:pointer;background:transparent;border:0;border-radius:7px}.remove-item:hover{color:#ff8e8e;background:rgba(255,90,90,.1)}
.multiple-empty{min-height:92px;display:grid;place-items:center;align-content:center;gap:5px;color:var(--v2-text);cursor:pointer;background:rgba(255,255,255,.018);border:1px dashed var(--v2-border-strong);border-radius:10px}.multiple-empty b{font-size:12px}.multiple-empty small{color:var(--v2-text-subtle);font-size:11px}
.preview-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:start}
.preview{min-height:76px;display:flex;align-items:center;gap:11px;min-width:0}.thumb-area{width:60px;height:58px;flex:0 0 auto;padding:0;display:grid;place-items:center;background:rgba(255,255,255,.04);border:1px dashed var(--v2-border-strong);border-radius:9px;cursor:pointer;overflow:hidden}.thumb-area:disabled{opacity:.55;cursor:not-allowed}.thumb-area img{width:100%;height:100%;object-fit:contain}.media-icon{font-size:24px;color:var(--v2-primary)}.text-area{flex:1;min-width:0;display:grid;gap:6px;padding:0;color:var(--v2-text);text-align:left;background:transparent;border:0;cursor:pointer}.text-area:disabled{opacity:.55;cursor:not-allowed}.text-area b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px}.text-area small{color:var(--v2-text-subtle)}
.side-buttons{display:flex;flex-direction:column;gap:4px}
.mask-badge{display:flex;align-items:center;gap:5px;padding:4px 10px;background:rgba(130,149,255,.12);border:1px solid rgba(130,149,255,.22);border-radius:8px}
.mask-badge small{color:#dfe5ff;font-size:11px}
.mask-indicator{color:#8295ff;font-size:14px}
@media(max-width:700px){.multiple-toolbar{align-items:flex-start;flex-direction:column}.multiple-actions{width:100%}.multiple-actions>*{flex:1}.ordered-media-list{grid-template-columns:1fr}}
</style>
