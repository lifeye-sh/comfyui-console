<script setup lang="ts">
import { ref } from 'vue'
import AssetPicker from '@/v2/components/AssetPicker.vue'
import GlassCard from '@/v2/components/GlassCard.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'
const open=ref(false);const type=ref<'image'|'video'|'audio'>('image');const result=ref<any[]>([])
</script>
<template><div class="v2-page"><div class="v2-page-heading"><StatusBadge tone="info">通用组件</StatusBadge><h1>素材选择器</h1><p>供下一轮所有图片、视频和音频输入参数复用。</p></div><GlassCard><div class="buttons"><V2Button v-for="item in ['image','video','audio']" :key="item" :variant="type===item?'primary':'secondary'" @click="type=item as any;open=true">选择{{ item==='image'?'图片':item==='video'?'视频':'音频' }}</V2Button></div><pre>{{ result.length?JSON.stringify(result.map(v=>({id:v.id,filename:v.filename,media_type:v.media_type})),null,2):'尚未选择素材' }}</pre></GlassCard><AssetPicker :open="open" :media-type="type" @close="open=false" @select="result=$event"/></div></template>
<style scoped>.v2-page-heading h1{margin-top:14px}.buttons{display:flex;gap:9px;flex-wrap:wrap}pre{margin-top:18px;padding:14px;min-height:100px;color:var(--v2-text-muted);background:rgba(0,0,0,.22);border-radius:12px;white-space:pre-wrap}</style>
