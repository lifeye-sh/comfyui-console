<script setup lang="ts">
import AssetPicker from '@/v2/components/AssetPicker.vue'
import type { ResourceItem } from './model'
import { ref, onMounted } from 'vue'
const open=ref(false)
onMounted(()=>{open.value=true})
function finish(items:ResourceItem[] = []) {
  const item = items[0]
  window.parent.postMessage({type:'gallery-resource-picked', item:item && {id:item.id,name:item.filename}}, location.origin)
}
</script>
<template><div class="v2-theme"><AssetPicker :open="open" media-type="image" @close="finish()" @select="finish"/></div></template>
