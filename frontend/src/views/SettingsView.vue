<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { genTypeApi, settingsApi } from '@/api/modules'
import GlassCard from '@/v2/components/GlassCard.vue'
import GlassDrawer from '@/v2/components/GlassDrawer.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'
import V2Field from '@/v2/components/V2Field.vue'

type OptionItem = { label: string; value: any }
type SelectOption = { label: string; options: OptionItem[]; default_value: any; value_type?: 'string' | 'number'; custom?: boolean }
type MotionScheme = { id: number; name: string; is_default: boolean; params: Record<string, any> }

const message = useMessage()
const settings = reactive<Record<string, any>>({})
const selectOptions = ref<Record<string, SelectOption>>({})
const motionSchemes = ref<MotionScheme[]>([])
const loading = ref(false)
const savingGeneral = ref(false)
const savingDrawer = ref(false)
const editingScheme = ref<MotionScheme | null>(null)
const editingKey = ref<string | null>(null)
const editingLabel = ref('')
const editingItems = ref<OptionItem[]>([])
const editingDefaultValue = ref<any>(null)
const creatingOptionProject = ref(false)
const newOptionProjectLabel = ref('')
const newOptionProjectValueType = ref<'string' | 'number'>('string')

const resolutionOptions = [
  { label: '480p', value: 1 }, { label: '576p（默认）', value: 2 },
  { label: '720p', value: 3 }, { label: '1080p', value: 4 },
]
const algorithmOptions = [
  { label: 'vitpose', value: 1 }, { label: 'sdpose', value: 2 }, { label: 'wuwupose', value: 3 },
]
const optionEntries = computed(() => Object.entries(selectOptions.value))
const isSizeOption = computed(() => editingKey.value === 'image_size' || editingKey.value === 'video_size')
const isStringOption = computed(() => isSizeOption.value || selectOptions.value[editingKey.value || '']?.value_type !== 'number')

async function load() {
  loading.value = true
  try {
    const [general, options, schemes] = await Promise.all([
      settingsApi.list(), settingsApi.getSelectOptions(), genTypeApi.motionTransferSchemes(),
    ])
    Object.assign(settings, general)
    selectOptions.value = options
    motionSchemes.value = schemes
  } catch { message.error('加载系统设置失败') }
  finally { loading.value = false }
}

async function saveGeneral() {
  savingGeneral.value = true
  try { await settingsApi.patch(settings); message.success('通用设置已保存') }
  catch { message.error('保存设置失败') }
  finally { savingGeneral.value = false }
}

function defaultSchemeParams() {
  return { frame_rate: 24, frame_load_cap: 0, resolution: 2, motion_algorithm: 1, expression_enabled: false, expression_strength: 1, camera_enabled: false, camera_strength: 1, lora_strength: 1 }
}
function openSchemeEditor(scheme?: MotionScheme) {
  editingScheme.value = scheme
    // ref 数组中的方案是 Vue 响应式代理，structuredClone(proxy) 会抛出 DataCloneError。
    ? JSON.parse(JSON.stringify(scheme))
    : { id: Date.now(), name: '', is_default: !motionSchemes.value.length, params: defaultSchemeParams() }
}
async function persistSchemes(items: MotionScheme[]) {
  savingDrawer.value = true
  try { motionSchemes.value = await genTypeApi.saveMotionTransferSchemes(items); message.success('参数方案已保存'); editingScheme.value = null }
  catch { message.error('参数方案保存失败') }
  finally { savingDrawer.value = false }
}
async function saveScheme() {
  if (!editingScheme.value?.name.trim()) { message.warning('请输入方案名称'); return }
  let next = motionSchemes.value.map(item => ({ ...item, is_default: editingScheme.value?.is_default ? false : item.is_default }))
  const index = next.findIndex(item => item.id === editingScheme.value!.id)
  if (index >= 0) next.splice(index, 1, editingScheme.value)
  else next.push(editingScheme.value)
  await persistSchemes(next)
}
async function setDefaultScheme(id: number) { await persistSchemes(motionSchemes.value.map(item => ({ ...item, is_default: item.id === id }))) }
async function deleteScheme(id: number) {
  if (motionSchemes.value.length <= 1) { message.warning('至少保留一个参数方案'); return }
  if (confirm('确定删除这个动作迁移参数方案？')) await persistSchemes(motionSchemes.value.filter(item => item.id !== id))
}

