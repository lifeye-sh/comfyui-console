<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getAccessToken } from '@/api/client'
import { resourceApi } from '@/api/modules'
import GlassCard from '@/v2/components/GlassCard.vue'
import MediaViewer from '@/v2/components/MediaViewer.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'
import { formatSize, mediaLabel, type ResourceItem } from './model'
import type { TaskOutput } from '@/v2/features/tasks/model'

const items = ref<ResourceItem[]>([])
const loading = ref(false)
const purging = ref(false)
const preview = ref<TaskOutput | null>(null)
const thumbs = ref<Record<number, string>>({})

async function loadThumbs(list: ResourceItem[]) {
  for (const item of list) {
    if (thumbs.value[item.id] || item.media_type === 'audio') continue
    try {
      const r = await fetch(resourceApi.thumbUrl(item.id), { headers: { Authorization: `Bearer ${getAccessToken() || ''}` } })
      if (r.ok) thumbs.value[item.id] = URL.createObjectURL(await r.blob())
    } catch { /* ignore */ }
  }
}

async function load() {
  loading.value = true
  try {
    items.value = await resourceApi.recycle()
    void loadThumbs(items.value)
  } finally { loading.value = false }
}

async function restore(item: ResourceItem) {
  await resourceApi.restore(item.id)
  items.value = items.value.filter(v => v.id !== item.id)
}

async function purgeAll() {
  if (!items.value.length) return
  if (!confirm(`确认永久删除回收站中的 ${items.value.length} 个素材？\n此操作将删除物理文件，无法恢复。`)) return
  purging.value = true
  try {
    const ids = items.value.map(v => v.id)
    const result = await resourceApi.batchPurge(ids)
    alert(`已永久删除 ${result.deleted} 项${result.failed?.length ? `，${result.failed.length} 项失败` : ''}`)
    items.value = []
    thumbs.value = {}
  } catch (e: any) {
    alert(e?.response?.data?.detail || e?.message || '清理失败')
  } finally { purging.value = false }
}

async function purgeOne(item: ResourceItem) {
  if (!confirm(`确认永久删除「${item.filename}」？\n此操作将删除物理文件，无法恢复。`)) return
  try {
    await resourceApi.batchPurge([item.id])
    items.value = items.value.filter(v => v.id !== item.id)
    if (thumbs.value[item.id]) { URL.revokeObjectURL(thumbs.value[item.id]); delete thumbs.value[item.id] }
  } catch (e: any) {
    alert(e?.response?.data?.detail || e?.message || '删除失败')
  }
}

function openPreview(item: ResourceItem) {
  preview.value = { id: item.id, filename: item.filename, media_type: item.media_type, mime: item.mime || '', width: item.width, height: item.height, duration: item.duration }
}

onMounted(load)
</script>

<template>
  <div class="v2-page">
    <div class="v2-page-heading heading">
      <div>
        <StatusBadge tone="warning">回收站</StatusBadge>
        <h1>回收站</h1>
        <p>已删除的素材可恢复或永久清理。{{ items.length }} 项</p>
      </div>
      <div class="head-actions">
        <V2Button :disabled="loading" @click="load">刷新</V2Button>
        <V2Button v-if="items.length" variant="danger" :disabled="purging" @click="purgeAll">{{ purging ? '清理中…' : '清空回收站' }}</V2Button>
      </div>
    </div>
    <div class="recycle-grid">
      <GlassCard v-for="item in items" :key="item.id" padding="none" class="recycle-card">
        <button class="card-media" @click="openPreview(item)">
          <img v-if="thumbs[item.id]" :src="thumbs[item.id]" :alt="item.filename" />
          <span v-else class="media-icon">{{ item.media_type === 'audio' ? '♪' : '▭' }}</span>
          <i v-if="item.media_type === 'video'" class="play">▶</i>
        </button>
        <div class="card-info">
          <b :title="item.filename">{{ item.filename }}</b>
          <small>{{ mediaLabel(item.media_type) }} · {{ formatSize(item.size) }}</small>
          <div class="card-actions">
            <button @click="restore(item)">恢复</button>
            <button class="danger" @click="purgeOne(item)">永久删除</button>
          </div>
        </div>
      </GlassCard>
      <p v-if="!items.length && !loading" class="empty">回收站为空</p>
    </div>
    <MediaViewer :open="!!preview" :output="preview" @close="preview = null" />
  </div>
</template>

<style scoped>
.heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 14px }
.heading h1 { margin-top: 14px }
.head-actions { display: flex; gap: 8px }
.recycle-grid { margin-top: 16px; display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 12px }
.recycle-card { overflow: hidden; display: flex; flex-direction: column }
.card-media { width: 100%; aspect-ratio: 4/3; position: relative; display: grid; place-items: center; background: rgba(0,0,0,.25); border: 0; cursor: pointer; overflow: hidden }
.card-media img { width: 100%; height: 100%; object-fit: contain }
.media-icon { font-size: 32px; color: var(--v2-text-muted) }
.play { position: absolute; width: 40px; height: 40px; display: grid; place-items: center; color: #fff; background: rgba(0,0,0,.45); border-radius: 50%; font-style: normal }
.card-info { padding: 10px 12px; display: grid; gap: 6px }
.card-info b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px }
.card-info small { color: var(--v2-text-subtle); font-size: 11px }
.card-actions { display: flex; gap: 6px; margin-top: 4px }
.card-actions button { flex: 1; padding: 6px 0; font-size: 11px; color: var(--v2-text-muted); background: var(--v2-surface-soft); border: 1px solid var(--v2-border); border-radius: 7px; cursor: pointer }
.card-actions button:hover { background: rgba(130,149,255,.1) }
.card-actions .danger { color: var(--v2-danger) }
.card-actions .danger:hover { background: rgba(255,127,145,.08) }
.empty { grid-column: 1/-1; padding: 70px; text-align: center; color: var(--v2-text-muted) }
</style>