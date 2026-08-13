<script setup lang="ts">
defineProps<{ label: string; hint?: string; required?: boolean }>()
</script>
<template><label class="v2-field"><span class="field-label">{{ label }}<b v-if="required">*</b></span><slot /><small v-if="hint">{{ hint }}</small></label></template>
<style scoped>
.v2-field { display:grid; gap:8px; }.field-label { color:var(--v2-text); font-size:13px; font-weight:600; }.field-label b { color:var(--v2-danger); margin-left:4px; }.v2-field :deep(input),.v2-field :deep(select),.v2-field :deep(textarea) { width:100%; min-height:42px; padding:9px 12px; color:var(--v2-text); background:rgba(3,12,25,.42); border:1px solid var(--v2-border); border-radius:var(--v2-radius-sm); outline:none; }.v2-field :deep(input:focus),.v2-field :deep(select:focus),.v2-field :deep(textarea:focus) { border-color:var(--v2-primary); box-shadow:0 0 0 3px rgba(130,149,255,.12); }.v2-field small { color:var(--v2-text-subtle); line-height:1.5; }
</style>