function openSelectEditor(key: string) {
  editingKey.value = key
  editingLabel.value = selectOptions.value[key]?.label || key
  editingItems.value = (selectOptions.value[key]?.options || []).map(item => ({ ...item }))
  editingDefaultValue.value = selectOptions.value[key]?.default_value ?? editingItems.value[0]?.value ?? null
}
function addSelectItem() { editingItems.value.push({ label: '', value: isSizeOption.value ? '1024x1024' : isStringOption.value ? '' : 0 }) }
function deleteSelectItem(index: number) {
  if (editingItems.value[index]?.value === editingDefaultValue.value) editingDefaultValue.value = null
  editingItems.value.splice(index, 1)
}
async function saveSelectOptions() {
  if (!editingKey.value) return
  if (isSizeOption.value) {
    if (editingItems.value.some(item => !/^\d+[x×]\d+$/.test(String(item.value).trim()))) { message.warning('尺寸格式应为“宽x高”，例如 1280x720'); return }
    editingItems.value = editingItems.value.map(item => ({ ...item, value: String(item.value).trim().replace('×', 'x') }))
    editingDefaultValue.value = String(editingDefaultValue.value || '').replace('×', 'x')
  }
  if (!editingItems.value.some(item => item.value === editingDefaultValue.value)) { message.warning('请选择一个默认值'); return }
  savingDrawer.value = true
  try {
    await settingsApi.saveSelectOptions(editingKey.value, editingItems.value, editingDefaultValue.value)
    message.success('选择项已保存'); editingKey.value = null; await load()
  } catch { message.error('选择项保存失败') }
  finally { savingDrawer.value = false }
}
async function createOptionProject() {
  const label = newOptionProjectLabel.value.trim()
  if (!label) { message.warning('请输入项目名称'); return }
  savingDrawer.value = true
  try {
    const created = await settingsApi.createSelectOptionProject(label, newOptionProjectValueType.value)
    creatingOptionProject.value = false; newOptionProjectLabel.value = ''; newOptionProjectValueType.value = 'string'
    await load(); openSelectEditor(created.key); message.success('选择项项目已创建，请继续添加选项')
  } catch (event: any) { message.error(event.response?.data?.detail || '新增选择项项目失败') }
  finally { savingDrawer.value = false }
}
async function deleteOptionProject(key: string, label: string) {
  if (!confirm(`确定删除选择项项目“${label}”？该项目的选项和默认值也会删除。`)) return
  try { await settingsApi.deleteSelectOptionProject(key); await load(); message.success('选择项项目已删除') }
  catch (event: any) { message.error(event.response?.data?.detail || '删除选择项项目失败') }
}
function defaultLabel(info: SelectOption) { return info.options.find(item => item.value === info.default_value)?.label || info.default_value }
function resolutionLabel(value: number) { return resolutionOptions.find(item => item.value === value)?.label || value }
function algorithmLabel(value: number) { return algorithmOptions.find(item => item.value === value)?.label || value }

onMounted(load)
</script>

