<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { shortDramaApi } from '@/api/modules'
import GlassCard from '@/v2/components/GlassCard.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'

const router = useRouter()
const step = ref(1)
const loading = ref(false)
const error = ref('')
const starts = [
  { value: 'idea', icon: '✦', title: '一句话创意', description: '通过引导问答补全人物、冲突和结局方向。' },
  { value: 'outline', icon: '≡', title: '故事大纲', description: '从已有梗概规划分集、场景和剧情节拍。' },
  { value: 'script', icon: '▤', title: '完整剧本', description: '解析场景、人物、动作、对白和转场。' },
  { value: 'novel', icon: '◇', title: '小说或文档', description: '后续可导入 TXT、DOCX、EPUB 进入改编流程。' },
] as const
const form = reactive({
  source_type: 'idea' as 'idea'|'outline'|'script'|'novel', name: '', synopsis: '', genre: '', audience: '', tone: '', platform: '', aspect_ratio: '9:16', episode_count: 1, episode_duration: 60, quality_tier: 'draft' as 'draft'|'standard'|'final', visual_style: '',
})
const selected = computed(() => starts.find((item) => item.value === form.source_type))

function choose(value: typeof form.source_type) { form.source_type = value; step.value = 2; error.value = '' }
async function submit() {
  if (!form.name.trim()) { error.value = '请输入短剧名称'; return }
  loading.value = true; error.value = ''
  try {
    const project = await shortDramaApi.createProject({
      name: form.name.trim(), synopsis: form.synopsis.trim(), source_type: form.source_type,
      brief: { genre: form.genre, audience: form.audience, tone: form.tone, platform: form.platform, aspect_ratio: form.aspect_ratio, episode_count: Number(form.episode_count), episode_duration: Number(form.episode_duration), quality_tier: form.quality_tier, visual_style: form.visual_style, constraints: {} },
    })
    router.replace(`/v2/drama/projects/${project.id}`)
  } catch (event: any) { error.value = event.response?.data?.message || '项目创建失败' }
  finally { loading.value = false }
}
</script>

<template>
  <div class="v2-page create-page">
    <div class="v2-page-heading"><StatusBadge tone="info">步骤 {{ step }} / 2</StatusBadge><h1>{{ step===1?'你想从哪里开始？':'创建短剧项目' }}</h1><p>{{ step===1?'选择创作起点，后续仍可在项目中修改。':`创作起点：${selected?.title}` }}</p></div>
    <div v-if="step===1" class="start-grid"><GlassCard v-for="item in starts" :key="item.value" interactive padding="lg" @click="choose(item.value)"><span class="start-icon">{{ item.icon }}</span><h2>{{ item.title }}</h2><p>{{ item.description }}</p><b>选择此方式 →</b></GlassCard></div>
    <form v-else class="project-form" @submit.prevent="submit">
      <GlassCard padding="lg"><h2>项目信息</h2><div class="field-grid"><label><span>短剧名称 *</span><input v-model="form.name" maxlength="160" placeholder="例如：迷雾档案"></label><label><span>题材类型</span><input v-model="form.genre" maxlength="64" placeholder="悬疑、都市、情感…"></label><label class="wide"><span>故事简介</span><textarea v-model="form.synopsis" rows="4" placeholder="用几句话说明主角、冲突和故事目标"></textarea></label><label><span>目标受众</span><input v-model="form.audience" placeholder="例如：18-35 岁观众"></label><label><span>内容基调</span><input v-model="form.tone" placeholder="紧张、轻松、治愈…"></label><label><span>目标平台</span><input v-model="form.platform" placeholder="抖音、视频号、横屏平台…"></label><label><span>视觉方向</span><input v-model="form.visual_style" placeholder="写实电影感、二维动画…"></label></div></GlassCard>
      <GlassCard padding="lg"><h2>成片规格</h2><div class="field-grid specs"><label><span>画面比例</span><select v-model="form.aspect_ratio"><option>9:16</option><option>16:9</option><option>1:1</option><option>4:3</option></select></label><label><span>预计集数</span><input v-model.number="form.episode_count" type="number" min="1" max="999"></label><label><span>单集时长（秒）</span><input v-model.number="form.episode_duration" type="number" min="1" max="7200"></label><label><span>质量档位</span><select v-model="form.quality_tier"><option value="draft">草稿</option><option value="standard">标准</option><option value="final">成片</option></select></label></div></GlassCard>
      <p v-if="error" class="error">{{ error }}</p><div class="actions"><V2Button variant="ghost" @click="step=1">上一步</V2Button><V2Button type="submit" variant="primary" :disabled="loading">{{ loading?'正在创建…':'创建项目' }}</V2Button></div>
    </form>
  </div>
</template>

<style scoped>
.v2-page-heading h1{margin-top:14px}.start-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.start-grid .glass-card{display:grid;gap:12px;min-height:220px;cursor:pointer}.start-grid h2,.start-grid p{margin:0}.start-grid p{color:var(--v2-text-muted);line-height:1.7}.start-grid b{margin-top:auto;color:var(--v2-info);font-size:13px}.start-icon{width:48px;height:48px;display:grid;place-items:center;border:1px solid var(--v2-border);border-radius:15px;background:var(--v2-surface-soft);font-size:22px}.project-form{display:grid;gap:16px}.project-form h2{margin:0 0 18px}.field-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.field-grid label{display:grid;gap:7px}.field-grid label>span{color:var(--v2-text-muted);font-size:13px}.field-grid input,.field-grid textarea,.field-grid select{width:100%;padding:11px 12px;color:var(--v2-text);background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:10px;outline:none}.field-grid textarea{resize:vertical}.field-grid input:focus,.field-grid textarea:focus,.field-grid select:focus{border-color:var(--v2-primary)}.field-grid .wide{grid-column:1/-1}.specs{grid-template-columns:repeat(4,minmax(0,1fr))}.error{padding:12px;color:var(--v2-danger);background:rgba(255,127,145,.08);border:1px solid rgba(255,127,145,.2);border-radius:10px}.actions{display:flex;justify-content:flex-end;gap:10px}@media(max-width:760px){.start-grid,.field-grid,.specs{grid-template-columns:1fr}.field-grid .wide{grid-column:auto}.actions .v2-button{flex:1}}
</style>
