<script setup lang="ts">
withDefaults(defineProps<{ tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'info' }>(), { tone: 'neutral' })
</script>
<template><span class="badge" :class="tone"><i /><slot /></span></template>
<style scoped>
.badge { width:max-content; display:inline-flex; align-items:center; gap:7px; padding:5px 9px; color:var(--v2-text-muted); background:var(--v2-surface-soft); border:1px solid var(--v2-border); border-radius:999px; font-size:12px; }.badge i { width:6px; height:6px; border-radius:50%; background:currentColor; }.success{color:var(--v2-success)}.warning{color:var(--v2-warning)}.danger{color:var(--v2-danger)}.info{color:var(--v2-info)}
</style>