<template>
  <div class="v2-page v2-theme settings-page">
    <div class="v2-page-heading heading">
      <div><StatusBadge tone="info">系统配置</StatusBadge><h1>系统设置</h1><p>维护平台运行参数、动作迁移方案和生成页面的公共选项。</p></div>
      <V2Button :disabled="loading" @click="load">{{ loading ? '加载中…' : '刷新设置' }}</V2Button>
    </div>

    <nav class="section-nav" aria-label="设置分区">
      <a href="#general"><span>01</span><b>平台参数</b><small>上传、任务和通知</small></a>
      <a href="#motion"><span>02</span><b>动作迁移方案</b><small>算法与强度预设</small></a>
      <a href="#options"><span>03</span><b>选项维护</b><small>尺寸、比例、帧数和帧率</small></a>
    </nav>

    <section id="general" class="settings-section">
      <header class="section-heading"><div><span class="section-icon">⚙</span><div><h2>平台参数</h2><p>控制文件上传、任务执行以及系统通知的默认行为。</p></div></div><V2Button variant="primary" :disabled="savingGeneral" @click="saveGeneral">{{ savingGeneral ? '保存中…' : '保存平台参数' }}</V2Button></header>
      <div class="general-grid">
        <GlassCard class="setting-card">
          <div class="card-title"><span>↥</span><div><h3>上传与任务</h3><p>资源限制和任务调度的基础参数</p></div></div>
          <div class="field-grid">
            <V2Field label="单文件上传上限" hint="允许上传的单个文件最大体积（MB）"><input v-model.number="settings.max_upload_size_mb" type="number" min="1" max="2048"/><i>MB</i></V2Field>
            <V2Field label="任务超时时间" hint="任务超过该时长后进入超时处理（秒）"><input v-model.number="settings.task_timeout_seconds" type="number" min="30" max="7200"/><i>秒</i></V2Field>
            <V2Field label="最大重试次数" hint="执行失败后允许自动重试的次数"><input v-model.number="settings.max_retries" type="number" min="0" max="10"/><i>次</i></V2Field>
            <V2Field label="节点默认并发" hint="新节点未单独配置时使用的并发数"><input v-model.number="settings.default_max_concurrent" type="number" min="1" max="16"/><i>任务</i></V2Field>
          </div>
        </GlassCard>
        <GlassCard class="setting-card">
          <div class="card-title"><span>⌁</span><div><h3>分享与通知</h3><p>控制分享链接和完成提醒</p></div></div>
          <div class="field-grid single">
            <V2Field label="分享默认有效期" hint="新建分享链接时默认使用的有效时长"><input v-model.number="settings.share_default_expire_hours" type="number" min="1" max="720"/><i>小时</i></V2Field>
            <label class="switch-row"><div><b>任务完成通知</b><small>任务成功或失败后发送站内提醒</small></div><input v-model="settings.enable_notification" type="checkbox"/><span aria-hidden="true"/></label>
          </div>
        </GlassCard>
      </div>
    </section>

    <section id="motion" class="settings-section">
      <header class="section-heading"><div><span class="section-icon">◇</span><div><h2>动作迁移参数方案</h2><p>生成页面只选择方案，具体算法参数在这里统一维护。</p></div></div><V2Button variant="primary" @click="openSchemeEditor()">新增方案</V2Button></header>
      <div class="scheme-grid">
        <GlassCard v-for="scheme in motionSchemes" :key="scheme.id" class="scheme-card" interactive>
          <header><div><h3>{{ scheme.name }}</h3><StatusBadge v-if="scheme.is_default" tone="success">默认方案</StatusBadge></div><small>#{{ scheme.id }}</small></header>
          <div class="scheme-summary"><span><small>帧率</small><b>{{ scheme.params.frame_rate }} fps</b></span><span><small>分辨率</small><b>{{ resolutionLabel(scheme.params.resolution) }}</b></span><span><small>动作算法</small><b>{{ algorithmLabel(scheme.params.motion_algorithm) }}</b></span><span><small>Lora 强度</small><b>{{ scheme.params.lora_strength }}</b></span></div>
          <div class="feature-tags"><span :class="{on:scheme.params.expression_enabled}">表情 {{ scheme.params.expression_enabled ? '开启' : '关闭' }}</span><span :class="{on:scheme.params.camera_enabled}">运镜 {{ scheme.params.camera_enabled ? '开启' : '关闭' }}</span></div>
          <footer><V2Button v-if="!scheme.is_default" variant="ghost" @click="setDefaultScheme(scheme.id)">设为默认</V2Button><V2Button @click="openSchemeEditor(scheme)">编辑</V2Button><V2Button variant="danger" :disabled="motionSchemes.length<=1" @click="deleteScheme(scheme.id)">删除</V2Button></footer>
        </GlassCard>
        <button class="add-card" @click="openSchemeEditor()"><span>＋</span><b>新增参数方案</b><small>创建另一组动作迁移预设</small></button>
      </div>
    </section>

    <section id="options" class="settings-section">
      <header class="section-heading"><div><span class="section-icon">☷</span><div><h2>选择项维护</h2><p>统一管理内置和自定义选择项，修改后生成类型参数设计可立即引用。</p></div></div><V2Button variant="primary" @click="creatingOptionProject=true">新增项目</V2Button></header>
      <GlassCard padding="sm" class="option-list">
        <article v-for="([key, info]) in optionEntries" :key="key">
          <div class="option-icon">{{ String(info.label).includes('图片') ? '▧' : String(info.label).includes('视频') ? '▷' : '≡' }}</div>
          <div class="option-main"><div><h3>{{ info.label }}</h3><StatusBadge tone="success">默认：{{ defaultLabel(info) }}</StatusBadge></div><p>{{ info.options.map(item => item.label).join('、') }}</p></div>
          <div class="option-actions"><V2Button variant="primary" @click="openSelectEditor(key)">编辑选项</V2Button><V2Button v-if="info.custom" variant="danger" @click="deleteOptionProject(key,info.label)">删除项目</V2Button></div>
        </article>
      </GlassCard>
    </section>

    <GlassDrawer :open="!!editingScheme" title="动作迁移参数方案" @close="editingScheme=null">
      <div v-if="editingScheme" class="drawer-form">
        <V2Field label="方案名称" required><input v-model="editingScheme.name" placeholder="输入方案名称"/></V2Field>
        <div class="drawer-grid"><V2Field label="帧率"><input v-model.number="editingScheme.params.frame_rate" type="number" min="1" max="120"/></V2Field><V2Field label="加载帧数上限"><input v-model.number="editingScheme.params.frame_load_cap" type="number" min="0"/></V2Field><V2Field label="分辨率"><select v-model.number="editingScheme.params.resolution"><option v-for="item in resolutionOptions" :key="item.value" :value="item.value">{{ item.label }}</option></select></V2Field><V2Field label="动作算法"><select v-model.number="editingScheme.params.motion_algorithm"><option v-for="item in algorithmOptions" :key="item.value" :value="item.value">{{ item.label }}</option></select></V2Field><V2Field label="表情强度"><input v-model.number="editingScheme.params.expression_strength" type="number" min="0" max="2" step=".05"/></V2Field><V2Field label="运镜强度"><input v-model.number="editingScheme.params.camera_strength" type="number" min="0" max="2" step=".05"/></V2Field><V2Field label="Lora 强度"><input v-model.number="editingScheme.params.lora_strength" type="number" min="0" max="2" step=".05"/></V2Field></div>
        <label class="switch-row compact"><div><b>开启表情</b></div><input v-model="editingScheme.params.expression_enabled" type="checkbox"/><span/></label><label class="switch-row compact"><div><b>开启运镜</b></div><input v-model="editingScheme.params.camera_enabled" type="checkbox"/><span/></label><label class="switch-row compact"><div><b>设为默认方案</b></div><input v-model="editingScheme.is_default" type="checkbox"/><span/></label>
        <V2Button variant="primary" :disabled="savingDrawer" @click="saveScheme">{{ savingDrawer ? '保存中…' : '保存方案' }}</V2Button>
      </div>
    </GlassDrawer>

    <GlassDrawer :open="!!editingKey" :title="`编辑“${editingLabel}”选项`" @close="editingKey=null">
      <div class="drawer-form"><V2Field label="默认值"><select v-model="editingDefaultValue"><option v-for="item in editingItems.filter(item=>item.label)" :key="String(item.value)" :value="item.value">{{ item.label }}</option></select></V2Field><div class="option-editor"><div v-for="(item,index) in editingItems" :key="index"><input v-model="item.label" placeholder="显示名称"/><input v-if="isStringOption" v-model="item.value" :placeholder="isSizeOption ? '如 1280x720' : '如 16:9'"/><input v-else v-model.number="item.value" type="number" placeholder="数值"/><button aria-label="删除选项" @click="deleteSelectItem(index)">×</button></div></div><V2Button variant="ghost" @click="addSelectItem">＋ 添加选项</V2Button><V2Button variant="primary" :disabled="savingDrawer" @click="saveSelectOptions">{{ savingDrawer ? '保存中…' : '保存选项' }}</V2Button></div>
    </GlassDrawer>

    <GlassDrawer :open="creatingOptionProject" title="新增选择项项目" @close="creatingOptionProject=false">
      <div class="drawer-form">
        <V2Field label="项目名称" required hint="将在生成类型的参数设计中作为选项来源显示"><input v-model="newOptionProjectLabel" maxlength="80" placeholder="例如：H3 视频模型"/></V2Field>
        <V2Field label="选项值类型" hint="文本适合比例、模型名；数字适合帧率、步数"><select v-model="newOptionProjectValueType"><option value="string">文本</option><option value="number">数字</option></select></V2Field>
        <V2Button variant="primary" :disabled="savingDrawer" @click="createOptionProject">{{ savingDrawer ? '创建中…' : '创建并添加选项' }}</V2Button>
      </div>
    </GlassDrawer>
  </div>
