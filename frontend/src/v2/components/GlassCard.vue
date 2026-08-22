<script setup lang="ts">
withDefaults(defineProps<{ padding?: 'none' | 'sm' | 'md' | 'lg'; interactive?: boolean }>(), { padding: 'md', interactive: false })
</script>
<template><section class="glass-card" :class="[`pad-${padding}`, { interactive }]"><slot /></section></template>
<style scoped>
.glass-card { background: var(--v2-surface); border: 1px solid var(--v2-border); border-radius: var(--v2-radius-lg); box-shadow: var(--v2-shadow-soft); backdrop-filter: blur(var(--v2-blur)); }
.pad-none { padding: 0; }.pad-sm { padding: var(--v2-space-4); }.pad-md { padding: var(--v2-space-6); }.pad-lg { padding: var(--v2-space-8); }
.interactive { transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease; }
.interactive:hover { transform: translateY(-2px); border-color: var(--v2-border-strong); box-shadow: var(--v2-shadow); }
</style>
