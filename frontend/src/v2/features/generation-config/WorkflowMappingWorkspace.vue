<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import V2Button from '@/v2/components/V2Button.vue'
import V2Field from '@/v2/components/V2Field.vue'
import { parameterTypes } from './model'

const props = defineProps<{
  open: boolean
  mode: 'upload' | 'mapping'
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
  selectSources: Array<{ value: string; label: string }>
  selectOptions: Record<string, { label: string; options: Array<{ label: string; value: any }>; default_value: any }>
  mediaType: 'image' | 'video' | 'audio'
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
  'size-target-change': [mapping: any, dimension: 'width' | 'height', nodeId: string]
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
function isMapped(item: any) { return item.type === 'size' ? Boolean(item.targets?.width?.node && item.targets?.width?.path && item.targets?.height?.node && item.targets?.height?.path) : Boolean(item.node && item.path) }
const mappedCount = computed(() => props.mappings.filter(isMapped).length)

function uniqueKey(prefix: string) {
  const used = new Set(props.mappings.map(item => String(item.key)))
  let index = 1
  while (used.has(`${prefix}_${index}`)) index++
  return `${prefix}_${index}`
}
function addParameter(media = false) {
  const type = media ? 'image' : 'text'
  const key = uniqueKey(media ? 'material' : 'parameter')
  props.mappings.push({ key, label: media ? '新素材' : '新参数', type, group: media ? 'media' : 'parameter', required: false, default: media ? null : '', node: '', path: '', media_order: media ? mediaMappings.value.length + 1 : undefined })
}
function addSizeParameter() {
  const sizeKind = props.mediaType === 'video' ? 'video' : 'image'
  const optionsFrom = `${sizeKind}_size`
  if (props.mappings.some(item => item.type === 'size')) return
  props.mappings.push({ key: 'size', label: sizeKind === 'video' ? '视频尺寸' : '图片尺寸', type: 'size', group: 'parameter', size_kind: sizeKind, options_from: optionsFrom, default: props.selectOptions[optionsFrom]?.default_value, required: true, help: '一次选择并同时写入宽度和高度', targets: { width: { node: '', path: '' }, height: { node: '', path: '' } } })
}
function removeParameter(mapping: any) {
  const index = props.mappings.indexOf(mapping)
  if (index >= 0) props.mappings.splice(index, 1)
  normalizeMediaOrder()
}
function moveParameter(mapping: any, offset: number) {
  const group = mediaTypes.includes(mapping.type) ? mediaMappings.value : normalMappings.value
  const current = group.indexOf(mapping)
  const target = current + offset
  if (target < 0 || target >= group.length) return
  const other = group[target]
  const from = props.mappings.indexOf(mapping)
  const to = props.mappings.indexOf(other)
  props.mappings.splice(from, 1)
  props.mappings.splice(to, 0, mapping)
  normalizeMediaOrder()
}
function normalizeMediaOrder() {
  mediaMappings.value.forEach((item, index) => { item.group = 'media'; item.media_order = index + 1 })
  normalMappings.value.forEach(item => { item.group = 'parameter'; delete item.media_order })
}
function changeType(mapping: any, value: string) {
  const wasSize = mapping.type === 'size'
  mapping.type = value
  mapping.group = mediaTypes.includes(value) ? 'media' : 'parameter'
  if (mapping.group === 'media') mapping.default = null
  if (value === 'size') {
    const sizeKind = props.mediaType === 'video' ? 'video' : 'image'
    mapping.key = mapping.key || 'size'; mapping.label = mapping.label || (sizeKind === 'video' ? '视频尺寸' : '图片尺寸')
    mapping.size_kind = sizeKind; mapping.options_from = `${sizeKind}_size`; mapping.default ||= props.selectOptions[mapping.options_from]?.default_value
    mapping.targets ||= { width: { node: '', path: '' }, height: { node: '', path: '' } }
    delete mapping.node; delete mapping.path
  } else if (wasSize) {
    delete mapping.targets; delete mapping.size_kind; delete mapping.options_from
    mapping.node = ''; mapping.path = ''
  }
  normalizeMediaOrder()
}
// 监听 select 类型参数的 options_from 变化，自动填入系统维护项默认值
watch(() => props.mappings.map(m => m.options_from), (newVals, oldVals) => {
  if (!oldVals) return
  for (let i = 0; i < newVals.length; i++) {
    if (newVals[i] !== oldVals[i] && newVals[i]) {
      const m = props.mappings[i]
      const source = props.selectOptions[newVals[i]]
      if (source?.default_value !== undefined && (m.type === 'select' || m.type === 'size')) {
        m.default = source.default_value
      }
    }
  }
}, { deep: true })

// 根据路径名推断参数类型
function inferType(path: string): string | null {
  const p = path.toLowerCase()
  if (p.includes('image') || p.includes('picture') || p.includes('photo')) return 'image'
  if (p.includes('video')) return 'video'
  if (p.includes('audio') || p.includes('sound') || p.includes('voice')) return 'audio'
  if (p.includes('negative') || p.includes('neg')) return 'textarea'
  if (p.includes('prompt') || p.includes('text') || p.includes('caption') || p.includes('description')) return 'textarea'
  if (p.includes('seed')) return 'seed'
  if (p.includes('denoise') || p.includes('strength') || p.includes('cfg') || p.includes('scale')) return 'float'
  if (p.includes('width') || p.includes('height') || p.includes('size') || p.includes('length') || p.includes('count') || p.includes('frames') || p.includes('batch')) return 'int'
  if (p.includes('step') || p.includes('fps') || p.includes('num')) return 'int'
  if (p.includes('enable') || p.includes('disable') || p.includes('use') || p.includes('skip')) return 'bool'
  return null
}

// 根据路径名生成中文标签
function inferLabel(path: string): string {
  const labelMap: Record<string, string> = {
    prompt: '提示词', negative: '负面提示词', negative_prompt: '负面提示词',
    seed: '随机种子', steps: '步数', cfg: 'CFG引导系数', denoise: '重绘幅度',
    width: '宽度', height: '高度', image: '输入图片', video: '输入视频',
    audio: '输入音频', text: '文本', caption: '描述', description: '描述',
    batch_size: '批量数量', length: '帧数', fps: '帧率',
    noise_seed: '噪声种子', noise: '噪声', scale: '缩放比例',
    strength: '强度', sampler_name: '采样器', scheduler: '调度器',
    start_at: '开始步', end_at: '结束步', control_after_generate: '生成后控制',
  }
  const key = path.toLowerCase().replace(/^inputs\./, '')
  if (labelMap[key]) return labelMap[key]
  // 去掉 inputs. 前缀，转驼峰式中文显示
  const cleaned = key.replace(/^inputs\./, '').replace(/_/g, ' ').trim()
  return cleaned || path
}

// 监听 path 变化，自动填充 label/key/type（仅在用户未手动填写时）
watch(() => props.mappings.map(m => `${m.node}:${m.path}`), (newVals, oldVals) => {
  if (!oldVals) return
  for (let i = 0; i < newVals.length; i++) {
    if (newVals[i] === oldVals[i] || !newVals[i]) continue
    const m = props.mappings[i]
    if (!m.path) continue
    const pathName = String(m.path).replace(/^inputs\./, '')
    // 仅在值为空或仍是默认占位时自动填
    if (!m.label || m.label === '新参数' || m.label === '新素材') {
      m.label = inferLabel(pathName)
    }
    if (!m.key || m.key.startsWith('parameter_') || m.key.startsWith('material_')) {
      m.key = pathName.replace(/[^a-zA-Z0-9_]/g, '_')
    }
    // 仅在类型为默认值（text 或新建时的初始类型）时自动推断
    if (m.type === 'text' && !mediaTypes.includes(m.type)) {
      const inferred = inferType(pathName)
      if (inferred) {
        m.type = inferred
        // 如果推断为媒体类型，更新 group
        if (mediaTypes.includes(inferred)) {
          m.group = 'media'
          m.default = null
          m.media_order = mediaMappings.value.length + 1
        }
        normalizeMediaOrder()
      }
    }
  }
}, { deep: true })

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
          <div><span class="workflow-icon">⌘</span><div><h2>{{ editing ? '编辑工作流和输入参数' : '导入工作流 JSON' }}</h2><p>每个工作流独立定义输入参数、素材顺序及 ComfyUI 节点映射。</p></div></div>
          <button class="close" aria-label="关闭" @click="emit('close')">×</button>
        </header>

        <main v-if="mode === 'upload'" class="upload-page">
          <div class="upload-drop" @click="fileInput?.click()"><span>⇧</span><b>选择 ComfyUI API JSON 文件</b><small>必须导出为 API 格式，不是界面 workflow 格式</small></div>
          <input ref="fileInput" hidden type="file" accept=".json,application/json" @change="fileChanged" />
          <V2Field label="或粘贴 JSON 内容"><textarea :value="rawJson" rows="14" placeholder='{"3":{"class_type":"KSampler","inputs":{...}}}' @input="emit('update:rawJson', ($event.target as HTMLTextAreaElement).value)" /></V2Field>
          <div class="upload-actions"><V2Button variant="ghost" @click="emit('close')">取消</V2Button><V2Button variant="primary" :disabled="!rawJson.trim()" @click="emit('parse')">解析并配置参数</V2Button></div>
        </main>

        <main v-else class="mapping-page">
          <section class="mapping-toolbar">
            <div class="workflow-status"><span class="workflow-icon">⌘</span><div><b>{{ workflowName || '尚未命名工作流' }}</b><small>{{ nodeCount }} 个节点 · {{ mappedCount }}/{{ mappings.length }} 已映射</small></div><V2Button variant="ghost" @click="emit('reupload')">导入 / 更换 JSON</V2Button></div>
            <div class="preset-toolbar"><input v-model="presetName" placeholder="输入预设名称" /><V2Button variant="ghost" :disabled="!presetName.trim()" @click="savePreset">保存预设</V2Button><select v-model="selectedPreset" @change="selectedPreset && emit('apply-preset', selectedPreset)"><option value="">选择已保存预设</option><option v-for="preset in presets" :key="preset.id" :value="preset.id">{{ preset.name }}</option></select><button class="delete-preset" :disabled="!selectedPreset" @click="emit('delete-preset', selectedPreset); selectedPreset=''">删除</button></div>
          </section>

          <section class="name-row"><V2Field label="工作流名称" required><input :value="workflowName" @input="emit('update:workflowName', ($event.target as HTMLInputElement).value)" /></V2Field><div><b>节点字段映射</b><small>选择节点后会优先匹配适合该参数类型的 inputs 属性，也可以手工调整。</small></div></section>

          <section class="mapping-section">
            <header><div><h3>提示词和参数</h3><p>为当前工作流添加页面输入项，并配置显示信息与节点映射。</p></div><div class="section-actions"><span>{{ normalMappings.filter(isMapped).length }}/{{ normalMappings.length }} 已映射</span><V2Button v-if="mediaType!=='audio'&&!mappings.some(v=>v.type==='size')" variant="ghost" @click="addSizeParameter">添加{{ mediaType==='video'?'视频':'图片' }}尺寸</V2Button><V2Button variant="ghost" @click="addParameter(false)">添加参数</V2Button></div></header>
            <div v-if="normalMappings.length" class="parameter-grid">
              <article v-for="mapping in normalMappings" :key="mapping.key" :class="{ missing: !isMapped(mapping) }">
                <div class="item-actions"><button :disabled="normalMappings[0]===mapping" @click="moveParameter(mapping,-1)">↑</button><button :disabled="normalMappings[normalMappings.length-1]===mapping" @click="moveParameter(mapping,1)">↓</button><button class="danger" @click="removeParameter(mapping)">删除</button></div>
                <div class="definition-grid"><label><span>参数名称</span><input v-model.trim="mapping.label" /></label><label><span>参数标识</span><input v-model.trim="mapping.key" /></label><label><span>参数类型</span><select :value="mapping.type" @change="changeType(mapping,($event.target as HTMLSelectElement).value)"><option v-for="item in parameterTypes.filter(v=>!mediaTypes.includes(v[0]))" :key="item[0]" :value="item[0]">{{ item[1] }}</option></select></label></div>
                <div class="definition-grid"><label><span>默认值</span><select v-if="mapping.type==='size'" v-model="mapping.default"><option v-for="option in selectOptions[mapping.options_from]?.options||[]" :key="String(option.value)" :value="option.value">{{ option.label }}</option></select><select v-else-if="mapping.type==='bool'" v-model="mapping.default"><option :value="false">关闭</option><option :value="true">开启</option></select><input v-else-if="['int','float','seed','slider'].includes(mapping.type)" v-model.number="mapping.default" type="number" /><input v-else v-model="mapping.default" /></label><label v-if="mapping.type==='select'"><span>选项来源</span><select v-model="mapping.options_from"><option value="">请选择维护项</option><option v-for="source in selectSources" :key="source.value" :value="source.value">{{ source.label }}</option></select></label><label v-else-if="mapping.type==='size'"><span>尺寸维护项</span><input :value="selectOptions[mapping.options_from]?.label||mapping.options_from" disabled /></label><label><span>帮助说明</span><input v-model="mapping.help" /></label><label class="checkbox"><input v-model="mapping.required" type="checkbox" /> 必填</label></div>
                <div v-if="['int','float','seed','slider'].includes(mapping.type)" class="definition-grid"><label><span>最小值</span><input v-model.number="mapping.min" type="number" /></label><label><span>最大值</span><input v-model.number="mapping.max" type="number" /></label><label><span>步长</span><input v-model.number="mapping.step" type="number" /></label><label><span>单位</span><input v-model="mapping.unit" /></label></div>
                <div v-if="mapping.type==='size'" class="size-targets"><div v-for="dimension in (['width','height'] as const)" :key="dimension"><b>{{ dimension==='width'?'宽度映射':'高度映射' }}</b><label><span>工作流节点</span><select :value="String(mapping.targets?.[dimension]?.node||'')" @change="emit('size-target-change',mapping,dimension,($event.target as HTMLSelectElement).value)"><option value="">请选择节点</option><option v-for="node in nodes" :key="node.value" :value="node.value">{{ node.label }}</option></select></label><label><span>参数名称</span><select v-model="mapping.targets[dimension].path" :disabled="!mapping.targets?.[dimension]?.node"><option value="">请选择 inputs 属性</option><option v-for="option in inputOptions({...mapping.targets[dimension],type:'int'})" :key="option.value" :value="option.value">{{ option.label }}</option></select></label></div></div>
                <template v-else><label><span>工作流节点</span><select :value="String(mapping.node || '')" @change="emit('node-change', mapping, ($event.target as HTMLSelectElement).value)"><option value="">不映射（使用工作流默认值）</option><option v-for="node in nodes" :key="node.value" :value="node.value">{{ node.label }}</option></select></label><label><span>参数名称</span><select v-model="mapping.path" :disabled="!mapping.node"><option value="">请选择 inputs 属性</option><option v-for="option in inputOptions(mapping)" :key="option.value" :value="option.value">{{ option.label }}</option></select></label></template>
              </article>
            </div><p v-else class="empty">当前工作流还没有页面参数，点击“添加参数”开始配置。</p>
          </section>

          <section class="mapping-section media-section">
            <header><div><h3>素材节点和顺序</h3><p>定义当前工作流需要的图片、视频、音频输入和展示顺序。</p></div><div class="section-actions"><span>{{ mediaMappings.filter(v=>v.node&&v.path).length }}/{{ mediaMappings.length }} 已映射</span><V2Button variant="ghost" @click="addParameter(true)">添加素材</V2Button></div></header>
            <div v-if="mediaMappings.length" class="media-list">
              <article v-for="(mapping,index) in mediaMappings" :key="mapping.key" :class="{ missing: !mapping.node || !mapping.path }"><span class="order">{{ String(index + 1).padStart(2, '0') }}</span><div class="media-definition"><label><span>素材名称</span><input v-model.trim="mapping.label" /></label><label><span>参数标识</span><input v-model.trim="mapping.key" /></label><label><span>素材类型</span><select :value="mapping.type" @change="changeType(mapping,($event.target as HTMLSelectElement).value)"><option value="image">图片</option><option value="video">视频</option><option value="audio">音频</option></select></label><label class="checkbox"><input v-model="mapping.required" type="checkbox" /> 必填</label><label class="checkbox"><input v-model="mapping.multiple" type="checkbox" /> 允许多选</label><label v-if="mapping.multiple"><span>最多选择</span><input v-model.number="mapping.max_items" type="number" min="1" max="20" /></label></div><label><span>目标加载节点</span><select :value="String(mapping.node || '')" @change="emit('node-change', mapping, ($event.target as HTMLSelectElement).value)"><option value="">请选择对应节点</option><option v-for="node in nodes" :key="node.value" :value="node.value">{{ node.label }}</option></select></label><label><span>参数名称</span><select v-model="mapping.path" :disabled="!mapping.node"><option value="">请选择 inputs 属性</option><option v-for="option in inputOptions(mapping)" :key="option.value" :value="option.value">{{ option.label }}</option></select></label><div class="item-actions"><button :disabled="index===0" @click="moveParameter(mapping,-1)">↑</button><button :disabled="index===mediaMappings.length-1" @click="moveParameter(mapping,1)">↓</button><button class="danger" @click="removeParameter(mapping)">删除</button></div></article>
            </div><p v-else class="empty">当前工作流还没有素材输入，点击“添加素材”开始配置。</p>
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
.mapping-section input{min-height:40px;padding:8px 10px;color:var(--v2-text);background:rgba(3,8,17,.72);border:1px solid var(--v2-border);border-radius:9px}.section-actions{display:flex;align-items:center;gap:10px}.parameter-grid{grid-template-columns:repeat(2,minmax(360px,1fr))}.definition-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}.definition-grid .checkbox,.media-definition .checkbox{display:flex;align-items:center;align-self:end;min-height:40px}.definition-grid .checkbox input,.media-definition .checkbox input{min-height:auto}.item-actions{display:flex;justify-content:flex-end;gap:5px}.item-actions button{min-width:32px;min-height:28px;color:var(--v2-text-muted);background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:7px}.item-actions .danger{color:var(--v2-danger)}.media-list article{grid-template-columns:42px minmax(420px,1.5fr) minmax(230px,1fr) minmax(170px,.7fr) auto}.media-definition{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}
@media(max-width:1100px){.parameter-grid{grid-template-columns:1fr}.media-list article{grid-template-columns:42px 1fr 1fr}.media-list article .item-actions{grid-column:3}}@media(max-width:700px){.definition-grid,.media-definition{grid-template-columns:1fr}.media-list article{grid-template-columns:38px 1fr}.media-list article label,.media-list article .item-actions{grid-column:1/-1}.mapping-section>header{align-items:flex-start;gap:8px}.section-actions{align-items:flex-end;flex-direction:column}}
.size-targets{display:grid;grid-template-columns:1fr 1fr;gap:8px}.size-targets>div{padding:9px;display:grid;gap:7px;background:rgba(130,149,255,.05);border:1px solid var(--v2-border);border-radius:9px}.size-targets b{font-size:12px;color:var(--v2-primary)}
@media(max-width:700px){.size-targets{grid-template-columns:1fr}}
</style>
