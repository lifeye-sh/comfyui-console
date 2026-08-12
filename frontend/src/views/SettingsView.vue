<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useMessage, NH2, NCard, NSpace, NInput, NInputNumber, NSwitch, NButton, NText, NModal, NDynamicTags, NDivider, NSelect, NCheckbox } from 'naive-ui'
import { settingsApi, genTypeApi } from '@/api/modules'

const message = useMessage()
const settings = reactive<Record<string, any>>({})
const selectOptions = ref<Record<string, { label: string; options: any[]; default_value: any }>>({})
const loading = ref(false)
const editingKey = ref<string | null>(null)
const editingLabel = ref('')
const editingItems = ref<Array<{ label: string; value: any }>>([])
const editingDefaultValue = ref<any>(null)
const motionSchemes = ref<any[]>([])
const showSchemeEditor = ref(false)
const editingScheme = ref<any>(null)

const resolutionOptions = [
  { label: '480p', value: 1 }, { label: '576p（默认）', value: 2 },
  { label: '720p', value: 3 }, { label: '1080p', value: 4 },
]
const algorithmOptions = [
  { label: 'vitpose', value: 1 }, { label: 'sdpose', value: 2 }, { label: 'wuwupose', value: 3 },
]

async function load() {
  loading.value = true
  try {
    const [s, so, schemes] = await Promise.all([settingsApi.list(), settingsApi.getSelectOptions(), genTypeApi.motionTransferSchemes()])
    Object.assign(settings, s)
    selectOptions.value = so
    motionSchemes.value = schemes
  } catch {
    message.error('加载设置失败')
  } finally {
    loading.value = false
  }
}

function defaultSchemeParams() {
  return {
    frame_rate: 24, frame_load_cap: 0, resolution: 2, motion_algorithm: 1,
    expression_enabled: false, expression_strength: 1, camera_enabled: false,
    camera_strength: 1, lora_strength: 1,
  }
}

function openSchemeEditor(scheme?: any) {
  editingScheme.value = scheme
    ? { ...scheme, params: { ...scheme.params } }
    : { id: Date.now(), name: '', is_default: motionSchemes.value.length === 0, params: defaultSchemeParams() }
  showSchemeEditor.value = true
}

async function persistSchemes(items = motionSchemes.value) {
  motionSchemes.value = await genTypeApi.saveMotionTransferSchemes(items)
}

async function saveScheme() {
  if (!editingScheme.value?.name?.trim()) { message.warning('请输入方案名称'); return }
  const index = motionSchemes.value.findIndex((item) => item.id === editingScheme.value.id)
  const next = motionSchemes.value.map((item) => ({ ...item, is_default: editingScheme.value.is_default ? false : item.is_default }))
  if (index >= 0) next[index] = editingScheme.value
  else next.push(editingScheme.value)
  try { await persistSchemes(next); showSchemeEditor.value = false; message.success('参数方案已保存') }
  catch { message.error('参数方案保存失败') }
}

async function setDefaultScheme(id: number) {
  try {
    await persistSchemes(motionSchemes.value.map((item) => ({ ...item, is_default: item.id === id })))
    message.success('已设为默认方案')
  } catch { message.error('设置失败') }
}

async function deleteScheme(id: number) {
  try { await persistSchemes(motionSchemes.value.filter((item) => item.id !== id)); message.success('方案已删除') }
  catch { message.error('删除失败') }
}
onMounted(load)

async function save() {
  try {
    await settingsApi.patch(settings)
    message.success('设置已保存')
  } catch {
    message.error('保存失败')
  }
}

function openSelectEditor(key: string) {
  editingKey.value = key
  editingLabel.value = selectOptions.value[key]?.label || key
  editingItems.value = (selectOptions.value[key]?.options || []).map((o) => ({ ...o }))
  editingDefaultValue.value = selectOptions.value[key]?.default_value ?? editingItems.value[0]?.value ?? null
}

function addSelectItem() {
  editingItems.value.push({ label: '', value: isSizeOption() ? '1024x1024' : 0 })
}

function isSizeOption() {
  return editingKey.value === 'image_size' || editingKey.value === 'video_size'
}

