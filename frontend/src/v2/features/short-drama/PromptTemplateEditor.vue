<script setup lang="ts">
import { ref, watch } from 'vue'
import { shortDramaApi } from '@/api/modules'
import V2Button from '@/v2/components/V2Button.vue'

const props = defineProps<{ visible: boolean; code: string; title: string }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const template = ref<any>(null)
const editing = ref(false)
const systemPrompt = ref('')
const userPrompt = ref('')
const saving = ref(false)
const error = ref('')

const CODE_LABELS: Record<string, string> = {
  novel_chunk_analysis: '小说分块分析',
  novel_analysis_merge: '分析合并',
  novel_adaptation: '改编方案生成',
  episode_screenplay: '单集剧本生成',
  director_story_ledger: '故事台账生成',
  json_repair: 'JSON 修复',
}

async function load() {
  if (!props.visible || !props.code) return
  error.value = ''
  try {
    const items = await shortDramaApi.promptTemplates(props.code) as any[]
    if (items.length) {
      template.value = items[0]
      systemPrompt.value = items[0].system_prompt
      userPrompt.value = items[0].user_prompt
    } else {
      template.value = null
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  }
}

function startEdit() {
  if (!template.value) return
  editing.value = true
  systemPrompt.value = template.value.system_prompt
  userPrompt.value = template.value.user_prompt
}

function cancelEdit() {
  editing.value = false
  if (template.value) {
    systemPrompt.value = template.value.system_prompt
    userPrompt.value = template.value.user_prompt
  }
}

async function save() {
  if (!template.value) return
  saving.value = true; error.value = ''
  try {
    const result = await shortDramaApi.updatePromptTemplate(template.value.id, {
      system_prompt: systemPrompt.value,
      user_prompt: userPrompt.value,
    })
    template.value = result
    editing.value = false
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '保存失败'
  } finally { saving.value = false }
}

watch(() => props.visible, (v) => { if (v) { void load(); editing.value = false } })
watch(() => props.code, () => { if (props.visible) { void load(); editing.value = false } })
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="ptm-overlay v2-theme" @click.self="emit('close')">
      <div class="ptm-dialog">
        <div class="ptm-head">
          <div>
            <b>📝 提示词管理</b>
            <small>{{ title || CODE_LABELS[code] || code }}</small>
          </div>
          <button class="ptm-close" @click="emit('close')">✕</button>
        </div>

        <div v-if="error" class="ptm-error">{{ error }}</div>

        <div v-if="!template && !error" class="ptm-empty">
          该操作没有关联的提示词模板（可能使用内置硬编码 prompt）。
        </div>

        <div v-else-if="template" class="ptm-body">
          <div class="ptm-meta">
            <span>代码：<code>{{ template.code }}</code></span>
            <span>名称：{{ template.name }}</span>
            <span>v{{ template.version }}</span>
            <StatusBadge tone="success" v-if="template.enabled">已启用</StatusBadge>
          </div>

          <div class="ptm-field">
            <label>系统提示词（System Prompt）</label>
            <textarea
              v-model="systemPrompt"
              :readonly="!editing"
              class="ptm-textarea ptm-system"
              rows="6"
            />
          </div>

          <div class="ptm-field">
            <label>用户提示词模板（User Prompt · 支持 {变量名} 占位符）</label>
            <textarea
              v-model="userPrompt"
              :readonly="!editing"
              class="ptm-textarea ptm-user"
              rows="10"
            />
          </div>

          <div class="ptm-actions">
            <template v-if="!editing">
              <V2Button variant="ghost" size="sm" @click="startEdit">编辑</V2Button>
              <small class="ptm-hint">编辑后保存会创建新版本，旧版本自动停用</small>
            </template>
            <template v-else>
              <V2Button variant="primary" size="sm" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存新版本' }}</V2Button>
              <V2Button variant="ghost" size="sm" @click="cancelEdit">取消</V2Button>
            </template>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script lang="ts">
import StatusBadge from '@/v2/components/StatusBadge.vue'
export default { components: { StatusBadge } }
</script>

<style scoped>
.ptm-overlay{position:fixed;inset:0;z-index:100;background:rgba(4,10,22,.72);backdrop-filter:blur(4px);display:flex;align-items:flex-start;justify-content:center;padding:60px 20px;overflow-y:auto}
.ptm-dialog{width:min(720px,94vw);background:#0c1930;border:1px solid var(--v2-border-strong);border-radius:16px;box-shadow:0 16px 48px rgba(0,0,0,.5);overflow:hidden}
.ptm-head{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid var(--v2-border)}
.ptm-head b{font-size:14px;color:var(--v2-text)}
.ptm-head small{margin-left:8px;color:var(--v2-text-subtle);font-size:11px}
.ptm-close{width:28px;height:28px;display:grid;place-items:center;color:var(--v2-text-muted);background:transparent;border:1px solid var(--v2-border);border-radius:8px;cursor:pointer;font-size:14px}
.ptm-close:hover{color:var(--v2-text);border-color:var(--v2-primary)}
.ptm-error{padding:10px 18px;color:#ffdce1;background:rgba(255,127,145,.1);font-size:12px}
.ptm-empty{padding:30px 18px;text-align:center;color:var(--v2-text-subtle);font-size:12px}
.ptm-body{padding:16px 18px;display:grid;gap:14px}
.ptm-meta{display:flex;gap:12px;flex-wrap:wrap;font-size:11px;color:var(--v2-text-muted);align-items:center}
.ptm-meta code{color:var(--v2-primary);font-size:10px;background:rgba(130,149,255,.08);padding:2px 6px;border-radius:4px}
.ptm-field{display:grid;gap:5px}
.ptm-field label{font-size:11px;color:var(--v2-text-subtle);font-weight:600;text-transform:uppercase;letter-spacing:.5px}
.ptm-textarea{width:100%;padding:10px 12px;color:#eaf0ff;background:#0a1526;border:1px solid var(--v2-border);border-radius:10px;font-size:13px;line-height:1.7;font-family:inherit;resize:vertical}
.ptm-textarea:focus{border-color:var(--v2-primary);outline:none}
.ptm-textarea[readonly]{opacity:.95;cursor:default}
.ptm-system{min-height:80px}
.ptm-user{min-height:120px}
.ptm-actions{display:flex;align-items:center;gap:10px}
.ptm-hint{color:var(--v2-text-subtle);font-size:10px}
</style>