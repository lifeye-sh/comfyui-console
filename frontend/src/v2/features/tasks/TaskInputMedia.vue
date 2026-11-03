<script setup lang="ts">
import { ref, watch } from 'vue'
import type { TaskOutput } from './model'
import { useTaskOutputThumbs } from './useTaskOutputThumbs'

const props = defineProps<{ items: TaskOutput[] }>()
const emit = defineEmits<{ preview: [TaskOutput, TaskOutput[]] }>()
const { withThumbs, release } = useTaskOutputThumbs()
const inputs = ref<TaskOutput[]>([])
watch(() => props.items, async (items, _, cleanup) => {
  let active = true
  cleanup(() => { active = false; release(inputs.value) })
  inputs.value = items
  const loaded = await withThumbs(items)
  if (active) inputs.value = loaded
  else release(loaded)
}, { immediate: true })
</script>
<template>
  <section v-if="items.length">
    <h3>参考图与输入素材</h3>
    <div class="input-grid">
      <button v-for="(item,index) in inputs" :key="index" type="button" @click="emit('preview',item,inputs)">
        <img v-if="item.thumbUrl" :src="item.thumbUrl" :alt="item.filename" />
        <small v-else>查看{{ item.media_type === 'image' ? '图片' : '素材' }}</small>
        <span>{{ item.filename }}</span>
      </button>
    </div>
  </section>
</template>
<style scoped>
.input-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(115px,1fr));gap:8px}
button{display:grid;gap:6px;padding:7px;color:inherit;border:1px solid var(--v2-border);border-radius:8px;background:var(--v2-surface-soft);cursor:pointer}
img,small{width:100%;height:112px;object-fit:contain}small{display:grid;place-items:center}span{overflow-wrap:anywhere}
</style>
