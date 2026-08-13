<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { auditApi } from '@/api/modules'
import GlassCard from '@/v2/components/GlassCard.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'
import V2Field from '@/v2/components/V2Field.vue'
import { formatDate } from '@/v2/features/tasks/model'
const logs=ref<any[]>([]);const loading=ref(false);const userId=ref('');const action=ref('')
async function load(){loading.value=true;try{const params:any={};if(userId.value)params.user_id=Number(userId.value);if(action.value)params.action=action.value;logs.value=await auditApi.list(params)}finally{loading.value=false}}
onMounted(load)
</script>
<template><div class="v2-page"><div class="v2-page-heading heading"><div><StatusBadge tone="info">安全追踪</StatusBadge><h1>审计日志</h1><p>查询关键操作、操作者、目标对象及请求来源。</p></div><V2Button :disabled="loading" @click="load">刷新</V2Button></div><GlassCard padding="sm"><div class="filters"><V2Field label="用户 ID"><input v-model="userId" type="number" placeholder="全部用户"/></V2Field><V2Field label="操作类型"><input v-model="action" placeholder="如 task.cancel"/></V2Field><V2Button variant="primary" @click="load">查询</V2Button></div></GlassCard><div class="logs"><article v-for="log in logs" :key="log.id"><div><b>{{ log.action }}</b><small>{{ formatDate(log.created_at) }}</small></div><span>用户 #{{ log.user_id||'系统' }}</span><span>{{ log.target_type||'—' }} {{ log.target_id||'' }}</span><span>{{ log.ip||'—' }}</span><p v-if="log.detail">{{ typeof log.detail==='string'?log.detail:JSON.stringify(log.detail) }}</p></article><p v-if="!logs.length&&!loading" class="empty">暂无审计记录</p></div></div></template>
<style scoped>.heading{display:flex;align-items:flex-end;justify-content:space-between}.heading h1{margin-top:14px}.filters{display:grid;grid-template-columns:160px 1fr auto;align-items:end;gap:10px}.logs{margin-top:14px;overflow:hidden;background:var(--v2-surface);border:1px solid var(--v2-border);border-radius:var(--v2-radius-lg)}.logs article{min-height:64px;padding:11px 16px;display:grid;grid-template-columns:1fr 110px 180px 130px;align-items:center;gap:10px;border-bottom:1px solid var(--v2-border)}.logs article>div{display:grid;gap:4px}.logs small,.logs span,.logs p{color:var(--v2-text-muted);font-size:11px}.logs p{grid-column:1/5;margin:0}.empty{padding:60px;text-align:center;color:var(--v2-text-muted)}@media(max-width:700px){.filters{grid-template-columns:1fr 1fr}.logs article{margin:9px;grid-template-columns:1fr auto;border:1px solid var(--v2-border);border-radius:11px}.logs article>div,.logs p{grid-column:1/3}}</style>