function delSelectItem(i: number) {
  if (editingItems.value[i]?.value === editingDefaultValue.value) editingDefaultValue.value = null
  editingItems.value.splice(i, 1)
}

async function saveSelectOptions() {
  if (!editingKey.value) return
  if (isSizeOption()) {
    const invalid = editingItems.value.some((item) => !/^\d+[x×]\d+$/.test(String(item.value).trim()))
    if (invalid) {
      message.warning('尺寸值格式应为“宽x高”，例如 1280x720')
      return
    }
    editingItems.value = editingItems.value.map((item) => ({
      ...item,
      value: String(item.value).trim().replace('×', 'x'),
    }))
    editingDefaultValue.value = String(editingDefaultValue.value || '').replace('×', 'x')
  }
  if (!editingItems.value.some((item) => item.value === editingDefaultValue.value)) {
    message.warning('请选择一个默认值')
    return
  }
  try {
    await settingsApi.saveSelectOptions(editingKey.value, editingItems.value, editingDefaultValue.value)
    message.success('选择项已保存')
    editingKey.value = null
    await load()
  } catch {
    message.error('保存失败')
  }
}
</script>

<template>
  <div class="space-y-4">
    <NH2>平台设置</NH2>

    <!-- 通用设置 -->
    <NCard title="上传与任务" size="small">
      <NSpace vertical :size="12">
        <div>
          <NText depth="3" style="font-size: 12px">单文件上传上限（MB）</NText>
          <NInputNumber v-model:value="settings.max_upload_size_mb" :min="1" :max="2048" style="width: 100%" />
        </div>
        <div>
          <NText depth="3" style="font-size: 12px">任务超时（秒）</NText>
          <NInputNumber v-model:value="settings.task_timeout_seconds" :min="30" :max="7200" style="width: 100%" />
        </div>
        <div>
          <NText depth="3" style="font-size: 12px">最大重试次数</NText>
          <NInputNumber v-model:value="settings.max_retries" :min="0" :max="10" style="width: 100%" />
        </div>
        <div>
          <NText depth="3" style="font-size: 12px">节点默认并发</NText>
          <NInputNumber v-model:value="settings.default_max_concurrent" :min="1" :max="16" style="width: 100%" />
        </div>
      </NSpace>
    </NCard>

    <NCard title="分享与通知" size="small">
      <NSpace vertical :size="12">
        <div>
          <NText depth="3" style="font-size: 12px">分享默认有效期（小时）</NText>
          <NInputNumber v-model:value="settings.share_default_expire_hours" :min="1" :max="720" style="width: 100%" />
        </div>
        <div class="flex items-center gap-2">
          <NText>启用任务完成通知</NText>
          <NSwitch v-model:value="settings.enable_notification" />
        </div>
      </NSpace>
    </NCard>

    <NButton type="primary" @click="save">保存通用设置</NButton>

    <NDivider />

    <NH2>动作迁移参数方案</NH2>
    <NText depth="3" style="font-size: 12px">生成页面只选择方案，方案中的参数由此处统一维护。</NText>
    <div class="space-y-2 mt-3">
      <div v-for="scheme in motionSchemes" :key="scheme.id" class="border rounded p-3 flex justify-between items-center">
        <div>
          <NText strong>{{ scheme.name }}</NText>
          <span v-if="scheme.is_default" class="ml-2 text-xs text-green-600">默认</span>
          <div class="text-xs text-gray-500 mt-1">{{ scheme.params.frame_rate }} fps · {{ resolutionOptions.find(o => o.value === scheme.params.resolution)?.label }} · {{ algorithmOptions.find(o => o.value === scheme.params.motion_algorithm)?.label }}</div>
        </div>
        <div class="flex gap-2">
          <NButton v-if="!scheme.is_default" size="small" @click="setDefaultScheme(scheme.id)">设为默认</NButton>
          <NButton size="small" @click="openSchemeEditor(scheme)">编辑</NButton>
          <NButton size="small" type="error" quaternary :disabled="motionSchemes.length <= 1" @click="deleteScheme(scheme.id)">删除</NButton>
        </div>
      </div>
      <NButton dashed block @click="openSchemeEditor()">+ 新增参数方案</NButton>
    </div>

    <NModal v-model:show="showSchemeEditor" preset="card" title="动作迁移参数方案" style="max-width: 620px">
      <div v-if="editingScheme" class="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div class="md:col-span-2"><NText depth="3">方案名称</NText><NInput v-model:value="editingScheme.name" /></div>
        <div><NText depth="3">帧率</NText><NInputNumber v-model:value="editingScheme.params.frame_rate" :min="1" :max="120" style="width:100%" /></div>
        <div><NText depth="3">加载帧数上限</NText><NInputNumber v-model:value="editingScheme.params.frame_load_cap" :min="0" style="width:100%" /></div>
        <div><NText depth="3">分辨率</NText><NSelect v-model:value="editingScheme.params.resolution" :options="resolutionOptions" /></div>
        <div><NText depth="3">动作算法</NText><NSelect v-model:value="editingScheme.params.motion_algorithm" :options="algorithmOptions" /></div>
        <div><NText depth="3">Lora强度</NText><NInputNumber v-model:value="editingScheme.params.lora_strength" :min="0" :max="2" :step="0.05" style="width:100%" /></div>
        <div class="border rounded p-2"><NCheckbox v-model:checked="editingScheme.params.expression_enabled">表情开启</NCheckbox><NInputNumber v-model:value="editingScheme.params.expression_strength" :min="0" :max="2" :step="0.05" style="width:100%; margin-top:8px" /></div>
        <div class="border rounded p-2"><NCheckbox v-model:checked="editingScheme.params.camera_enabled">运镜开启</NCheckbox><NInputNumber v-model:value="editingScheme.params.camera_strength" :min="0" :max="2" :step="0.05" style="width:100%; margin-top:8px" /></div>
        <div class="md:col-span-2"><NCheckbox v-model:checked="editingScheme.is_default">设为默认方案</NCheckbox></div>
        <NButton class="md:col-span-2" type="primary" @click="saveScheme">保存方案</NButton>
      </div>
    </NModal>

    <NDivider />

    <!-- 选择项维护 -->
    <NH2>选择项维护</NH2>
    <NText depth="3" style="font-size: 12px">
      管理图片尺寸、视频尺寸、帧数和帧率选项。尺寸值使用“宽x高”格式，修改后生成页面会立即使用新选项。
    </NText>

    <div class="space-y-2">
      <div
        v-for="(info, key) in selectOptions"
        :key="key"
        class="border rounded p-3 flex justify-between items-center"
      >
        <div>
          <NText strong>{{ info.label }}</NText>
          <div class="text-xs text-gray-500 mt-1">
            {{ info.options.map((o) => o.label).join('、') }}
          </div>
          <div class="text-xs text-green-600 mt-1">默认：{{ info.options.find((o) => o.value === info.default_value)?.label || info.default_value }}</div>
        </div>
        <NButton size="small" @click="openSelectEditor(key as string)">编辑选项</NButton>
      </div>
    </div>

    <!-- 选择项编辑弹窗 -->
    <NModal :show="!!editingKey" @update:show="editingKey = null" preset="card" :title="`编辑「${editingLabel}」选项`" style="max-width: 500px">
      <NSpace vertical :size="12">
        <div>
          <NText depth="3" style="font-size: 12px">默认值</NText>
          <NSelect v-model:value="editingDefaultValue" :options="editingItems.filter(item => item.label).map(item => ({ label: item.label, value: item.value }))" placeholder="请选择默认值" />
        </div>
        <div v-for="(item, i) in editingItems" :key="i" class="flex gap-2 items-center">
          <NInput v-model:value="item.label" placeholder="显示名称" style="flex: 1" />
          <NInput v-if="isSizeOption()" v-model:value="item.value" placeholder="如 1280x720" style="width: 150px" />
          <NInputNumber v-else v-model:value="item.value" placeholder="数值" style="width: 120px" />
          <NButton size="small" type="error" quaternary @click="delSelectItem(i)">删除</NButton>
        </div>
        <NButton size="small" dashed block @click="addSelectItem">+ 添加选项</NButton>
        <NButton type="primary" block @click="saveSelectOptions">保存</NButton>
      </NSpace>
    </NModal>
  </div>
</template>
