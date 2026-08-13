<script setup lang="ts">
import { computed, ref } from 'vue'
import V2Button from '@/v2/components/V2Button.vue'
import V2Field from '@/v2/components/V2Field.vue'
import type { ParameterConfig } from './model'
import { parameterTypes } from './model'

const props = defineProps<{
  open: boolean
  mode: 'upload' | 'mapping'
  parameters: ParameterConfig[]
  mappings: any[]
  nodes: Array<{ value: string; label: string }>
  nodeCount: number
  workflowName: string
  rawJson: string
  outputMapping: string
  editing: boolean
  busy: boolean
  presets: Array<{ id: string; name: string }>
  inputOptions: (mapping: any) => Array<{ value: string; label: string }>
}>()
const emit = defineEmits<{
  close: []
  parse: []
  save: []
  reupload: []
  'file-content': [name: string, content: string]
  'update:workflowName': [value: string]
  'update:rawJson': [value: string]
  'update:outputMapping': [value: string]
  'node-change': [mapping: any, nodeId: string]
  'save-preset': [name: string]
  'apply-preset': [id: string]
  'delete-preset': [id: string]
}>()

const fileInput = ref<HTMLInputElement | null>(null)
const presetName = ref('')
const selectedPreset = ref('')
const mediaTypes = ['image', 'video', 'audio']
const normalMappings = computed(() => props.mappings.filter(item => !mediaTypes.includes(item.type)))
const mediaMappings = computed(() => props.mappings.filter(item => mediaTypes.includes(item.type)))
const mappedCount = computed(() => props.mappings.filter(item => item.node && item.path).length)
const typeLabel = (type: string) => parameterTypes.find(item => item[0] === type)?.[1] || type

async function fileChanged(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  emit('file-content', file.name, await file.text())
}
function savePreset() {
  if (!presetName.value.trim()) return
  emit('save-preset', presetName.value.trim())
  presetName.value = ''
}
</script>

