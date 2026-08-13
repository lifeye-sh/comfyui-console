<script setup lang="ts">
defineProps<{ open: boolean; title: string }>()
const emit = defineEmits<{ close: [] }>()
</script>
<template>
  <Teleport to="body"><Transition name="drawer"><div v-if="open" class="drawer-layer v2-theme" @keydown.esc="emit('close')"><button class="drawer-backdrop" aria-label="关闭抽屉" @click="emit('close')" /><aside class="drawer-panel" role="dialog" aria-modal="true" :aria-label="title"><header><h2>{{ title }}</h2><button aria-label="关闭" @click="emit('close')">×</button></header><div class="drawer-body"><slot /></div></aside></div></Transition></Teleport>
</template>
<style scoped>
.drawer-layer { position:fixed; inset:0; z-index:1300; }.drawer-backdrop { position:absolute; inset:0; width:100%; border:0; background:rgba(1,6,15,.68); backdrop-filter:blur(5px); }.drawer-panel { position:absolute; top:0; right:0; width:min(460px, 94vw); height:100%; color:var(--v2-text); background:var(--v2-surface-strong); border-left:1px solid var(--v2-border); box-shadow:-20px 0 50px rgba(0,0,0,.35); backdrop-filter:blur(var(--v2-blur)); }.drawer-panel header { height:68px; padding:0 20px; display:flex; align-items:center; justify-content:space-between; border-bottom:1px solid var(--v2-border); }.drawer-panel h2 { margin:0; font-size:18px; }.drawer-panel header button { width:36px; height:36px; color:var(--v2-text); background:var(--v2-surface-soft); border:1px solid var(--v2-border); border-radius:10px; cursor:pointer; }.drawer-body { padding:20px; overflow:auto; height:calc(100% - 68px); }.drawer-enter-active,.drawer-leave-active { transition:opacity .2s ease; }.drawer-enter-from,.drawer-leave-to { opacity:0; }
</style>
