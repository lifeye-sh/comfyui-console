<script setup lang="ts">
defineProps<{ title?: string; description?: string }>()
</script>
<template>
  <section class="glass-panel">
    <header v-if="title || $slots.actions" class="panel-header"><div><h2 v-if="title">{{ title }}</h2><p v-if="description">{{ description }}</p></div><div><slot name="actions" /></div></header>
    <div class="panel-body"><slot /></div>
  </section>
</template>
<style scoped>
.glass-panel { overflow: hidden; background: var(--v2-surface); border: 1px solid var(--v2-border); border-radius: var(--v2-radius-lg); box-shadow: var(--v2-shadow-soft); backdrop-filter: blur(var(--v2-blur)); }
.panel-header { min-height: 68px; padding: 16px 20px; display:flex; align-items:center; justify-content:space-between; gap:16px; border-bottom:1px solid var(--v2-border); }
h2 { margin:0; font-size:17px; } p { margin:5px 0 0; color:var(--v2-text-muted); font-size:13px; }.panel-body { padding:20px; }
</style>