<template>
  <Teleport to="body">
    <Transition name="workspace">
      <div v-if="open" class="workspace-layer v2-theme" role="dialog" aria-modal="true" aria-label="工作流 JSON 导入与参数映射">
        <header class="workspace-header">
          <div><span class="workflow-icon">⌘</span><div><h2>{{ editing ? '编辑工作流映射' : '导入工作流 JSON' }}</h2><p>参数项完全来自参数设计；这里只负责关联 ComfyUI 节点和 inputs 属性。</p></div></div>
          <button class="close" aria-label="关闭" @click="emit('close')">×</button>
        </header>

        <main v-if="mode === 'upload'" class="upload-page">
          <div class="upload-drop" @click="fileInput?.click()"><span>⇧</span><b>选择 ComfyUI API JSON 文件</b><small>必须导出为 API 格式，不是界面 workflow 格式</small></div>
          <input ref="fileInput" hidden type="file" accept=".json,application/json" @change="fileChanged" />
          <V2Field label="或粘贴 JSON 内容"><textarea :value="rawJson" rows="14" placeholder='{"3":{"class_type":"KSampler","inputs":{...}}}' @input="emit('update:rawJson', ($event.target as HTMLTextAreaElement).value)" /></V2Field>
          <div class="upload-actions"><V2Button variant="ghost" @click="emit('close')">取消</V2Button><V2Button variant="primary" :disabled="!rawJson.trim()" @click="emit('parse')">解析并自动匹配</V2Button></div>
        </main>

        <main v-else class="mapping-page">
          <section class="mapping-toolbar">
            <div class="workflow-status"><span class="workflow-icon">⌘</span><div><b>{{ workflowName || '尚未命名工作流' }}</b><small>{{ nodeCount }} 个节点 · {{ mappedCount }}/{{ mappings.length }} 已映射</small></div><V2Button variant="ghost" @click="emit('reupload')">导入 / 更换 JSON</V2Button></div>
            <div class="preset-toolbar"><input v-model="presetName" placeholder="输入预设名称" /><V2Button variant="ghost" :disabled="!presetName.trim()" @click="savePreset">保存预设</V2Button><select v-model="selectedPreset" @change="selectedPreset && emit('apply-preset', selectedPreset)"><option value="">选择已保存预设</option><option v-for="preset in presets" :key="preset.id" :value="preset.id">{{ preset.name }}</option></select><button class="delete-preset" :disabled="!selectedPreset" @click="emit('delete-preset', selectedPreset); selectedPreset=''">删除</button></div>
          </section>

          <section class="name-row"><V2Field label="工作流名称" required><input :value="workflowName" @input="emit('update:workflowName', ($event.target as HTMLInputElement).value)" /></V2Field><div><b>节点字段映射</b><small>选择节点后会优先匹配适合该参数类型的 inputs 属性，也可以手工调整。</small></div></section>

          <section class="mapping-section">
            <header><div><h3>提示词和参数</h3><p>来自参数设计中的文本、数字、开关、选项等参数。</p></div><span>{{ normalMappings.filter(v=>v.node&&v.path).length }}/{{ normalMappings.length }} 已映射</span></header>
            <div v-if="normalMappings.length" class="parameter-grid">
              <article v-for="mapping in normalMappings" :key="mapping.key" :class="{ missing: !mapping.node || !mapping.path }">
                <div class="mapping-label"><b>{{ mapping.label }}</b><small>{{ mapping.key }} · {{ typeLabel(mapping.type) }}</small></div>
                <label><span>工作流节点</span><select :value="String(mapping.node || '')" @change="emit('node-change', mapping, ($event.target as HTMLSelectElement).value)"><option value="">不映射（使用工作流默认值）</option><option v-for="node in nodes" :key="node.value" :value="node.value">{{ node.label }}</option></select></label>
                <label><span>参数名称</span><select v-model="mapping.path" :disabled="!mapping.node"><option value="">请选择 inputs 属性</option><option v-for="option in inputOptions(mapping)" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
              </article>
            </div><p v-else class="empty">参数设计中还没有提示词或普通参数。</p>
          </section>

          <section class="mapping-section media-section">
            <header><div><h3>素材节点和顺序</h3><p>顺序继承参数设计，工作流映射不能新增、删除或改变素材项。</p></div><span>{{ mediaMappings.filter(v=>v.node&&v.path).length }}/{{ mediaMappings.length }} 已映射</span></header>
            <div v-if="mediaMappings.length" class="media-list">
              <article v-for="(mapping,index) in mediaMappings" :key="mapping.key" :class="{ missing: !mapping.node || !mapping.path }"><span class="order">{{ String(index + 1).padStart(2, '0') }}</span><div class="mapping-label"><b>{{ mapping.label }}</b><small>{{ typeLabel(mapping.type) }} · {{ mapping.key }}</small></div><label><span>目标加载节点</span><select :value="String(mapping.node || '')" @change="emit('node-change', mapping, ($event.target as HTMLSelectElement).value)"><option value="">请选择对应节点</option><option v-for="node in nodes" :key="node.value" :value="node.value">{{ node.label }}</option></select></label><label><span>参数名称</span><select v-model="mapping.path" :disabled="!mapping.node"><option value="">请选择 inputs 属性</option><option v-for="option in inputOptions(mapping)" :key="option.value" :value="option.value">{{ option.label }}</option></select></label></article>
            </div><p v-else class="empty">参数设计中还没有图片、视频或音频素材参数。</p>
          </section>

          <section class="output-section"><V2Field label="输出节点映射（JSON）"><textarea :value="outputMapping" rows="4" @input="emit('update:outputMapping', ($event.target as HTMLTextAreaElement).value)" /></V2Field></section>
        </main>
        <footer v-if="mode === 'mapping'" class="workspace-footer"><span>{{ mappings.length - mappedCount ? `还有 ${mappings.length - mappedCount} 项未映射，可保留工作流默认值` : '全部参数已完成映射' }}</span><div><V2Button variant="ghost" @click="emit('close')">取消</V2Button><V2Button variant="primary" :disabled="busy" @click="emit('save')">{{ busy ? '保存中…' : editing ? '保存为新版本并更新绑定' : '保存工作流并绑定' }}</V2Button></div></footer>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.workspace-layer{position:fixed;inset:0;z-index:1100;display:grid;grid-template-rows:auto 1fr auto;color:var(--v2-text);background:rgba(4,8,16,.96);backdrop-filter:blur(18px)}.workspace-header{min-height:68px;padding:12px 22px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--v2-border);background:rgba(10,15,27,.82)}.workspace-header>div,.workflow-status{display:flex;align-items:center;gap:12px}.workspace-header h2{margin:0;font-size:18px}.workspace-header p{margin:4px 0 0;color:var(--v2-text-muted);font-size:12px}.workflow-icon{width:38px;height:38px;display:grid;place-items:center;color:#ff9a48;background:rgba(255,137,45,.08);border:1px solid rgba(255,137,45,.25);border-radius:10px}.close{width:38px;height:38px;color:var(--v2-text);font-size:24px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:10px}.upload-page{width:min(820px,calc(100% - 32px));margin:auto;padding:28px;display:grid;gap:18px;overflow:auto}.upload-drop{min-height:220px;display:grid;place-items:center;align-content:center;gap:10px;border:1px dashed var(--v2-border-strong);border-radius:16px;background:rgba(130,149,255,.05);cursor:pointer}.upload-drop>span{font-size:46px;color:var(--v2-primary)}.upload-drop small,.empty{color:var(--v2-text-muted)}.upload-actions{display:flex;justify-content:flex-end;gap:8px}.mapping-page{padding:12px 18px 30px;overflow:auto}.mapping-toolbar{display:grid;grid-template-columns:minmax(300px,.72fr) minmax(500px,1.28fr);gap:10px}.workflow-status,.preset-toolbar,.name-row,.mapping-section,.output-section{padding:11px;border:1px solid var(--v2-border);border-radius:12px;background:rgba(12,17,28,.7)}.workflow-status>div{flex:1;display:grid;gap:5px}.workflow-status small{color:var(--v2-text-muted)}.preset-toolbar{display:grid;grid-template-columns:1fr auto 1.2fr auto;gap:8px}.preset-toolbar input,.preset-toolbar select,.delete-preset,.mapping-section select{min-height:40px;padding:8px 10px;color:var(--v2-text);background:rgba(3,8,17,.72);border:1px solid var(--v2-border);border-radius:9px}.delete-preset{color:var(--v2-danger)}.name-row{margin-top:10px;display:grid;grid-template-columns:minmax(260px,.6fr) 1.4fr;align-items:end;gap:18px}.name-row>div:last-child{display:grid;gap:5px}.name-row small{color:var(--v2-text-muted)}.mapping-section{margin-top:10px}.mapping-section>header{display:flex;align-items:center;justify-content:space-between;padding-bottom:10px;border-bottom:1px solid var(--v2-border)}.mapping-section h3,.mapping-section p{margin:0}.mapping-section p{margin-top:4px;color:var(--v2-text-muted);font-size:12px}.mapping-section>header>span{font-size:12px;color:var(--v2-text-muted)}.parameter-grid{padding-top:10px;display:grid;grid-template-columns:repeat(3,minmax(280px,1fr));gap:8px}.parameter-grid article,.media-list article{padding:10px;display:grid;gap:9px;background:rgba(255,255,255,.018);border:1px solid var(--v2-border);border-radius:10px}.parameter-grid article.missing,.media-list article.missing{border-color:rgba(255,183,77,.2)}.mapping-label{display:grid;gap:4px}.mapping-label small{color:var(--v2-text-muted)}.mapping-section label{display:grid;gap:5px}.mapping-section label>span{color:var(--v2-text-subtle);font-size:11px}.media-list{padding-top:10px;display:grid;gap:7px}.media-list article{grid-template-columns:42px minmax(150px,.5fr) minmax(260px,1.3fr) minmax(170px,.7fr);align-items:end}.order{align-self:center;color:var(--v2-primary);font:700 18px/1 monospace}.output-section{margin-top:10px}.workspace-footer{min-height:68px;padding:12px 22px;display:flex;align-items:center;justify-content:space-between;border-top:1px solid var(--v2-border);background:rgba(10,15,27,.92)}.workspace-footer>span{color:var(--v2-text-muted);font-size:12px}.workspace-footer>div{display:flex;gap:8px}.workspace-enter-active,.workspace-leave-active{transition:opacity .18s}.workspace-enter-from,.workspace-leave-to{opacity:0}
@media(max-width:1100px){.mapping-toolbar{grid-template-columns:1fr}.parameter-grid{grid-template-columns:repeat(2,minmax(260px,1fr))}}@media(max-width:700px){.workspace-header p{display:none}.mapping-page{padding:10px}.preset-toolbar,.name-row{grid-template-columns:1fr}.parameter-grid{grid-template-columns:1fr}.media-list article{grid-template-columns:38px 1fr}.media-list article label{grid-column:1/-1}.workflow-status{align-items:flex-start;flex-wrap:wrap}.workflow-status>div{min-width:180px}.workspace-footer{align-items:flex-start;gap:8px;flex-direction:column}.workspace-footer>div{width:100%}.workspace-footer>div>*{flex:1}}
</style>
