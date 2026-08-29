<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { shortDramaApi, type AdaptationCandidate } from '@/api/modules'
import GlassPanel from '@/v2/components/GlassPanel.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'

const props = defineProps<{ projectId: number }>()
const emit = defineEmits<{ (e: 'edit-prompt', code: string, title: string): void; (e: 'skip'): void; (e: 'job-created'): void }>()

const candidates = ref<AdaptationCandidate[]>([])
const loading = ref(false)
const generating = ref(false)
const confirmingId = ref<number | null>(null)
const error = ref('')
const expandedCandidate = ref<number | null>(null)
const expandedEpisodes = ref(new Set<string>())
const analyses = ref<any[]>([])

async function load() {
  loading.value = true; error.value = ''
  try {
    candidates.value = await shortDramaApi.candidates(props.projectId) as AdaptationCandidate[]
    if (!analyses.value.length) {
      analyses.value = await shortDramaApi.novelAnalyses(props.projectId) as any[]
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally { loading.value = false }
}

const confirmedAnalysis = computed(() => analyses.value.find(a => a.status === 'confirmed'))

async function generateAdaptation() {
  generating.value = true; error.value = ''
  try {
    const analysis = confirmedAnalysis.value
    if (!analysis) { error.value = '请先在步骤 0 确认一个分析版本'; return }
    await shortDramaApi.generateAIAdaptation(props.projectId, {
      analysis_id: analysis.id,
      episode_count: 8,
      strategies: ['faithful', 'high_tempo', 'emotional'],
      idempotency_key: crypto.randomUUID(),
    })
    emit('job-created')
    pollCandidates()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '改编生成任务启动失败'
    generating.value = false
  }
}

let pollTimer: ReturnType<typeof setTimeout> | null = null
function pollCandidates(attempts = 0) {
  if (pollTimer) clearTimeout(pollTimer)
  if (attempts > 30) { generating.value = false; error.value = '改编生成超时，请检查 AI 配置'; return }
  pollTimer = setTimeout(async () => {
    try {
      await load()
      const hasNew = candidates.value.some(c => c.status === 'pending')
      if (hasNew) {
        generating.value = false
      } else {
        pollCandidates(attempts + 1)
      }
    } catch {
      pollCandidates(attempts + 1)
    }
  }, 2000)
}

async function confirm(candidate: AdaptationCandidate, optionKey: string) {
  confirmingId.value = candidate.id; error.value = ''
  try {
    await shortDramaApi.confirmCandidate(props.projectId, candidate.id, {
      option_key: optionKey,
      version_name: `改编版本 ${optionKey}`,
    })
    await load()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '确认失败'
  } finally { confirmingId.value = null }
}

function toggle(id: number) {
  expandedCandidate.value = expandedCandidate.value === id ? null : id
}

function toggleEpisode(key: string) {
  if (expandedEpisodes.value.has(key)) expandedEpisodes.value.delete(key)
  else expandedEpisodes.value.add(key)
}

const statusTone = (s: string) => s === 'confirmed' ? 'success' : s === 'invalid' ? 'danger' : 'info'
const statusLabel = (s: string) => s === 'confirmed' ? '已确认' : s === 'invalid' ? '校验失败' : s === 'pending' ? '待确认' : s

const ELEMENT_TYPE_LABEL: Record<string, string> = {
  action: '动作', dialogue: '对白', narration: '旁白', transition: '转场',
}
function elementLabel(type: string): string {
  return ELEMENT_TYPE_LABEL[type] || type || '元素'
}
function episodeScenes(ep: any): any[] {
  const scenes = ep?.scenes
  return Array.isArray(scenes) ? scenes : []
}
function sceneElements(scene: any): any[] {
  const elements = scene?.elements
  return Array.isArray(elements) ? elements : []
}

onMounted(() => void load())
watch(() => props.projectId, () => void load())
</script>

<template>
  <GlassPanel
    title="改编候选确认"
    description="基于已确认的小说分析，AI 生成多个改编方案（集数/节奏/策略不同）。确认一个方案后进入步骤 3 场景台账。"
  >
    <template #actions>
      <div class="adapt-actions-row">
        <V2Button variant="primary" :disabled="generating || !confirmedAnalysis" @click="generateAdaptation">
          {{ generating ? 'AI 生成中…' : 'AI 生成改编方案' }}
        </V2Button>
        <V2Button variant="ghost" @click="emit('edit-prompt', 'novel_adaptation', '改编方案生成')">📝</V2Button>
      </div>
    </template>

    <div v-if="error" class="adapt-error">{{ error }}</div>

    <div class="adapt-skip-box">
      <p>如果不需要改编（直接使用原始分析进入场景台账），可以跳过此步骤。</p>
      <V2Button variant="ghost" size="sm" @click="emit('skip')">跳过改编 →</V2Button>
    </div>

    <div v-if="!confirmedAnalysis" class="adapt-empty">
      需要先在步骤 0 确认一个分析版本后才能生成改编方案。
    </div>

    <div v-else-if="!candidates.length && !generating" class="adapt-empty">
      还没有改编候选。点击「AI 生成改编方案」开始。
    </div>

    <div v-else class="adapt-list">
      <div v-for="c in candidates" :key="c.id" class="adapt-card">
        <!-- 候选头 -->
        <div class="adapt-head" @click="toggle(c.id)">
          <div class="adapt-meta">
            <strong>候选 #{{ c.id }}</strong>
            <small>章节 {{ c.chapter_start }}-{{ c.chapter_end }}</small>
          </div>
          <span class="adapt-options-count">{{ c.options?.length || 0 }} 个方案</span>
          <StatusBadge :tone="statusTone(c.status)">{{ statusLabel(c.status) }}</StatusBadge>
          <button class="adapt-toggle">{{ expandedCandidate === c.id ? '−' : '+' }}</button>
        </div>

        <!-- 校验错误 -->
        <div v-if="c.validation_errors?.length" class="adapt-errors">
          <small v-for="(err, i) in c.validation_errors" :key="i" class="danger">⚠ {{ err.message || JSON.stringify(err) }}</small>
        </div>

        <!-- 展开详情：完整方案 -->
        <div v-if="expandedCandidate === c.id" class="adapt-body">
          <div v-for="opt in c.options" :key="opt.key" class="option-card">
            <!-- 方案头 -->
            <div class="option-head">
              <div class="option-title">
                <strong>{{ opt.label }}</strong>
                <p class="option-desc">{{ opt.description }}</p>
              </div>
              <div class="option-metrics">
                <span>{{ opt.metrics?.episode_count || '?' }} 集</span>
                <span>{{ opt.metrics?.source_chapters || '?' }} 章</span>
                <span>节奏 {{ opt.metrics?.pace_ratio || '?' }}x</span>
              </div>
            </div>

            <!-- 完整分集列表 -->
            <div v-if="opt.episodes?.length" class="episodes-full">
              <div v-for="(ep, epIdx) in opt.episodes" :key="epIdx" class="episode-card">
                <div class="episode-head" @click="toggleEpisode(`${c.id}-${opt.key}-${epIdx}`)">
                  <span class="episode-no">第 {{ epIdx + 1 }} 集</span>
                  <strong class="episode-title">{{ (ep as any).title || '未命名' }}</strong>
                  <small v-if="(ep as any).target_duration" class="episode-duration">{{ (ep as any).target_duration }}s</small>
                  <span class="episode-scene-count">{{ episodeScenes(ep).length }} 场景</span>
                  <button class="episode-toggle">{{ expandedEpisodes.has(`${c.id}-${opt.key}-${epIdx}`) ? '−' : '+' }}</button>
                </div>

                <!-- 分集详情 -->
                <div v-if="expandedEpisodes.has(`${c.id}-${opt.key}-${epIdx}`)" class="episode-body">
                  <p v-if="(ep as any).synopsis" class="episode-synopsis">{{ (ep as any).synopsis }}</p>

                  <!-- 场景列表 -->
                  <div class="scenes-list">
                    <div v-for="(scene, scIdx) in episodeScenes(ep)" :key="scIdx" class="scene-card">
                      <div class="scene-head">
                        <span class="scene-no">场景 {{ scIdx + 1 }}</span>
                        <strong class="scene-heading">{{ (scene as any).heading || '未命名' }}</strong>
                        <small class="scene-meta">
                          {{ (scene as any).location_name || '—' }}
                          <template v-if="(scene as any).time_of_day"> · {{ (scene as any).time_of_day }}</template>
                          <template v-if="(scene as any).interior_exterior"> · {{ (scene as any).interior_exterior === 'interior' ? '内景' : (scene as any).interior_exterior === 'exterior' ? '外景' : (scene as any).interior_exterior }}</template>
                        </small>
                      </div>
                      <p v-if="(scene as any).content" class="scene-content">{{ (scene as any).content }}</p>
                      <!-- 元素列表 -->
                      <div v-if="sceneElements(scene).length" class="elements-list">
                        <div v-for="(el, elIdx) in sceneElements(scene)" :key="elIdx" class="element-row" :class="'el-' + ((el as any).type || '')">
                          <span class="element-type">{{ elementLabel((el as any).type) }}</span>
                          <span class="element-text">{{ (el as any).text }}</span>
                        </div>
                      </div>
                    </div>
                    <div v-if="!episodeScenes(ep).length" class="no-scenes">该集暂未生成场景。</div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 确认按钮 -->
            <div class="option-actions">
              <V2Button
                v-if="c.status === 'pending'"
                variant="primary" size="sm"
                :disabled="confirmingId === c.id"
                @click="confirm(c, opt.key)"
              >
                {{ confirmingId === c.id ? '确认中…' : '确认此方案' }}
              </V2Button>
              <StatusBadge v-else-if="c.confirmed_option === opt.key" tone="success">已采用</StatusBadge>
            </div>
          </div>
        </div>

        <div v-else-if="c.status === 'pending'" class="adapt-hint">
          点击 + 展开查看完整方案（所有分集与场景）
        </div>
      </div>
    </div>
  </GlassPanel>
</template>

<style scoped>
.adapt-error{padding:10px 12px;color:#ffdce1;background:rgba(255,127,145,.1);border-radius:10px;font-size:12px;margin-bottom:10px}
.adapt-actions-row{display:flex;gap:8px;align-items:center}
.adapt-skip-box{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 14px;margin-bottom:12px;background:rgba(255,183,77,.06);border:1px solid rgba(255,183,77,.15);border-radius:10px}
.adapt-skip-box p{margin:0;color:var(--v2-text-subtle);font-size:11px}
.adapt-empty{color:var(--v2-text-subtle);font-size:12px;padding:16px 0;text-align:center}
.adapt-list{display:grid;gap:12px}
.adapt-card{background:rgba(130,149,255,.04);border:1px solid var(--v2-border);border-radius:12px;overflow:hidden}
.adapt-head{display:flex;align-items:center;gap:10px;padding:12px 14px;cursor:pointer;user-select:none}
.adapt-head:hover{background:rgba(130,149,255,.06)}
.adapt-meta{display:grid;gap:2px;flex-shrink:0;min-width:110px}
.adapt-meta strong{font-size:12px;color:var(--v2-text)}
.adapt-meta small{color:var(--v2-text-muted);font-size:10px}
.adapt-options-count{flex:1;font-size:11px;color:var(--v2-text-subtle)}
.adapt-toggle{width:26px;height:26px;display:grid;place-items:center;color:var(--v2-text-muted);background:none;border:1px solid var(--v2-border);border-radius:7px;cursor:pointer;font-size:14px;flex-shrink:0}
.adapt-toggle:hover{color:var(--v2-text);border-color:var(--v2-primary)}
.adapt-errors{padding:0 14px 8px;display:grid;gap:3px}
.adapt-errors .danger{color:var(--v2-danger);font-size:11px}
.adapt-body{padding:0 14px 14px;border-top:1px solid var(--v2-border);display:grid;gap:12px;padding-top:12px}
.option-card{padding:12px;background:rgba(0,0,0,.12);border:1px solid var(--v2-border);border-radius:10px;display:grid;gap:12px}
.option-head{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
.option-title{flex:1;min-width:200px}
.option-head strong{font-size:13px;color:var(--v2-text)}
.option-desc{margin:4px 0 0;font-size:11px;color:var(--v2-text-muted);line-height:1.6}
.option-metrics{display:flex;gap:10px;flex-shrink:0;font-size:11px;color:var(--v2-primary);font-weight:600}
.option-metrics span{white-space:nowrap}

/* 完整分集列表 */
.episodes-full{display:grid;gap:8px}
.episode-card{background:rgba(0,0,0,.15);border:1px solid var(--v2-border);border-radius:9px;overflow:hidden}
.episode-head{display:flex;align-items:center;gap:8px;padding:9px 12px;cursor:pointer;user-select:none}
.episode-head:hover{background:rgba(130,149,255,.05)}
.episode-no{font-size:10px;color:var(--v2-primary);font-weight:600;white-space:nowrap}
.episode-title{flex:1;min-width:0;font-size:12px;color:var(--v2-text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.episode-duration{font-size:10px;color:var(--v2-text-subtle);white-space:nowrap}
.episode-scene-count{font-size:10px;color:var(--v2-text-subtle);white-space:nowrap}
.episode-toggle{width:22px;height:22px;display:grid;place-items:center;color:var(--v2-text-muted);background:none;border:1px solid var(--v2-border);border-radius:6px;cursor:pointer;font-size:12px;flex-shrink:0}
.episode-body{padding:0 12px 12px;border-top:1px solid var(--v2-border);padding-top:10px;display:grid;gap:10px}
.episode-synopsis{margin:0;font-size:11px;color:var(--v2-text-muted);line-height:1.6}

/* 场景列表 */
.scenes-list{display:grid;gap:8px}
.scene-card{padding:9px 11px;background:rgba(0,0,0,.12);border:1px solid var(--v2-border);border-radius:8px;display:grid;gap:6px}
.scene-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.scene-no{font-size:10px;color:var(--v2-primary);font-weight:600;white-space:nowrap}
.scene-heading{font-size:12px;color:var(--v2-text)}
.scene-meta{font-size:10px;color:var(--v2-text-subtle)}
.scene-content{margin:0;font-size:11px;color:var(--v2-text-muted);line-height:1.6}
.elements-list{display:grid;gap:3px}
.element-row{display:flex;gap:8px;font-size:11px;line-height:1.5;padding:3px 6px;border-radius:5px;background:rgba(0,0,0,.1)}
.element-type{flex-shrink:0;font-size:9px;color:var(--v2-primary);font-weight:600;padding:1px 5px;border:1px solid rgba(130,149,255,.2);border-radius:4px}
.element-text{color:var(--v2-text-muted)}
.element-row.el-dialogue .element-text{color:#a8c7ff}
.element-row.el-narration .element-text{color:#c9b8ff}
.no-scenes{font-size:11px;color:var(--v2-text-subtle);padding:4px 0}

.option-actions{display:flex;align-items:center;gap:8px}
.adapt-hint{padding:0 14px 10px;color:var(--v2-text-subtle);font-size:11px}
</style>