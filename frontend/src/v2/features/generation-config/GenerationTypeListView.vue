<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { genTypeApi, generationTypeConfigApi } from '@/api/modules'
import GlassCard from '@/v2/components/GlassCard.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'
import V2Field from '@/v2/components/V2Field.vue'

const router = useRouter()
const items = ref<any[]>([])
const keyword = ref('')
const media = ref('')
const state = ref('')
const loading = ref(true)
const message = ref('')

const filtered = computed(() => items.value.filter((item) => {
  const matchesKeyword = !keyword.value || `${item.name} ${item.code}`.toLowerCase().includes(keyword.value.toLowerCase())
  return matchesKeyword && (!media.value || item.media_type === media.value) && (!state.value || String(item.enabled) === state.value)
}))

async function load() {
  loading.value = true
  try { items.value = await genTypeApi.list() } finally { loading.value = false }
}
async function toggle(item: any) {
  if (item.enabled && !confirm(`停用“${item.name}”后将不能创建新任务，是否继续？`)) return
  if (item.enabled) await generationTypeConfigApi.deactivate(item.id)
  else await genTypeApi.patch(item.id, { enabled: true })
  message.value = item.enabled ? '生成类型已停用' : '生成类型已启用'
  await load()
}
onMounted(load)
</script>

<template>
  <div class="v2-page">
    <div class="v2-page-heading heading"><div><StatusBadge tone="info">Iteration 6</StatusBadge><h1>生成类型配置</h1><p>通过版本化配置管理生成页面、参数、工作流与输出规则。</p></div></div>
    <GlassCard padding="sm"><div class="filters"><V2Field label="搜索"><input v-model="keyword" placeholder="名称或编码" /></V2Field><V2Field label="媒体类型"><select v-model="media"><option value="">全部</option><option value="image">图片</option><option value="video">视频</option><option value="audio">音频</option></select></V2Field><V2Field label="状态"><select v-model="state"><option value="">全部</option><option value="true">已启用</option><option value="false">已停用</option></select></V2Field></div></GlassCard>
    <p v-if="message" class="message">{{ message }}</p>
    <div v-if="loading" class="empty">加载中…</div>
    <div v-else class="type-grid">
      <GlassCard v-for="item in filtered" :key="item.id" interactive>
        <header><span class="media-icon">{{ item.media_type==='image'?'▧':item.media_type==='video'?'▷':'♫' }}</span><div><h3>{{ item.name }}</h3><code>{{ item.code }}</code></div><StatusBadge :tone="item.enabled?'success':'neutral'">{{ item.enabled?'已启用':'已停用' }}</StatusBadge></header>
        <dl><div><dt>媒体类型</dt><dd>{{ item.media_type }}</dd></div><div><dt>菜单顺序</dt><dd>{{ item.menu_order }}</dd></div><div><dt>发布版本</dt><dd>{{ item.published_config_version_id ? `#${item.published_config_version_id}` : '尚未发布' }}</dd></div><div><dt>默认工作流</dt><dd>{{ item.default_workflow_id ? `#${item.default_workflow_id}` : '未配置' }}</dd></div></dl>
        <footer><V2Button variant="primary" @click="router.push(`/v2/settings/generation-types/${item.id}`)">配置</V2Button><V2Button :variant="item.enabled?'danger':'secondary'" @click="toggle(item)">{{ item.enabled?'停用':'启用' }}</V2Button></footer>
      </GlassCard>
      <p v-if="!filtered.length" class="empty">没有符合条件的生成类型</p>
    </div>
  </div>
</template>

<style scoped>
.heading h1{margin-top:14px}.filters{display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px}.type-grid{margin-top:16px;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.type-grid header{display:flex;align-items:center;gap:12px}.type-grid header>div{flex:1}.type-grid h3{margin:0 0 5px}.type-grid code{color:var(--v2-text-subtle)}.media-icon{width:42px;height:42px;display:grid;place-items:center;border-radius:12px;background:rgba(130,149,255,.14);font-size:20px}.type-grid dl{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:20px 0}.type-grid dl div{padding:10px;background:var(--v2-surface-soft);border-radius:10px}.type-grid dt{color:var(--v2-text-subtle);font-size:11px}.type-grid dd{margin:5px 0 0}.type-grid footer{display:flex;gap:8px}.message{color:var(--v2-success)}.empty{text-align:center;color:var(--v2-text-muted);grid-column:1/-1}@media(max-width:1050px){.type-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:700px){.filters,.type-grid{grid-template-columns:1fr}}
</style>
