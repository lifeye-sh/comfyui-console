<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import GlassCard from '@/v2/components/GlassCard.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
const route = useRoute()
const title = computed(() => String(route.meta.title || '功能页面'))
</script>
<template><div class="v2-page"><div class="v2-page-heading"><StatusBadge tone="warning">建设中</StatusBadge><h1>{{ title }}</h1><p>当前已接入 V2 导航与响应式布局，业务能力将在后续迭代迁移。</p></div><GlassCard padding="lg"><h2>页面骨架已预留</h2><p>本页不会调用或修改 V1 业务数据。完成迁移前，请通过“返回稳定版”继续使用现有功能。</p></GlassCard></div></template>
<style scoped>.v2-page-heading h1 { margin-top:14px; }.glass-card h2 { margin-top:0; }.glass-card p { color:var(--v2-text-muted); line-height:1.8; }</style>
