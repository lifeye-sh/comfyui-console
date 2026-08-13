<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { resourceApi } from '@/api/modules'
import GlassCard from '@/v2/components/GlassCard.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'
import { formatSize, mediaLabel, type ResourceItem } from './model'
const items=ref<ResourceItem[]>([]);const loading=ref(false);async function load(){loading.value=true;try{items.value=await resourceApi.recycle()}finally{loading.value=false}}async function restore(item:ResourceItem){await resourceApi.restore(item.id);items.value=items.value.filter(v=>v.id!==item.id)}onMounted(load)
</script>
<template><div class="v2-page"><div class="v2-page-heading heading"><div><StatusBadge tone="warning">软删除</StatusBadge><h1>回收站</h1><p>普通用户仅能看到自己的已删除素材。</p></div><V2Button :disabled="loading" @click="load">刷新</V2Button></div><div class="list"><GlassCard v-for="item in items" :key="item.id"><div><b>{{ item.filename }}</b><span>{{ mediaLabel(item.media_type) }} · {{ formatSize(item.size) }} · 删除前目录 #{{ item.folder_id||'—' }}</span></div><V2Button variant="primary" @click="restore(item)">恢复</V2Button></GlassCard><p v-if="!items.length&&!loading">回收站为空</p></div></div></template>
<style scoped>.heading{display:flex;align-items:flex-end;justify-content:space-between}.heading h1{margin-top:14px}.list{display:grid;gap:10px}.list .glass-card{display:flex;align-items:center;justify-content:space-between;gap:14px}.list .glass-card>div{min-width:0;display:grid;gap:6px}.list b{overflow:hidden;text-overflow:ellipsis}.list span,.list>p{color:var(--v2-text-muted);font-size:12px}</style>
