<script setup lang="ts">
import { ref } from 'vue'
import { getAccessToken } from '@/api/client'
import { resourceApi } from '@/api/modules'
import CopyButton from '@/v2/components/CopyButton.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import { formatDuration, formatSize, mediaLabel, type ResourceItem } from './model'
const props = defineProps<{ item: ResourceItem; thumb?: string; selected?: boolean; selectOnPreview?: boolean }>()
const emit = defineEmits<{ open: []; select: []; preview: [] }>()
const promptOpen = ref(false)
const promptLoading = ref(false)
const promptText = ref('')
const promptKeys = ref<string[]>([])
async function showPrompt() {
  promptOpen.value = true
  promptLoading.value = true
  promptText.value = ''
  promptKeys.value = []
  try {
    const info = await resourceApi.generationInfo(props.item.id)
    const params = info?.params || {}
    // 收集所有包含 prompt 的参数（正向/负面提示词）
    const entries = Object.entries(params).filter(([k, v]) => String(k).toLowerCase().includes('prompt') && typeof v === 'string' && v.trim())
    promptKeys.value = entries.map(([k]) => k)
    promptText.value = entries.map(([k, v]) => `${k}：\n${String(v)}`).join('\n\n')
  } catch { promptText.value = '获取提示词失败' }
  finally { promptLoading.value = false }
}
async function download() {
  try {
    const r = await fetch(resourceApi.fileUrl(props.item.id), { headers: { Authorization: `Bearer ${getAccessToken() || ''}` } })
    if (!r.ok) return
    const blob = await r.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = props.item.filename || `resource-${props.item.id}`
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch { /* ignore */ }
}
</script>
<template><article class="resource-card" :class="{selected}" @dblclick="emit('open')"><button class="check" :aria-label="selected?'取消选择':'选择素材'" @click="emit('select')">{{ selected?'✓':'○' }}</button><button class="media" @click="selectOnPreview?emit('select'):emit('open')"><img v-if="thumb" :src="thumb" :alt="item.filename" loading="lazy"/><span v-else>{{ item.media_type==='audio'?'♪':item.media_type==='text'?'文':'加载中' }}</span><i v-if="item.media_type==='video'" class="play">▶</i></button><button v-if="selectOnPreview&&item.media_type!=='audio'" class="magnify" aria-label="放大预览" title="放大预览" @click.stop="emit('preview')">🔍</button><button class="download-btn" aria-label="下载" title="下载" @click.stop="download">⇩</button><button v-if="item.direction==='output'" class="prompt-btn" aria-label="查看提示词" title="查看提示词" @click.stop="showPrompt">提</button><div class="meta"><b :title="item.filename">{{ item.filename }}</b><div><StatusBadge :tone="item.direction==='output'?'success':'neutral'">{{ mediaLabel(item.media_type) }}</StatusBadge><small>{{ item.width&&item.height?`${item.width}×${item.height}`:item.media_type==='text'?formatSize(item.size):item.media_type!=='image'?formatDuration(item.duration):formatSize(item.size) }}</small></div></div>
<!-- 提示词弹窗（Teleport 到 body，避免被卡片 overflow/transform 裁剪） -->
<Teleport to="body"><div v-if="promptOpen" class="prompt-popup" @click.self="promptOpen=false"><div class="prompt-popup-body"><header><b>生成提示词</b><div class="prompt-header-actions"><CopyButton v-if="promptText && !promptLoading" :text="promptText" /><button @click="promptOpen=false">✕</button></div></header><div class="prompt-content" v-if="promptLoading">加载中…</div><pre v-else>{{ promptText }}</pre></div></div></Teleport>
</article></template>
<style scoped>.resource-card{position:relative;overflow:hidden;background:var(--v2-surface);border:1px solid var(--v2-border);border-radius:15px;box-shadow:var(--v2-shadow-soft);transition:.18s}.resource-card:hover,.resource-card.selected{transform:translateY(-2px);border-color:var(--v2-primary)}.check,.magnify,.download-btn,.prompt-btn{position:absolute;z-index:3;top:8px;width:31px;height:31px;color:var(--v2-text);background:rgba(5,14,28,.82);border:1px solid var(--v2-border);border-radius:9px;cursor:pointer;backdrop-filter:blur(8px)}.check{left:8px}.magnify{right:8px;font-size:21px}.magnify:hover{color:#fff;background:var(--v2-primary-strong)}.download-btn{right:44px;font-size:16px}.download-btn:hover{color:#fff;background:var(--v2-primary-strong)}.prompt-btn{right:80px;font-size:12px;color:#ffd580}.prompt-btn:hover{color:#fff;background:#ffb347}.media{width:100%;aspect-ratio:2/3;position:relative;display:grid;place-items:center;color:var(--v2-text-muted);background:rgba(0,0,0,.25);border:0;cursor:pointer;overflow:hidden}.media img{width:100%;height:100%;object-fit:contain}.media .play{position:absolute;width:40px;height:40px;display:grid;place-items:center;color:#fff;background:rgba(0,0,0,.45);border-radius:50%;font-style:normal}.meta{padding:11px;display:grid;gap:9px}.meta>b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}.meta>div{display:flex;justify-content:space-between;align-items:center;gap:7px}.meta small{color:var(--v2-text-subtle)}
.prompt-popup{position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center;padding:20px}.prompt-popup-body{width:min(560px,92vw);max-height:70vh;background:#1a2238;border:1px solid rgba(130,149,255,.3);border-radius:14px;display:flex;flex-direction:column;overflow:hidden}.prompt-popup-body header{padding:12px 16px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(130,149,255,.15)}.prompt-popup-body header b{color:#e8edff;font-size:14px}.prompt-header-actions{display:flex;align-items:center;gap:8px}.prompt-popup-body header button{color:#7a85a8;background:none;border:0;font-size:16px;cursor:pointer}.prompt-content{padding:30px;text-align:center;color:#7a85a8}.prompt-popup-body pre{margin:0;padding:16px;white-space:pre-wrap;word-break:break-word;color:#c8d0ee;font-family:inherit;font-size:13px;line-height:1.7;overflow-y:auto}</style>
