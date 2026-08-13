<script setup lang="ts">
withDefaults(defineProps<{ variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; disabled?: boolean; type?: 'button' | 'submit' }>(), { variant: 'secondary', type: 'button' })
</script>
<template><button :type="type" class="v2-button" :class="variant" :disabled="disabled"><slot /></button></template>
<style scoped>
.v2-button { min-height:40px; padding:0 16px; color:var(--v2-text); border:1px solid var(--v2-border); border-radius:var(--v2-radius-sm); background:var(--v2-surface-soft); cursor:pointer; transition:transform .15s ease, background .15s ease, border-color .15s ease; }.v2-button:hover:not(:disabled) { transform:translateY(-1px); border-color:var(--v2-border-strong); }.primary { background:linear-gradient(135deg,var(--v2-primary-strong),#865fee); border-color:transparent; }.ghost { background:transparent; }.danger { color:#ffdce1; background:rgba(255,127,145,.12); border-color:rgba(255,127,145,.25); }.v2-button:disabled { opacity:.45; cursor:not-allowed; }
</style>
