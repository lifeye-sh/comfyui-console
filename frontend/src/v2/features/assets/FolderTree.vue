<script setup lang="ts">
import { computed } from 'vue'
import type { FolderNode } from './model'
const props=defineProps<{tree:FolderNode[];currentId:number|null;expanded:Set<number>}>()
const emit=defineEmits<{select:[number];toggle:[number]}>()
type Row={node:FolderNode;depth:number};const rows=computed(()=>{const out:Row[]=[];const walk=(nodes:FolderNode[],depth=0)=>nodes.forEach(node=>{out.push({node,depth});if(props.expanded.has(node.id))walk(node.children||[],depth+1)});walk(props.tree);return out})
</script>
<template><nav class="folder-tree" aria-label="素材目录"><button v-for="row in rows" :key="row.node.id" :class="{active:currentId===row.node.id}" :style="{paddingLeft:`${10+row.depth*17}px`}" @click="emit('select',row.node.id)"><span class="caret" @click.stop="row.node.children?.length&&emit('toggle',row.node.id)">{{ row.node.children?.length?(expanded.has(row.node.id)?'⌄':'›'):'·' }}</span><span class="folder">{{ row.node.folder_type==='normal'?'◇':'▣' }}</span><b>{{ row.node.name }}</b><small>{{ row.node.resource_count }}</small></button></nav></template>
<style scoped>.folder-tree{display:grid;gap:2px}.folder-tree button{min-height:39px;padding-right:8px;display:flex;align-items:center;gap:7px;color:var(--v2-text-muted);background:transparent;border:1px solid transparent;border-radius:10px;text-align:left;cursor:pointer}.folder-tree button:hover,.folder-tree button.active{color:var(--v2-text);background:var(--v2-surface-soft);border-color:var(--v2-border)}.caret{width:28px;height:28px;display:grid;place-items:center;flex-shrink:0;cursor:pointer;border-radius:6px}.caret:hover{background:rgba(130,149,255,0.12)}.folder{color:var(--v2-primary)}b{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}small{color:var(--v2-text-subtle)}
@media(max-width:700px){.folder-tree button{min-height:44px}.caret{width:36px;height:36px}b{font-size:13px}small{font-size:12px}}</style>
