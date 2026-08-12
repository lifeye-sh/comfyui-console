<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useMessage } from 'naive-ui'
import { workflowApi, genTypeApi } from '@/api/modules'

const route = useRoute()
const message = useMessage()
const workflows = ref<any[]>([])
const typeInfo = ref<any>(null)

const code = computed(() => route.params.code as string | undefined)
const pageTitle = computed(() => typeInfo.value?.name ? `${typeInfo.value.name} · 工作流` : '工作流管理')

// 导入工作流弹窗
const showImport = ref(false)
const importStep = ref<'upload' | 'review'>('upload')
const rawJson = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const parseResult = ref<any>(null)
const workflowName = ref('')

// 参数映射编辑
const paramSchema = ref<any[]>([])
const outputMapping = ref<string>('')

// 创建工作流
const form = reactive({
  name: '',
  description: '',
  media_type: 'image',
})

async function loadTypeInfo() {
  typeInfo.value = null
  if (!code.value) return
  try {
    const menu = await genTypeApi.menu()
    const flat = [...(menu.image || []), ...(menu.video || []), ...(menu.audio || [])]
    const t = flat.find((x: any) => x.code === code.value)
    if (t) {
      typeInfo.value = t
      form.media_type = t.media_type || 'image'
    }
  } catch {
    /* ignore */
  }
}

async function load() {
  if (!code.value) {
    workflows.value = []
    return
  }
  try {
    const params: any = {}
    if (code.value) {
      params.generation_type_code = code.value
    }
    workflows.value = await workflowApi.list(params)
  } catch {
    message.error('加载失败')
  }
}
onMounted(async () => {
  await loadTypeInfo()
  await load()
})
watch(code, async () => {
  await loadTypeInfo()
  await load()
})

// ---- 导入工作流流程 ----

// 上传 JSON 文件
function onFileUpload(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = (e) => {
    rawJson.value = e.target?.result as string
    parseJson()
  }
  reader.readAsText(file)
}

// 也可粘贴 JSON 后点解析
async function parseJson() {
  if (!rawJson.value.trim()) {
    message.warning('请先上传或粘贴 JSON')
    return
  }
  try {
    const apiJson = JSON.parse(rawJson.value)
    const result = await workflowApi.parse(apiJson, code.value || undefined)
    parseResult.value = result
    workflowName.value = result.suggested_name || '未命名'
    paramSchema.value = result.param_schema || []
    outputMapping.value = JSON.stringify(result.output_mapping || {}, null, 2)
    importStep.value = 'review'
  } catch (e: any) {
    message.error('解析失败：' + (e.response?.data?.message || e.message))
  }
}

// 参数映射编辑
function addParam() {
  paramSchema.value.push({
    key: '',
    node: '',
    path: 'inputs.',
    type: 'textarea',
    label: '',
  })
}

function delParam(i: number) {
  paramSchema.value.splice(i, 1)
}

const inputFieldCandidates: Record<string, string[]> = {
  int: ['value', 'Float', 'text', 'Int', 'integer'],
  bool: ['value', 'Float', 'text', 'boolean'],
  select: ['value', 'Float', 'text', 'Int', 'integer'],
  seed: ['value', 'Float', 'text', 'seed'],
  float: ['Float', 'value', 'text', 'float'],
  image: ['image'],
  video: ['video'],
  audio: ['audio'],
  text: ['text', 'value'],
  textarea: ['text', 'value'],
}

function autoMatchSelectedNode(param: any, nodeId: string | number | null, apiJson: any) {
  param.node = nodeId == null ? '' : String(nodeId)
  if (!param.node) { param.path = ''; return }
  const inputs = apiJson?.[param.node]?.inputs
  if (!inputs || typeof inputs !== 'object') {
    param.path = ''
    message.warning('所选节点没有可匹配的 inputs 参数')
    return
  }
  const candidates = inputFieldCandidates[param.type] || ['value']
  const field = candidates.find((name) => Object.prototype.hasOwnProperty.call(inputs, name))
  if (field) {
    param.path = `inputs.${field}`
    return
  }
  param.path = ''
  message.warning(`节点 ${param.node} 没有适用于“${param.label || param.key || param.type}”的输入字段`)
}