</template>

<style scoped>
.settings-page{max-width:1480px}.heading,.section-heading,.section-heading>div,.card-title,.scheme-card header,.scheme-card header>div,.scheme-card footer,.option-list article,.option-main>div{display:flex;align-items:center}.heading{align-items:flex-end;justify-content:space-between;gap:18px}.heading h1{margin-top:14px}.section-nav{margin-bottom:26px;display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.section-nav a{min-height:76px;padding:14px 16px;display:grid;grid-template-columns:36px 1fr;column-gap:11px;align-items:center;color:var(--v2-text);text-decoration:none;background:var(--v2-surface);border:1px solid var(--v2-border);border-radius:15px;box-shadow:var(--v2-shadow-soft);backdrop-filter:blur(var(--v2-blur));transition:.18s}.section-nav a:hover{transform:translateY(-2px);border-color:var(--v2-primary)}.section-nav span,.section-icon,.card-title>span,.option-icon{display:grid;place-items:center;background:rgba(130,149,255,.13);border:1px solid rgba(130,149,255,.2);border-radius:10px}.section-nav span{grid-row:1/3;width:36px;height:36px;color:var(--v2-primary);font-size:11px}.section-nav small{color:var(--v2-text-muted)}.settings-section{padding:8px 0 32px;scroll-margin-top:90px}.section-heading{margin-bottom:14px;justify-content:space-between;gap:16px}.section-heading>div{gap:12px}.section-heading h2,.section-heading p,.card-title h3,.card-title p,.scheme-card h3,.option-main h3,.option-main p{margin:0}.section-heading h2{font-size:20px}.section-heading p,.card-title p{margin-top:4px;color:var(--v2-text-muted);font-size:12px}.section-icon{width:42px;height:42px;color:var(--v2-primary);font-size:20px}.general-grid{display:grid;grid-template-columns:1.45fr 1fr;gap:14px}.setting-card{min-width:0}.card-title{gap:11px;margin-bottom:20px}.card-title>span{width:40px;height:40px;color:var(--v2-primary);font-size:20px}.field-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.field-grid.single{grid-template-columns:1fr}.field-grid :deep(.v2-field){position:relative}.field-grid :deep(.v2-field>i){position:absolute;right:12px;top:39px;color:var(--v2-text-subtle);font-size:11px;font-style:normal}.field-grid :deep(input){padding-right:52px}.switch-row{min-height:69px;padding:12px;display:flex;align-items:center;gap:14px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:12px;cursor:pointer}.switch-row>div{flex:1;display:grid;gap:5px}.switch-row small{color:var(--v2-text-muted)}.switch-row input{display:none}.switch-row>span{width:40px;height:23px;padding:3px;background:#536176;border-radius:20px;transition:.2s}.switch-row>span:after{content:'';display:block;width:17px;height:17px;background:#fff;border-radius:50%;transition:.2s}.switch-row input:checked+span{background:var(--v2-primary-strong)}.switch-row input:checked+span:after{transform:translateX(17px)}.switch-row.compact{min-height:48px}.scheme-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.scheme-card{display:flex;flex-direction:column}.scheme-card header{justify-content:space-between;gap:10px}.scheme-card header>div{gap:8px}.scheme-card header>small{color:var(--v2-text-subtle)}.scheme-summary{margin:18px 0 12px;display:grid;grid-template-columns:1fr 1fr;gap:8px}.scheme-summary span{padding:9px;display:grid;gap:4px;background:var(--v2-surface-soft);border-radius:9px}.scheme-summary small{color:var(--v2-text-subtle);font-size:10px}.feature-tags{display:flex;gap:7px;margin-bottom:18px}.feature-tags span{padding:5px 8px;color:var(--v2-text-muted);background:var(--v2-surface-soft);border-radius:7px;font-size:11px}.feature-tags span.on{color:var(--v2-success);background:rgba(86,214,161,.1)}.scheme-card footer{margin-top:auto;justify-content:flex-end;gap:7px}.add-card{min-height:265px;display:grid;place-items:center;align-content:center;gap:8px;color:var(--v2-text-muted);background:rgba(255,255,255,.018);border:1px dashed var(--v2-border-strong);border-radius:var(--v2-radius-lg);cursor:pointer}.add-card:hover{color:var(--v2-text);border-color:var(--v2-primary);background:rgba(130,149,255,.05)}.add-card span{font-size:30px}.add-card small{color:var(--v2-text-subtle)}.option-list{display:grid;gap:2px}.option-list article{min-height:86px;padding:12px 10px;gap:14px;border-bottom:1px solid var(--v2-border)}.option-list article:last-child{border:0}.option-icon{width:42px;height:42px;color:var(--v2-primary);font-size:20px}.option-main{min-width:0;flex:1}.option-main>div{gap:9px}.option-main p{margin-top:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--v2-text-muted);font-size:12px}.drawer-form{display:grid;gap:14px}.drawer-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.option-editor{display:grid;gap:8px}.option-editor>div{display:grid;grid-template-columns:1fr 140px 36px;gap:7px}.option-editor input{min-width:0;min-height:42px;padding:9px 11px;color:var(--v2-text);background:rgba(3,12,25,.42);border:1px solid var(--v2-border);border-radius:9px;outline:none}.option-editor button{color:var(--v2-danger);background:rgba(255,127,145,.08);border:1px solid rgba(255,127,145,.2);border-radius:9px;cursor:pointer}@media(max-width:1100px){.scheme-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:850px){.general-grid{grid-template-columns:1fr}.section-nav{grid-template-columns:1fr 1fr 1fr}.section-nav a{grid-template-columns:1fr;text-align:center}.section-nav span{grid-row:auto;margin:auto}.section-nav small{display:none}}@media(max-width:650px){.heading,.section-heading{align-items:flex-start;flex-direction:column}.heading>*:last-child,.section-heading>*:last-child{width:100%}.section-nav{grid-template-columns:1fr}.section-nav a{min-height:58px;grid-template-columns:36px 1fr;text-align:left}.section-nav span{grid-row:1/3;margin:0}.section-nav small{display:block}.field-grid,.scheme-grid,.drawer-grid{grid-template-columns:1fr}.option-list article{align-items:flex-start;flex-wrap:wrap}.option-main{width:calc(100% - 58px)}.option-list article>.v2-button{width:100%}.option-editor>div{grid-template-columns:1fr 1fr 36px}}
</style>

<style scoped>
/* 选项行固定保留操作列，长内容只能在中间信息列内换行。 */
.settings-page { min-width: 0; overflow-x: clip; }
.option-list { min-width: 0; overflow: hidden; }
.option-list article {
  width: 100%;
  min-width: 0;
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr) max-content;
  align-items: center;
}
.option-icon { flex: none; }
.option-main { width: 100%; min-width: 0; overflow: hidden; }
.option-main > div { min-width: 0; flex-wrap: wrap; }
.option-main h3 { min-width: 0; overflow-wrap: anywhere; }
.option-main p {
  width: 100%;
  max-width: 100%;
  white-space: normal;
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.option-actions { flex: none; padding-left: 8px; }
.option-actions :deep(.v2-button) { min-width: 96px; }
.option-editor, .option-editor > div, .drawer-form { min-width: 0; }

@media (max-width: 650px) {
  .option-list article {
    grid-template-columns: 42px minmax(0, 1fr);
    align-items: start;
  }
  .option-main { width: auto; }
  .option-actions { grid-column: 1 / -1; width: 100%; padding: 2px 0 0; }
  .option-actions :deep(.v2-button) { width: 100%; }
}

@media (max-width: 430px) {
  .option-editor > div { grid-template-columns: minmax(0, 1fr) 36px; }
  .option-editor > div input:first-child { grid-column: 1 / -1; }
}
</style>
