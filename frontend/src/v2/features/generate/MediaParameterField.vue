<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { getAccessToken } from '@/api/client'
import { resourceApi } from '@/api/modules'
import AssetPicker from '@/v2/components/AssetPicker.vue'
import V2Button from '@/v2/components/V2Button.vue'
import type { ResourceItem } from '@/v2/features/assets/model'

const props = defineProps<{ modelValue: number | null | undefined; mediaType: 'image' | 'video' | 'audio'; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [number | null]; selected: [ResourceItem | null] }>()
const pickerOpen = ref(false)
const resource = ref<ResourceItem | null>(null)
const previewUrl = ref('')
let request = 0

function release() { if (previewUrl.value) URL.revokeObjectURL(previewUrl.value); previewUrl.value = '' }
async function load() {
  const id = Number(props.modelValue || 0); const marker = ++request; release(); resource.value = null
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
function choose(items: ResourceItem[]) { const item = items[0] || null; resource.value = item; emit('update:modelValue', item?.id || null); emit('selected', item) }
function clear() { resource.value = null; release(); emit('update:modelValue', null); emit('selected', null) }
watch(() => props.modelValue, load, { immediate: true }); onUnmounted(release)
</script>

<template>
  <div class="media-input" :class="{ filled: !!modelValue }">
    <button type="button" class="preview" :disabled="disabled" @click="pickerOpen=true">
      <img v-if="previewUrl" :src="previewUrl" :alt="resource?.filename" />
      <span v-else class="media-icon">{{ mediaType==='image'?'▧':mediaType==='video'?'▶':'♪' }}</span>
      <span class="copy"><b>{{ resource?.filename || `选择${mediaType==='image'?'图片':mediaType==='video'?'视频':'音频'}` }}</b><small>{{ modelValue ? `素材 #${modelValue}` : '从素材库选择或上传' }}</small></span>
    </button>
    <V2Button v-if="modelValue" variant="ghost" :disabled="disabled" @click="clear">清除</V2Button>
    <AssetPicker :open="pickerOpen" :media-type="mediaType" @close="pickerOpen=false" @select="choose" />
  </div>
</template>

<style scoped>
.media-input{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px}.preview{min-height:76px;padding:8px;display:flex;align-items:center;gap:11px;color:var(--v2-text);text-align:left;background:rgba(3,12,25,.42);border:1px dashed var(--v2-border-strong);border-radius:12px;cursor:pointer}.preview:disabled{opacity:.55;cursor:not-allowed}.preview img,.media-icon{width:60px;height:58px;flex:0 0 auto;object-fit:contain;background:rgba(255,255,255,.04);border-radius:9px}.media-icon{display:grid;place-items:center;font-size:24px;color:var(--v2-primary)}.copy{min-width:0;display:grid;gap:6px}.copy b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px}.copy small{color:var(--v2-text-subtle)}
</style>