function inputPathOptions(param: any, apiJson: any) {
  if (!param?.node) return []
  const inputs = apiJson?.[String(param.node)]?.inputs
  if (!inputs || typeof inputs !== 'object' || Array.isArray(inputs)) return []
  const options = Object.keys(inputs).map((field) => ({
    label: field,
    value: `inputs.${field}`,
  }))
  // Keep a legacy mapping visible while editing even if the uploaded JSON changed.
  if (param.path && !options.some((option) => option.value === param.path)) {
    options.unshift({ label: `${param.path.replace(/^inputs\./, '')}（原映射）`, value: param.path })
  }
  return options
}

function importInputPathOptions(param: any) {
  let apiJson: any = {}
  try { apiJson = JSON.parse(rawJson.value || '{}') } catch { /* 已在解析步骤校验 */ }
  return inputPathOptions(param, apiJson)
}

function versionInputPathOptions(param: any) {
  let apiJson: any = {}
  try { apiJson = JSON.parse(versionRawJson.value || '{}') } catch { /* 已在解析步骤校验 */ }
  return inputPathOptions(param, apiJson)
}

function editInputPathOptions(param: any) {
  return inputPathOptions(param, editApiJson.value)
}

function importNodeChanged(param: any, nodeId: string | number | null) {
  let apiJson: any = {}
  try { apiJson = JSON.parse(rawJson.value || '{}') } catch { /* 已在解析步骤校验 */ }
  autoMatchSelectedNode(param, nodeId, apiJson)
}

function versionNodeChanged(param: any, nodeId: string | number | null) {
  let apiJson: any = {}
  try { apiJson = JSON.parse(versionRawJson.value || '{}') } catch { /* 已在解析步骤校验 */ }
  autoMatchSelectedNode(param, nodeId, apiJson)
}

function editNodeChanged(param: any, nodeId: string | number | null) {
  autoMatchSelectedNode(param, nodeId, editApiJson.value)
}

// 可用节点列表（从解析结果获取）
const nodeOptions = computed(() => {
  if (!parseResult.value) return []
  return parseResult.value.nodes.map((n: any) => ({
    label: `${n.id} - ${n.title}`,
    value: n.id,
  }))
})

// 保存工作流+版本
async function saveImport() {
  if (!workflowName.value.trim()) {
    message.warning('请填写工作流名称')
    return
  }
  try {
    // 1. 创建工作流
    const wfBody: any = {
      name: workflowName.value,
      description: '',
      media_type: typeInfo.value?.media_type || form.media_type,
      generation_type_id: typeInfo.value?.id || null,
    }
    const wf = await workflowApi.create(wfBody)

    // 2. 添加版本（含 API JSON + 参数映射）
    await workflowApi.addVersion(wf.id, {
      api_json: JSON.parse(rawJson.value),
      param_schema: paramSchema.value,
      output_mapping: JSON.parse(outputMapping.value),
    })

    message.success('工作流导入成功')
    showImport.value = false
    resetImport()
    await load()
  } catch (e: any) {
    message.error('保存失败：' + (e.response?.data?.message || e.message))
  }
}

function resetImport() {
  importStep.value = 'upload'
  rawJson.value = ''
  parseResult.value = null
  workflowName.value = ''
  paramSchema.value = []
  outputMapping.value = '{}'
}

// 给已有工作流添加版本（从已有工作流卡片触发）
const showAddVersion = ref(false)
const selectedWf = ref<any>(null)
const versionStep = ref<'upload' | 'review'>('upload')
const versionRawJson = ref('')
const versionParseResult = ref<any>(null)
const versionParamSchema = ref<any[]>([])
const versionOutputMapping = ref<string>('{}')

function openAddVersion(w: any) {
  selectedWf.value = w
  versionStep.value = 'upload'
  versionRawJson.value = ''
  versionParseResult.value = null
  versionParamSchema.value = []
  versionOutputMapping.value = '{}'
  showAddVersion.value = true
}

function onVersionFileUpload(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = (e) => {
    versionRawJson.value = e.target?.result as string
    parseVersionJson()
  }
  reader.readAsText(file)
}

