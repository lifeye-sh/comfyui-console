<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { shortDramaApi } from '@/api/modules'
import GlassCard from '@/v2/components/GlassCard.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'

const router = useRouter()
const step = ref(1)
const loading = ref(false)
const error = ref('')
const name = ref('')
const sourceType = ref<'idea'|'outline'|'script'|'novel'>('idea')
const starts = [
  { value: 'idea', icon: '✦', title: '一句话创意', description: '通过引导问答补全人物、冲突和结局方向。' },
  { value: 'outline', icon: '≡', title: '故事大纲', description: '从已有梗概规划分集、场景和剧情节拍。' },
  { value: 'script', icon: '▤', title: '完整剧本', description: '解析场景、人物、动作、对白和转场。' },
  { value: 'novel', icon: '◇', title: '小说或文档', description: '后续可导入 TXT、DOCX、EPUB 进入改编流程。' },
] as const
const selected = computed(() => starts.find((item) => item.value === sourceType.value))

function choose(value: typeof sourceType.value) { sourceType.value = value; step.value = 2; error.value = '' }
async function submit() {
  if (!name.value.trim()) { error.value = '请输入短剧名称'; return }
  loading.value = true; error.value = ''
  try {
    const project = await shortDramaApi.createProject({ name: name.value.trim(), source_type: sourceType.value })
    router.replace(`/v2/drama/projects/${project.id}`)
  } catch (event: any) { error.value = event.response?.data?.detail || event.response?.data?.message || '项目创建失败' }
  finally { loading.value = false }
}
</script>

<template>
  <div class="v2-page create-page">
    <div class="v2-page-heading"><StatusBadge tone="info">步骤 {{ step }} / 2</StatusBadge><h1>{{ step===1?'你想从哪里开始？':'创建短剧项目' }}</h1><p>{{ step===1?'选择创作起点，后续仍可在项目中修改。':`创作起点：${selected?.title}` }}</p></div>
    <div v-if="step===1" class="start-grid"><GlassCard v-for="item in starts" :key="item.value" interactive padding="lg" @click="choose(item.value)"><span class="start-icon">{{ item.icon }}</span><h2>{{ item.title }}</h2><p>{{ item.description }}</p><b>选择此方式 →</b></GlassCard></div>
    <form v-else class="project-form" @submit.prevent="submit">
      <GlassCard padding="lg"><h2>项目信息</h2><div class="field-grid"><label class="wide"><span>短剧名称 *</span><input v-model="name" maxlength="160" placeholder="例如：迷雾档案" autofocus></label></div><p class="hint">题材类型、目标受众、内容基调、视觉方向、成片规格等，都会在后续导入故事文档时由 AI 分析并给出建议，届时再确认即可。</p></GlassCard>
      <p v-if="error" class="error">{{ error }}</p><div class="actions"><V2Button variant="ghost" @click="step=1">上一步</V2Button><V2Button type="submit" variant="primary" :disabled="loading || !name.trim()">{{ loading?'正在创建…':'创建项目' }}</V2Button></div>
    </form>
  </div>
</template>

<style scoped>
.v2-page-heading h1{margin-top:14px}.start-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.start-grid .glass-card{display:grid;gap:12px;min-height:220px;cursor:pointer}.start-grid h2,.start-grid p{margin:0}.start-grid p{color:var(--v2-text-muted);line-height:1.7}.start-grid b{margin-top:auto;color:var(--v2-info);font-size:13px}.start-icon{width:48px;height:48px;display:grid;place-items:center;border:1px solid var(--v2-border);border-radius:15px;background:var(--v2-surface-soft);font-size:22px}.project-form{display:grid;gap:16px}.project-form h2{margin:0 0 18px}.field-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.field-grid label{display:grid;gap:7px}.field-grid label>span{color:var(--v2-text-muted);font-size:13px}.field-grid input{width:100%;padding:11px 12px;color:var(--v2-text);background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:10px;outline:none}.field-grid input:focus{border-color:var(--v2-primary)}.field-grid .wide{grid-column:1/-1}.hint{margin:4px 0 0;color:var(--v2-text-subtle);font-size:12px;line-height:1.7}.error{padding:12px;color:var(--v2-danger);background:rgba(255,127,145,.08);border:1px solid rgba(255,127,145,.2);border-radius:10px}.actions{display:flex;justify-content:flex-end;gap:10px}@media(max-width:760px){.start-grid,.field-grid{grid-template-columns:1fr}.field-grid .wide{grid-column:auto}.actions .v2-button{flex:1}}
</style>