async function parseVersionJson() {
  if (!versionRawJson.value.trim()) return
  try {
    const apiJson = JSON.parse(versionRawJson.value)
    const result = await workflowApi.parse(apiJson, code.value || undefined)
    versionParseResult.value = result
    versionParamSchema.value = result.param_schema || []
    versionOutputMapping.value = JSON.stringify(result.output_mapping || {}, null, 2)
    versionStep.value = 'review'
  } catch (e: any) {
    message.error('解析失败：' + (e.response?.data?.message || e.message))
  }
}

function addVersionParam() {
  versionParamSchema.value.push({ key: '', node: '', path: 'inputs.', type: 'textarea', label: '' })
}

function delVersionParam(i: number) {
  versionParamSchema.value.splice(i, 1)
}

const versionNodeOptions = computed(() => {
  if (!versionParseResult.value) return []
  return versionParseResult.value.nodes.map((n: any) => ({
    label: `${n.id} - ${n.title}`,
    value: n.id,
  }))
})

async function saveAddVersion() {
  try {
    await workflowApi.addVersion(selectedWf.value.id, {
      api_json: JSON.parse(versionRawJson.value),
      param_schema: versionParamSchema.value,
      output_mapping: JSON.parse(versionOutputMapping.value),
    })
    message.success('版本添加成功')
    showAddVersion.value = false
    await load()
  } catch (e: any) {
    message.error('保存失败：' + (e.response?.data?.message || e.message))
  }
}

// ---- 编辑参数映射 ----
const showEdit = ref(false)
const editWf = ref<any>(null)
const editWorkflowName = ref('')
const editVersionId = ref<number | null>(null)
const editParamSchema = ref<any[]>([])
const editOutputMapping = ref<string>('{}')
const editApiJson = ref<any>({})
const editNodeOptions = ref<any[]>([])
const editJsonFileName = ref('')

async function openEdit(w: any) {
  editWf.value = w
  editWorkflowName.value = w.name || ''
  editJsonFileName.value = ''
  if (!w.current_version_id) {
    message.warning('该工作流暂无版本，请先添加版本')
    return
  }
  try {
    const detail = await workflowApi.getVersionDetail(w.id, w.current_version_id)
    editVersionId.value = w.current_version_id
    editParamSchema.value = detail.param_schema || []
    editOutputMapping.value = JSON.stringify(detail.output_mapping || {}, null, 2)
    editApiJson.value = detail.api_json || {}
    editNodeOptions.value = (detail.nodes || []).map((n: any) => ({
      label: `${n.id} - ${n.title}`,
      value: n.id,
    }))
    showEdit.value = true
  } catch (e: any) {
    message.error('加载版本详情失败：' + (e.response?.data?.message || e.message))
  }
}

async function onEditFileUpload(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  try {
    const text = await file.text()
    const apiJson = JSON.parse(text)
    const result = await workflowApi.parse(apiJson, code.value || undefined)
    editApiJson.value = apiJson
    editParamSchema.value = result.param_schema || []
    editOutputMapping.value = JSON.stringify(result.output_mapping || {}, null, 2)
    editNodeOptions.value = (result.nodes || []).map((node: any) => ({
      label: `${node.id} - ${node.title}`,
      value: node.id,
    }))
    editJsonFileName.value = file.name
    message.success('新工作流 JSON 已解析，请检查参数映射后保存')
  } catch (e: any) {
    target.value = ''
    message.error('JSON 解析失败：' + (e.response?.data?.message || e.message))
  }
}

function addEditParam() {
  editParamSchema.value.push({ key: '', node: '', path: 'inputs.', type: 'textarea', label: '' })
}

function delEditParam(i: number) {
  editParamSchema.value.splice(i, 1)
}

async function saveEdit() {
  if (!editWf.value || editVersionId.value === null) {
    message.error('工作流版本不存在')
    return
  }
  if (!editWorkflowName.value.trim()) {
    message.warning('工作流名称不能为空')
    return
  }
  try {
    await workflowApi.updateVersion(editWf.value.id, editVersionId.value, {
      api_json: editApiJson.value,
      param_schema: editParamSchema.value,
      output_mapping: JSON.parse(editOutputMapping.value),
    })
    await workflowApi.update(editWf.value.id, { name: editWorkflowName.value.trim() })
    message.success('工作流名称、JSON 和参数映射已更新')
    showEdit.value = false
    await load()
  } catch (e: any) {
    message.error('保存失败：' + (e.response?.data?.message || e.message))
  }
}

// 删除与设默认
async function del(id: number) {
  try {
    await workflowApi.remove(id)
    await load()
  } catch {
    message.error('删除失败')
  }
}

async function setDefault(w: any) {
  if (!typeInfo.value) return
  try {
    const wf = workflows.value.find((x) => x.id === w.id)
    if (!wf?.current_version_id) {
      message.warning('请先添加版本')
      return
    }
    await genTypeApi.setDefault(typeInfo.value.id, wf.current_version_id)
    message.success('已设为默认工作流')
    await loadTypeInfo()
  } catch (e: any) {
    message.error(e.response?.data?.message || '设置失败')
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex justify-between items-center mb-4">
      <NH2 style="margin: 0">{{ pageTitle }}</NH2>
      <NButton v-if="code && typeInfo" type="primary" @click="showImport = true">导入工作流</NButton>
    </div>

    <div v-if="!workflows.length" class="text-gray-400">
      {{ code ? `暂无「${typeInfo?.name}」类型的工作流，请点击「导入工作流」` : '请从具体生成类型页面进入工作流管理' }}
    </div>
    <div v-else class="space-y-2">
      <div v-for="w in workflows" :key="w.id" class="border rounded p-3 flex justify-between items-center">
        <div>
          <NText strong>{{ w.name }}</NText>
          <NText depth="3" style="font-size: 12px; margin-left: 8px">{{ w.media_type }}</NText>
          <div class="text-xs text-gray-500">当前版本：{{ w.current_version_id || '无' }}</div>
        </div>
        <div class="flex gap-1">
          <NButton v-if="code && typeInfo" size="small" quaternary @click="setDefault(w)">设为默认</NButton>
          <NButton size="small" @click="openEdit(w)">编辑</NButton>
          <NButton size="small" @click="openAddVersion(w)">添加版本</NButton>
          <NButton size="small" type="error" quaternary @click="del(w.id)">删除</NButton>
        </div>
      </div>
    </div>

    <!-- 导入工作流弹窗 -->
    <NModal :show="showImport" @update:show="(v) => { showImport = v; if (!v) resetImport() }" preset="card"
      title="导入 ComfyUI 工作流" style="max-width: 800px">
      <!-- 第一步：上传/粘贴 JSON -->
      <template v-if="importStep === 'upload'">
        <NSpace vertical :size="12">
          <NText>上传 ComfyUI 导出的 API 格式 JSON 文件，系统会自动识别节点和参数映射。</NText>
          <input ref="fileInput" type="file" accept=".json" @change="onFileUpload" class="block mb-2" />
          <NButton type="primary" @click="fileInput?.click()">选择 JSON 文件</NButton>
          <NText depth="3" style="font-size: 12px">或粘贴 JSON 内容：</NText>
          <NInput v-model:value="rawJson" type="textarea" :rows="8" placeholder='{"3": {"class_type": "KSampler", ...}}' />
          <NButton @click="parseJson">解析 JSON</NButton>
        </NSpace>
      </template>

      <!-- 第二步：确认参数映射 -->
      <template v-else>
        <NSpace vertical :size="16">
          <!-- 解析概要 -->
          <NCard title="识别结果" size="small">
            <div class="text-sm space-y-1">
              <div>工作流名称：<NText strong>{{ parseResult?.suggested_name }}</NText></div>
              <div>识别到 {{ parseResult?.nodes?.length }} 个节点，{{ paramSchema.length }} 个可配置参数</div>
              <div>输出节点：{{ Object.entries(parseResult?.output_mapping || {}).map(([k, v]) => `${k}: ${v}`).join('，') }}</div>
            </div>
          </NCard>

          <!-- 工作流名称 -->
          <div>
            <NText depth="3" style="font-size: 12px">工作流名称</NText>
            <NInput v-model:value="workflowName" placeholder="工作流名称" />
          </div>

          <!-- 参数映射表 -->
          <div>
            <div class="flex justify-between items-center mb-2">
              <NText strong>参数映射</NText>
              <NButton size="small" @click="addParam">+ 添加参数</NButton>
            </div>
            <div class="space-y-2">
              <div v-for="(p, i) in paramSchema" :key="i" class="border rounded p-2 space-y-2">
                <div class="flex gap-2 items-center">
                  <NInput v-model:value="p.key" placeholder="参数 key" style="width: 120px" />
                  <NInput v-model:value="p.label" placeholder="显示名称" style="width: 120px" />
                  <NSelect v-model:value="p.type" :options="[
                    { label: '文本', value: 'textarea' },
                    { label: '数字', value: 'int' },
                    { label: '小数', value: 'float' },
                    { label: '种子', value: 'seed' },
                    { label: '下拉', value: 'select' },
                    { label: '图片', value: 'image' },
                    { label: '视频', value: 'video' },
                    { label: '音频', value: 'audio' },
                    { label: '开关', value: 'bool' },
                  ]" style="width: 100px" />
                  <NSelect v-model:value="p.node" :options="nodeOptions" placeholder="节点" style="width: 160px" @update:value="(value) => importNodeChanged(p, value)" />
                  <NSelect v-model:value="p.path" :options="importInputPathOptions(p)" placeholder="参数名称" style="width: 140px" />
                  <NButton size="tiny" type="error" quaternary @click="delParam(i)">删</NButton>
                </div>
                <div class="flex gap-2">
                  <NInput v-if="p.type === 'select'" v-model:value="p.options_from" placeholder="options_from (如 image_width)" style="width: 200px" />
                  <NInputNumber v-if="'default' in p" v-model:value="p.default" placeholder="默认值" style="width: 120px" />
                </div>
              </div>
            </div>
          </div>

          <!-- 输出映射 -->
          <div>
            <NText depth="3" style="font-size: 12px">输出节点映射（JSON）</NText>
            <NInput v-model:value="outputMapping" type="textarea" :rows="3" />
          </div>

          <NSpace>
            <NButton @click="importStep = 'upload'">返回</NButton>
            <NButton type="primary" @click="saveImport">保存工作流</NButton>
          </NSpace>
        </NSpace>
      </template>
    </NModal>

    <!-- 添加版本弹窗 -->
    <NModal :show="showAddVersion" @update:show="showAddVersion = false" preset="card"
      :title="`添加版本 - ${selectedWf?.name || ''}`" style="max-width: 800px">
      <template v-if="versionStep === 'upload'">
        <NSpace vertical :size="12">
          <NText>上传新的 API JSON 文件作为新版本。</NText>
          <input type="file" accept=".json" @change="onVersionFileUpload" class="block mb-2" />
          <NInput v-model:value="versionRawJson" type="textarea" :rows="6" placeholder="或粘贴 JSON" />
          <NButton @click="parseVersionJson">解析 JSON</NButton>
        </NSpace>
      </template>
      <template v-else>
        <NSpace vertical :size="16">
          <NCard title="识别结果" size="small">
            <div class="text-sm">
              识别到 {{ versionParseResult?.nodes?.length }} 个节点，{{ versionParamSchema.length }} 个可配置参数
            </div>
          </NCard>
          <div class="flex justify-between items-center mb-2">
            <NText strong>参数映射</NText>
            <NButton size="small" @click="addVersionParam">+ 添加参数</NButton>
          </div>
          <div class="space-y-2">
            <div v-for="(p, i) in versionParamSchema" :key="i" class="border rounded p-2 space-y-2">
              <div class="flex gap-2 items-center">
                <NInput v-model:value="p.key" placeholder="参数 key" style="width: 120px" />
                <NInput v-model:value="p.label" placeholder="显示名称" style="width: 120px" />
                <NSelect v-model:value="p.type" :options="[
                  { label: '文本', value: 'textarea' },
                  { label: '数字', value: 'int' },
                  { label: '小数', value: 'float' },
                  { label: '种子', value: 'seed' },
                  { label: '下拉', value: 'select' },
                  { label: '图片', value: 'image' },
                  { label: '视频', value: 'video' },
                  { label: '音频', value: 'audio' },
                  { label: '开关', value: 'bool' },
                ]" style="width: 100px" />
                <NSelect v-model:value="p.node" :options="versionNodeOptions" placeholder="节点" style="width: 160px" @update:value="(value) => versionNodeChanged(p, value)" />
                <NSelect v-model:value="p.path" :options="versionInputPathOptions(p)" placeholder="参数名称" style="width: 140px" />
                <NButton size="tiny" type="error" quaternary @click="delVersionParam(i)">删</NButton>
              </div>
            </div>
          </div>
          <div>
            <NText depth="3" style="font-size: 12px">输出节点映射（JSON）</NText>
            <NInput v-model:value="versionOutputMapping" type="textarea" :rows="3" />
          </div>
          <NSpace>
            <NButton @click="versionStep = 'upload'">返回</NButton>
            <NButton type="primary" @click="saveAddVersion">保存版本</NButton>
          </NSpace>
        </NSpace>
      </template>
    </NModal>

    <!-- 编辑参数映射弹窗 -->
    <NModal :show="showEdit" @update:show="showEdit = false" preset="card"
      :title="`编辑工作流 - ${editWorkflowName || editWf?.name || ''}`" style="max-width: 800px">
      <NSpace vertical :size="16">
        <NCard title="基本信息" size="small">
          <NSpace vertical :size="12">
            <div>
              <NText depth="3" style="font-size: 12px">工作流名称</NText>
              <NInput v-model:value="editWorkflowName" placeholder="工作流名称" />
            </div>
            <div>
              <NText depth="3" style="font-size: 12px">重新上传工作流 JSON</NText>
              <input type="file" accept=".json,application/json" class="block mt-1" @change="onEditFileUpload" />
              <NText depth="3" style="font-size: 12px">
                {{ editJsonFileName ? `已解析：${editJsonFileName}` : '上传后会重新识别节点、参数映射和输出映射' }}
              </NText>
            </div>
          </NSpace>
        </NCard>
        <NCard title="参数映射" size="small">
          <div class="flex justify-end mb-2">
            <NButton size="small" @click="addEditParam">+ 添加参数</NButton>
          </div>
          <div class="space-y-2">
            <div v-for="(p, i) in editParamSchema" :key="i" class="border rounded p-2 space-y-2">
              <div class="flex gap-2 items-center flex-wrap">
                <NInput v-model:value="p.key" placeholder="参数 key" style="width: 120px" />
                <NInput v-model:value="p.label" placeholder="显示名称" style="width: 120px" />
                <NSelect v-model:value="p.type" :options="[
                  { label: '文本', value: 'textarea' },
                  { label: '数字', value: 'int' },
                  { label: '小数', value: 'float' },
                  { label: '种子', value: 'seed' },
                  { label: '下拉', value: 'select' },
                  { label: '图片', value: 'image' },
                  { label: '视频', value: 'video' },
                  { label: '音频', value: 'audio' },
                  { label: '开关', value: 'bool' },
                ]" style="width: 100px" />
                <NSelect v-model:value="p.node" :options="editNodeOptions" placeholder="节点" style="width: 160px" @update:value="(value) => editNodeChanged(p, value)" />
                <NSelect v-model:value="p.path" :options="editInputPathOptions(p)" placeholder="参数名称" style="width: 140px" />
                <NButton size="tiny" type="error" quaternary @click="delEditParam(i)">删</NButton>
              </div>
              <div class="flex gap-2 flex-wrap">
                <NInput v-if="p.type === 'select'" v-model:value="p.options_from" placeholder="options_from" style="width: 200px" />
                <NInputNumber v-if="'default' in p" v-model:value="p.default" placeholder="默认值" style="width: 120px" />
                <NInput v-if="p.random !== undefined" v-model:value="p.random" placeholder="random" style="width: 80px" />
              </div>
            </div>
          </div>
        </NCard>

        <div>
          <NText depth="3" style="font-size: 12px">输出节点映射（JSON）</NText>
          <NInput v-model:value="editOutputMapping" type="textarea" :rows="3" />
        </div>

        <NSpace>
          <NButton @click="showEdit = false">取消</NButton>
          <NButton type="primary" @click="saveEdit">保存修改</NButton>
        </NSpace>
      </NSpace>
    </NModal>
  </div>
</template>

<script lang="ts">
import { NH2, NSpace, NText, NButton, NModal, NInput, NSelect, NInputNumber, NCard } from 'naive-ui'
</script>
