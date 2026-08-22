<template>
  <div class="space-y-4">
    <!-- 标题栏 -->
    <div class="flex justify-between items-center">
      <NH2 style="margin: 0">{{ typeInfo?.name || route.params.code }}</NH2>
      <div class="flex gap-2">
        <NSelect
          v-model:value="globalWorkflowVersionId"
          :options="workflowOptions"
          size="small"
          style="width: 200px"
          placeholder="生成 API（工作流）"
          @update:value="applyGlobalWorkflowToAll"
        />
        <NButton size="small" @click="showImport = true">导入</NButton>
        <NButton size="small" @click="showSave = true">SAVE</NButton>
        <NButton size="small" @click="router.push(`/wf/${route.params.code}`)">工作流管理</NButton>
      </div>
    </div>

    <!-- 全局设置区 -->
    <NCard title="全局设置" size="small">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <NText depth="3" style="font-size: 12px">全局提示词 1</NText>
          <NInput v-model:value="global1" type="textarea" :rows="2" placeholder="全局提示词 1" />
        </div>
        <div>
          <NText depth="3" style="font-size: 12px">全局提示词 2</NText>
          <NInput v-model:value="global2" type="textarea" :rows="2" placeholder="全局提示词 2" />
        </div>
      </div>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
        <div v-if="hasSizeOptions" class="md:col-span-2">
          <NText depth="3" style="font-size: 12px">默认{{ sizeLabel }}</NText>
          <NSelect v-model:value="defaultSize" :options="sizeOptions" @update:value="applyDefaultSize" />
        </div>
        <div v-if="hasDuration">
          <NText depth="3" style="font-size: 12px">默认视频时长（秒）</NText>
          <NInputNumber v-model:value="defaultDuration" :min="1" :max="600" :step="1" style="width: 100%" @update:value="applyDefaultDuration" />
        </div>
        <div v-if="hasSeed">
          <NText depth="3" style="font-size: 12px">默认种子</NText>
          <NInputNumber v-model:value="defaultSeed" :step="1" style="width: 100%" :disabled="useRandomSeed" />
        </div>
        <div v-if="hasSeed" class="flex items-end gap-2">
          <NCheckbox v-model:checked="useRandomSeed" @update:checked="applyGlobalSeedToAll">随机种子</NCheckbox>
        </div>
      </div>
    </NCard>

    <!-- 任务行表格 -->
    <NCard size="small">
      <template #header>
        <div class="flex justify-between items-center">
          <span>任务行 ({{ rows.length }})</span>
          <div class="flex gap-2">
            <NButton size="small" @click="addRow">+ 添加行</NButton>
            <NButton size="small" type="primary" :disabled="!rows.length" @click="submit">批量生成</NButton>
          </div>
        </div>
      </template>

      <!-- 桌面端表格 -->
      <div class="hidden md:block overflow-x-auto">
        <table class="w-full text-sm border-collapse">
          <thead>
            <tr class="border-b bg-gray-50">
              <th class="p-2 text-left" style="width: 30px">#</th>
              <th v-if="!isMotionTransfer" class="p-2 text-left" style="min-width: 200px">提示词</th>
              <th class="p-2 text-left" v-for="p in extraParams" :key="p.key" style="width: 120px">{{ p.label || p.key }}</th>
              <th v-if="isMotionTransfer" class="p-2 text-left" style="width: 160px">参数方案</th>
              <th v-if="scalarParams.length" class="p-2 text-left" style="min-width: 220px">参数设置</th>
              <th v-if="hasSizeOptions" class="p-2 text-left" style="min-width: 190px">{{ sizeLabel }}</th>
              <th v-if="hasDuration" class="p-2 text-left" style="width: 110px">视频时长</th>
              <th v-if="hasSeed" class="p-2 text-left" style="width: 110px">种子</th>
              <th class="p-2 text-left" style="width: 140px">工作流</th>
              <th class="p-2 text-center" style="width: 70px">状态</th>
              <th class="p-2 text-center" style="min-width: 180px">输出预览</th>
              <th class="p-2 text-center" style="width: 130px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in rows" :key="i" class="border-b hover:bg-gray-50">
              <td class="p-2 text-gray-400">{{ i + 1 }}</td>
              <td v-if="!isMotionTransfer" class="p-2">
                <NInput v-model:value="row.prompt" type="textarea" :rows="2" placeholder="提示词" size="small" :disabled="['PENDING','RUNNING'].includes(row.status)" />
                <NSelect
                  v-if="prompts.length"
                  :options="prompts.map((p) => ({ label: p.name, value: p.id }))"
                  placeholder="提示词库"
                  size="tiny"
                  style="margin-top: 4px; width: 160px"
                  :disabled="['PENDING','RUNNING'].includes(row.status)"
                  @update:value="(v: number) => applyPrompt(row, prompts.find((p) => p.id === v))"
                />
              </td>
              <!-- 资源槽位 -->
              <td class="p-2" v-for="p in extraParams" :key="p.key">
                <div class="space-y-1">
                  <input
                    type="file"
                    :accept="p.type === 'image' ? 'image/*' : p.type === 'video' ? 'video/*' : 'audio/*'"
                    @change="(e: any) => e.target.files?.[0] && uploadResource(row, p.key, e.target.files[0], p.type)"
                    class="block text-xs w-28"
                    :disabled="['PENDING','RUNNING'].includes(row.status)"
                  />
                  <NButton size="tiny" block :disabled="['PENDING','RUNNING'].includes(row.status)" @click="openResourcePicker(row, p)">从素材库选择</NButton>
                  <NText v-if="row.extra[p.key]" type="success" style="font-size: 11px">✓ {{ selectedResourceLabel(row.extra[p.key]) }}</NText>
                  <img
                    v-if="row.inputPreviews[p.key]?.media_type === 'image'"
                    :src="row.inputPreviews[p.key].url"
                    class="w-28 h-20 object-contain bg-gray-100 rounded cursor-pointer"
                    @click="openOutput(row.inputPreviews[p.key])"
                  />
                  <button
                    v-else-if="row.inputPreviews[p.key]?.media_type === 'video'"
                    class="relative w-28 h-20 bg-gray-100 rounded overflow-hidden"
                    @click="openOutput(row.inputPreviews[p.key])"
                  >
                    <img :src="row.inputPreviews[p.key].url" class="w-full h-full object-contain" />
                    <span class="absolute inset-0 flex items-center justify-center text-white text-xl bg-black/20">▶</span>
                  </button>
                  <audio v-else-if="row.inputPreviews[p.key]?.media_type === 'audio'" :src="row.inputPreviews[p.key].url" controls class="w-40 max-w-full" />
                </div>
              </td>
              <td v-if="isMotionTransfer" class="p-2 align-top">
                <NSelect v-model:value="row.parameter_scheme_id" :options="parameterSchemeOptions" size="small" placeholder="选择参数方案" :disabled="['PENDING','RUNNING'].includes(row.status)" />
              </td>
              <td v-if="scalarParams.length" class="p-2 align-top">
                <div class="grid grid-cols-2 gap-2 min-w-[220px]">
                  <div v-for="p in scalarParams" :key="p.key">
                    <NText depth="3" style="font-size: 11px">{{ p.label || p.key }}</NText>
                    <NSelect v-if="p.type === 'select'" v-model:value="row.extra[p.key]" :options="p.options || []" size="small" :disabled="['PENDING','RUNNING'].includes(row.status)" />
                    <NCheckbox v-else-if="p.type === 'bool'" v-model:checked="row.extra[p.key]" size="small" :disabled="['PENDING','RUNNING'].includes(row.status)">开启</NCheckbox>
                    <NInputNumber v-else v-model:value="row.extra[p.key]" :min="p.min" :max="p.max" :step="p.step || (p.type === 'int' ? 1 : 0.05)" size="small" style="width: 100%" :disabled="['PENDING','RUNNING'].includes(row.status)" />
                  </div>
                </div>
              </td>
              <td v-if="hasSizeOptions" class="p-2">
                <NSelect v-model:value="row.size" :options="sizeOptions" size="small" :disabled="['PENDING','RUNNING'].includes(row.status)" @update:value="(value: string) => applyRowSize(row, value)" />
              </td>
              <td v-if="hasDuration" class="p-2">
                <NInputNumber v-model:value="row.duration" :min="1" :max="600" :step="1" size="small" style="width: 90px" :disabled="['PENDING','RUNNING'].includes(row.status)">
                  <template #suffix>秒</template>
                </NInputNumber>
              </td>
              <td v-if="hasSeed" class="p-2">
                <div class="flex items-center gap-1">
                  <NInputNumber v-model:value="row.seed" :step="1" size="small" style="width: 70px" :disabled="row.random_seed || ['PENDING','RUNNING'].includes(row.status)" />
                  <NCheckbox v-model:checked="row.random_seed" size="small" :disabled="['PENDING','RUNNING'].includes(row.status)" />
                </div>
              </td>
              <td class="p-2">
                <NSelect v-model:value="row.workflow_version_id" :options="workflowOptions" size="small" placeholder="默认" :disabled="['PENDING','RUNNING'].includes(row.status)" />
              </td>
              <td class="p-2 text-center">
                <span :style="{ color: statusColor(row.status), fontSize: '11px', fontWeight: 'bold' }">{{ row.status }}</span>
                <div v-if="row.error" style="font-size: 10px; color: #ef4444; max-width: 70px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap" :title="row.error">{{ row.error }}</div>
              </td>
              <td class="p-2 text-center">
                <div v-if="row.outputs.length" class="grid grid-cols-2 gap-1">
                  <template v-for="output in row.outputs" :key="output.id">
                    <img
                      v-if="output.media_type === 'image' || output.mime.startsWith('image/')"
                      :src="output.url"
                      class="w-20 h-20 object-contain bg-gray-100 rounded cursor-pointer"
                      :title="output.filename"
                      @click="openOutput(output)"
                    />
                    <button
                      v-else-if="output.media_type === 'video'"
                      class="relative w-20 h-20 bg-gray-100 rounded overflow-hidden cursor-pointer"
                      :title="output.filename"
                      @click="openOutput(output)"
                    >
                      <img :src="output.url" :alt="output.filename" class="w-full h-full object-contain" />
                      <span class="absolute inset-0 flex items-center justify-center text-white text-xl bg-black/20">▶</span>
                    </button>
                    <audio v-else-if="output.media_type === 'audio'" :src="output.url" controls class="w-40" />
                  </template>
                </div>
                <NSpin v-else-if="row.outputsLoading" size="small" />
                <span v-else style="font-size: 11px; color: #ccc">—</span>
              </td>
              <td class="p-2 text-center">
                <div class="flex justify-center gap-1">
                  <NButton size="tiny" type="primary" :disabled="['PENDING','RUNNING'].includes(row.status)" @click="generateSingle(i)">生成</NButton>
                  <NButton size="tiny" quaternary :disabled="['PENDING','RUNNING'].includes(row.status)" @click="duplicateRow(i)">复制</NButton>
                  <NButton size="tiny" type="error" quaternary :disabled="['PENDING','RUNNING'].includes(row.status)" @click="delRow(i)">删</NButton>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 移动端卡片 -->
      <div class="md:hidden space-y-3">
        <div v-for="(row, i) in rows" :key="i" class="border rounded p-3 space-y-2">
          <div class="flex justify-between items-center">
            <NText strong>第 {{ i + 1 }} 行</NText>
            <span :style="{ color: statusColor(row.status), fontSize: '11px' }">{{ row.status }}</span>
          </div>
          <NInput v-if="!isMotionTransfer" v-model:value="row.prompt" type="textarea" :rows="2" placeholder="提示词" size="small" :disabled="['PENDING','RUNNING'].includes(row.status)" />
          <div v-for="p in extraParams" :key="p.key" class="border rounded p-2 space-y-1">
            <NText depth="3" style="font-size: 11px">{{ p.label || p.key }}（{{ resourceSlotLabel(p) }}）</NText>
            <input
              type="file"
              :accept="p.type === 'image' ? 'image/*' : p.type === 'video' ? 'video/*' : 'audio/*'"
              @change="(e: any) => e.target.files?.[0] && uploadResource(row, p.key, e.target.files[0], p.type)"
              class="block text-xs w-full"
              :disabled="['PENDING','RUNNING'].includes(row.status)"
            />
            <NButton size="tiny" :disabled="['PENDING','RUNNING'].includes(row.status)" @click="openResourcePicker(row, p)">从素材库选择</NButton>
            <NText v-if="row.extra[p.key]" type="success" style="font-size: 11px">✓ {{ selectedResourceLabel(row.extra[p.key]) }}</NText>
            <img v-if="row.inputPreviews[p.key]?.media_type === 'image'" :src="row.inputPreviews[p.key].url" class="w-full max-h-40 object-contain bg-gray-100 rounded" @click="openOutput(row.inputPreviews[p.key])" />
            <button v-else-if="row.inputPreviews[p.key]?.media_type === 'video'" class="relative w-full h-36 bg-gray-100 rounded overflow-hidden" @click="openOutput(row.inputPreviews[p.key])">
              <img :src="row.inputPreviews[p.key].url" class="w-full h-full object-contain" />
              <span class="absolute inset-0 flex items-center justify-center text-white text-3xl bg-black/20">▶</span>
            </button>
            <audio v-else-if="row.inputPreviews[p.key]?.media_type === 'audio'" :src="row.inputPreviews[p.key].url" controls class="w-full" />
          </div>
          <div v-if="isMotionTransfer">
            <NText depth="3" style="font-size: 11px">参数方案</NText>
            <NSelect v-model:value="row.parameter_scheme_id" :options="parameterSchemeOptions" size="small" placeholder="选择参数方案" :disabled="['PENDING','RUNNING'].includes(row.status)" />
          </div>
          <div v-if="scalarParams.length" class="grid grid-cols-2 gap-2 border rounded p-2">
            <div v-for="p in scalarParams" :key="p.key">
              <NText depth="3" style="font-size: 11px">{{ p.label || p.key }}</NText>
              <NSelect v-if="p.type === 'select'" v-model:value="row.extra[p.key]" :options="p.options || []" size="small" :disabled="['PENDING','RUNNING'].includes(row.status)" />
              <NCheckbox v-else-if="p.type === 'bool'" v-model:checked="row.extra[p.key]" size="small" :disabled="['PENDING','RUNNING'].includes(row.status)">开启</NCheckbox>
              <NInputNumber v-else v-model:value="row.extra[p.key]" :min="p.min" :max="p.max" :step="p.step || (p.type === 'int' ? 1 : 0.05)" size="small" style="width: 100%" :disabled="['PENDING','RUNNING'].includes(row.status)" />
            </div>
          </div>
          <div v-if="hasSizeOptions">
            <NText depth="3" style="font-size: 11px">{{ sizeLabel }}</NText>
            <NSelect v-model:value="row.size" :options="sizeOptions" size="small" :disabled="['PENDING','RUNNING'].includes(row.status)" @update:value="(value: string) => applyRowSize(row, value)" />
          </div>
          <div v-if="hasDuration">
            <NText depth="3" style="font-size: 11px">视频时长（秒）</NText>
            <NInputNumber v-model:value="row.duration" :min="1" :max="600" :step="1" size="small" style="width: 100%" :disabled="['PENDING','RUNNING'].includes(row.status)" />
          </div>
          <div v-if="hasSeed" class="flex items-center gap-2">
            <NInputNumber v-model:value="row.seed" size="small" :disabled="row.random_seed || ['PENDING','RUNNING'].includes(row.status)" style="width: 100px" />
            <NCheckbox v-model:checked="row.random_seed" size="small" :disabled="['PENDING','RUNNING'].includes(row.status)">随机</NCheckbox>
          </div>
          <div v-if="row.outputs.length" class="grid grid-cols-2 gap-2">
            <template v-for="output in row.outputs" :key="output.id">
              <img v-if="output.media_type === 'image' || output.mime.startsWith('image/')" :src="output.url" class="w-full max-h-48 object-contain rounded" @click="openOutput(output)" />
              <button v-else-if="output.media_type === 'video'" class="relative w-full h-40 bg-gray-100 rounded overflow-hidden" @click="openOutput(output)">
                <img :src="output.url" :alt="output.filename" class="w-full h-full object-contain" />
                <span class="absolute inset-0 flex items-center justify-center text-white text-3xl bg-black/20">▶</span>
              </button>
              <audio v-else-if="output.media_type === 'audio'" :src="output.url" controls class="w-full col-span-2" />
            </template>
          </div>
          <NSpin v-else-if="row.outputsLoading" size="small" />
          <div class="flex gap-1">
            <NButton size="tiny" type="primary" :disabled="['PENDING','RUNNING'].includes(row.status)" @click="generateSingle(i)">生成</NButton>
            <NButton size="tiny" type="error" quaternary :disabled="['PENDING','RUNNING'].includes(row.status)" @click="delRow(i)">删</NButton>
          </div>
        </div>
      </div>

      <div v-if="!rows.length" class="text-gray-400 text-center py-4">暂无任务行，点击「添加行」开始</div>
    </NCard>

    <!-- 素材库选择弹窗 -->
    <NModal :show="!!pickerTarget" @update:show="closeResourcePicker" preset="card" :title="`选择${resourceSlotLabel(pickerTarget?.param || {})}`" style="width: 94%; max-width: 1080px">
      <div class="grid grid-cols-1 md:grid-cols-[230px_minmax(0,1fr)] gap-3">
        <aside class="border rounded p-2 max-h-[68vh] overflow-auto">
          <div class="flex items-center justify-between px-2 py-1">
            <span class="text-xs text-gray-400">素材目录</span>
            <span class="flex gap-2"><button class="text-xs text-blue-500" @click="expandAllPickerFolders">展开</button><button class="text-xs text-gray-500" @click="collapseAllPickerFolders">折叠</button></span>
          </div>
          <div
            v-for="folder in pickerVisibleFolders" :key="folder.id"
            class="flex items-center w-full rounded text-sm hover:bg-gray-100"
            :class="{ 'bg-green-50 text-green-700 font-medium': pickerFolderId === folder.id }"
            :style="{ paddingLeft: `${8 + folder.depth * 18}px` }"
          >
            <button class="w-5 h-8 shrink-0 text-xs text-gray-500" @click.stop="togglePickerFolder(folder)">{{ folder.children?.length ? (pickerExpandedIds.has(folder.id) ? '▼' : '▶') : '' }}</button>
            <button class="flex-1 text-left py-2 pr-2 truncate" @click="selectPickerFolder(folder.id)">📁 {{ folder.name }} <span class="text-xs text-gray-400">({{ folder.resource_count }})</span></button>
          </div>
        </aside>
        <NSpin :show="pickerLoading">
          <div class="text-xs text-gray-500 mb-2">当前目录：{{ pickerCurrentFolder?.name || '—' }}</div>
          <div v-if="!pickerItems.length && !pickerLoading" class="text-gray-400 text-center py-8">当前目录中暂无可选素材</div>
          <div v-else class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 max-h-[62vh] overflow-auto">
          <button
            v-for="resource in pickerItems"
            :key="resource.id"
            class="border rounded overflow-hidden text-left hover:border-blue-500"
            @click="selectLibraryResource(resource)"
          >
            <div v-if="['image', 'video'].includes(resource.media_type) && pickerBlobs[resource.id]" class="relative w-full h-28 bg-gray-100">
              <img :src="pickerBlobs[resource.id]" class="w-full h-full object-contain" />
              <span v-if="resource.media_type === 'video'" class="absolute inset-0 flex items-center justify-center text-white text-2xl bg-black/20">▶</span>
            </div>
            <div v-else class="w-full h-28 bg-gray-100 flex items-center justify-center text-gray-500">
              {{ resource.media_type === 'video' ? '视频' : resource.media_type === 'audio' ? '音频' : '图片' }}
            </div>
            <div class="p-2 text-xs truncate">{{ resource.filename }}</div>
          </button>
          </div>
        </NSpin>
      </div>
    </NModal>

    <NModal
      :show="!!outputPreview"
      @update:show="closeOutputPreview"
      preset="card"
      :title="outputPreview?.filename || '媒体预览'"
      style="width: 94%; max-width: 1200px"
    >
      <NSpin :show="outputPreviewLoading">
        <div class="flex items-center justify-center bg-gray-100 rounded min-h-48">
          <img
            v-if="outputPreviewUrl && outputPreview?.media_type === 'image'"
            :src="outputPreviewUrl"
            :alt="outputPreview.filename"
            class="max-w-full max-h-[78vh] object-contain"
          />
          <video
            v-else-if="outputPreviewUrl && outputPreview?.media_type === 'video'"
            :src="outputPreviewUrl"
            controls
            autoplay
            class="max-w-full max-h-[78vh]"
          />
          <audio
            v-else-if="outputPreviewUrl && outputPreview?.media_type === 'audio'"
            :src="outputPreviewUrl"
            controls
            autoplay
            class="w-full max-w-3xl"
          />
        </div>
      </NSpin>
    </NModal>

    <!-- 导入弹窗 -->
    <NModal :show="showImport" @update:show="showImport = false" preset="card" title="导入任务" style="max-width: 480px">
      <NSpace vertical :size="12">
        <input type="file" accept=".csv,.txt,.xlsx" @change="onImportFileChange" class="block" />
        <div class="grid grid-cols-2 gap-3">
          <div>
            <NText depth="3" style="font-size: 12px">起始行号</NText>
            <NInputNumber v-model:value="importStartRow" :min="1" style="width: 100%" />
          </div>
          <div>
            <NText depth="3" style="font-size: 12px">起始列号</NText>
            <NInputNumber v-model:value="importStartCol" :min="1" style="width: 100%" />
          </div>
        </div>
        <NRadioGroup v-model:value="importMode">
          <NRadioButton value="clear">清空后添加</NRadioButton>
          <NRadioButton value="append">添加到现有队列</NRadioButton>
        </NRadioGroup>
        <NButton type="primary" block :disabled="!importFile" @click="doImport">导入</NButton>
      </NSpace>
    </NModal>

    <!-- SAVE 弹窗 -->
    <NModal :show="showSave" @update:show="showSave = false" preset="card" title="保存任务" style="max-width: 360px">
      <NSpace vertical :size="12">
        <NInput v-model:value="saveName" placeholder="任务名称" />
        <NButton type="primary" block @click="doSave">保存</NButton>
      </NSpace>
    </NModal>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref, watch, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useMessage } from 'naive-ui'
import { genTypeApi, batchApi, promptApi, resourceApi, resourceFolderApi, workflowApi, taskApi } from '@/api/modules'
import { onWsEvent, connectWs } from '@/ws/client'
import { getAccessToken } from '@/api/client'

const router = useRouter()
const route = useRoute()
const message = useMessage()

const typeId = ref<number | null>(null)
const typeInfo = ref<any>(null)
const paramSchema = ref<any[]>([])
const prompts = ref<any[]>([])
const workflows = ref<any[]>([])
const defaultWorkflowVersionId = ref<number | null>(null)
const workflowOptions = ref<Array<{ label: string; value: number }>>([])

const global1 = ref('')
const global2 = ref('')
const defaultWidth = ref<number>(720)
const defaultHeight = ref<number>(1280)
const defaultSize = ref('720x1280')
const defaultSeed = ref<number>(0)
const defaultDuration = ref<number>(5)
const defaultFps = ref<number>(24)
const useRandomSeed = ref(true)
const globalWorkflowVersionId = ref<number | null>(null)
const parameterSchemes = ref<any[]>([])

const sizeOptions = computed<any[]>(() => (
  paramSchema.value.some((p) => p.key === 'width') && paramSchema.value.some((p) => p.key === 'height')
    ? (typeInfo.value?.size_options || [])
    : []
).map((option: any) => ({
  label: option.label,
  value: String(option.value).replace('×', 'x'),
})))
const hasSizeOptions = computed(() => sizeOptions.value.length > 0)
const isVideo = computed(() => typeInfo.value?.media_type === 'video')
const isMotionTransfer = computed(() => typeInfo.value?.code === 'motion_transfer')
const parameterSchemeOptions = computed(() => parameterSchemes.value.map((item) => ({
  label: `${item.name}${item.is_default ? '（默认）' : ''}`,
  value: item.id,
})))
const hasDuration = computed(() => paramSchema.value.some((p) => p.key === 'duration'))
const hasSeed = computed(() => paramSchema.value.some((p) => p.key === 'seed'))
const sizeLabel = computed(() => typeInfo.value?.media_type === 'video' ? '视频尺寸' : '图片尺寸')

interface Row {
  prompt: string
  size: string
  width: number
  height: number
  duration: number
  seed: number
  random_seed: boolean
  workflow_version_id: number | null
  parameter_scheme_id: number | null
  extra: Record<string, any>
  status: string
  task_id: number | null
  batch_id: number | null
  outputs: OutputPreview[]
  inputPreviews: Record<string, OutputPreview>
  outputsLoading: boolean
  error: string | null
}

interface OutputPreview {
  id: number
  filename: string
  media_type: 'image' | 'video' | 'audio'
  mime: string
  url: string
}
const rows = ref<Row[]>([])
const outputPreview = ref<OutputPreview | null>(null)
const outputPreviewUrl = ref('')
const outputPreviewLoading = ref(false)

const extraParams = computed(() => paramSchema.value.filter((p) =>
  !['prompt', 'negative_prompt', 'width', 'height', 'seed'].includes(p.key) &&
  ['image', 'video', 'audio'].includes(p.type)
))
const scalarParams = computed(() => paramSchema.value.filter((p) =>
  !['prompt', 'negative_prompt', 'width', 'height', 'duration', 'seed'].includes(p.key) &&
  ['int', 'float', 'bool', 'select'].includes(p.type) &&
  (!isMotionTransfer.value || ['skip_seconds', 'multi_reference_enabled', 'multi_reference_count'].includes(p.key))
))

function defaultExtraParams() {
  return Object.fromEntries(
    [...extraParams.value, ...scalarParams.value]
      .filter((p) => p.default !== undefined)
      .map((p) => [p.key, p.default]),
  )
}

async function loadType(code: string) {
  for (const row of rows.value) {
    clearRowOutputs(row)
    clearRowInputPreviews(row)
  }
  typeId.value = null
  typeInfo.value = null
  paramSchema.value = []
  rows.value = []
  global1.value = ''
  global2.value = ''
  try {
    const menu = await genTypeApi.menu()
    const flat = [...(menu.image || []), ...(menu.video || []), ...(menu.audio || [])]
    const t = flat.find((x: any) => x.code === code)
    if (!t) { message.error(`未找到生成类型：${code}`); return }
    typeId.value = t.id
    typeInfo.value = t
    paramSchema.value = t.param_schema || []
    parameterSchemes.value = code === 'motion_transfer' ? await genTypeApi.motionTransferSchemes() : []
    const wDef = paramSchema.value.find((p) => p.key === 'width')
    const hDef = paramSchema.value.find((p) => p.key === 'height')
    const durationDef = paramSchema.value.find((p) => p.key === 'duration')
    const lengthDef = paramSchema.value.find((p) => p.key === 'length')
    const fpsDef = paramSchema.value.find((p) => p.key === 'fps')
    defaultWidth.value = wDef?.default ?? 720
    defaultHeight.value = hDef?.default ?? 1280
    defaultFps.value = Number(fpsDef?.default ?? 24)
    defaultDuration.value = Number(durationDef?.default ?? Math.max(1, Math.round(((lengthDef?.default ?? 121) - 1) / defaultFps.value)))
    defaultSize.value = typeInfo.value?.size_default
      ? String(typeInfo.value.size_default).replace('×', 'x')
      : chooseDefaultSize(defaultWidth.value, defaultHeight.value)
    setDefaultDimensions(defaultSize.value)
    workflows.value = await workflowApi.list({ generation_type_code: code })
    workflowOptions.value = workflows.value
      .filter((w: any) => w.current_version_id)
      .map((w: any) => ({ label: w.name, value: w.current_version_id }))
    globalWorkflowVersionId.value = t.default_workflow_id
      ? (workflows.value.find((w: any) => w.id === t.default_workflow_id)?.current_version_id ?? null)
      : (workflowOptions.value[0]?.value ?? null)
    defaultWorkflowVersionId.value = globalWorkflowVersionId.value
    if (!prompts.value.length) prompts.value = await promptApi.list({ limit: 100 })
    rows.value = []
    addRow()
    if (route.query.batch) await loadBatch(Number(route.query.batch))
    if (getAccessToken()) connectWs()
  } catch (e: any) { message.error('加载失败：' + (e.response?.data?.message || e.message)) }
}

onMounted(() => loadType(route.params.code as string))
watch(() => route.params.code, (n) => { if (n && route.name === 'generate') loadType(n as string) })

onWsEvent(async (e: any) => {
  if (!e.task_id) return
  const row = rows.value.find((r) => r.task_id === e.task_id)
  if (!row) return
  if (e.type === 'task.status') row.status = e.payload?.status || row.status
  else if (e.type === 'task.completed') { row.status = 'SUCCESS'; await loadRowPreview(row) }
  else if (e.type === 'task.failed') { row.status = 'FAILED'; row.error = e.payload?.error || '执行失败' }
})

function addRow() {
  rows.value.unshift({
    prompt: '', size: defaultSize.value, width: defaultWidth.value, height: defaultHeight.value,
    duration: defaultDuration.value,
    seed: defaultSeed.value, random_seed: useRandomSeed.value,
    workflow_version_id: defaultWorkflowVersionId.value,
    parameter_scheme_id: parameterSchemes.value.find((item) => item.is_default)?.id ?? parameterSchemes.value[0]?.id ?? null,
    extra: defaultExtraParams(),
    status: 'DRAFT', task_id: null, batch_id: null, outputs: [], inputPreviews: {}, outputsLoading: false, error: null,
  })
}
function delRow(i: number) {
  clearRowOutputs(rows.value[i])
  clearRowInputPreviews(rows.value[i])
  rows.value.splice(i, 1)
}
function duplicateRow(i: number) {
  const c = { ...rows.value[i], extra: { ...rows.value[i].extra }, inputPreviews: {} }
  c.status = 'DRAFT'; c.task_id = null; c.batch_id = null; c.outputs = []; c.outputsLoading = false; c.error = null
  rows.value.splice(i + 1, 0, c)
  void restoreRowInputPreviews(c)
}
function applyGlobalSeedToAll() {
  for (const r of rows.value) {
    r.seed = useRandomSeed.value ? Math.floor(Math.random() * 4294967295) : defaultSeed.value
    r.random_seed = useRandomSeed.value
  }
}
function applyDefaultDuration(value: number | null) {
  defaultDuration.value = Number(value || 1)
  for (const row of rows.value) row.duration = defaultDuration.value
}
function parseSize(value: string): [number, number] | null {
  const match = String(value).match(/^(\d+)[x×](\d+)$/)
  if (!match) return null
  return [Number(match[1]), Number(match[2])]
}

function chooseDefaultSize(width: number, height: number) {
  const exact = `${width}x${height}`
  if (sizeOptions.value.some((option: any) => option.value === exact)) return exact
  const targetOrientation = width === height ? 'square' : width > height ? 'landscape' : 'portrait'
  const sameOrientation = sizeOptions.value.find((option: any) => {
    const dimensions = parseSize(option.value)
    if (!dimensions) return false
    const [w, h] = dimensions
    return targetOrientation === 'square' ? w === h : targetOrientation === 'landscape' ? w > h : w < h
  })
  return sameOrientation?.value || sizeOptions.value[0]?.value || exact
}

function setDefaultDimensions(value: string) {
  const dimensions = parseSize(value)
  if (!dimensions) return
  ;[defaultWidth.value, defaultHeight.value] = dimensions
}

function applyDefaultSize(value: string) {
  setDefaultDimensions(value)
  for (const row of rows.value) {
    row.size = value
    row.width = defaultWidth.value
    row.height = defaultHeight.value
  }
}

function applyRowSize(row: Row, value: string) {
  const dimensions = parseSize(value)
  if (!dimensions) return
  row.size = value
  ;[row.width, row.height] = dimensions
}
function applyGlobalWorkflowToAll() { for (const r of rows.value) r.workflow_version_id = globalWorkflowVersionId.value }
function applyPrompt(row: Row, p: any) { row.prompt = p.content }
async function uploadResource(row: Row, key: string, file: File, mt: string) {
  try {
    const r = await resourceApi.upload(file, mt, 'input')
    row.extra[key] = r.id
    resourceNames.value[r.id] = r.filename
    await loadInputPreview(row, key, r.id, mt, r.filename)
    message.success(`${resourceSlotLabel({ type: mt })}已上传`)
  }
  catch { message.error('上传失败') }
}

const pickerTarget = ref<{ row: Row; param: any } | null>(null)
const pickerItems = ref<any[]>([])
const pickerLoading = ref(false)
const pickerFolders = ref<any[]>([])
const pickerExpandedIds = ref<Set<number>>(new Set())
const pickerFolderId = ref<number | null>(null)
const pickerBlobs = ref<Record<number, string>>({})
const resourceNames = ref<Record<number, string>>({})
const pickerFlatFolders = computed(() => {
  const result: any[] = []
  const visit = (nodes: any[], depth = 0) => nodes.forEach((node) => {
    result.push({ ...node, depth })
    visit(node.children || [], depth + 1)
  })
  visit(pickerFolders.value)
  return result
})
const pickerCurrentFolder = computed(() => pickerFlatFolders.value.find((folder) => folder.id === pickerFolderId.value))
const pickerVisibleFolders = computed(() => {
  const result: any[] = []
  const visit = (nodes: any[], depth = 0) => nodes.forEach((node) => {
    result.push({ ...node, depth })
    if (pickerExpandedIds.value.has(node.id)) visit(node.children || [], depth + 1)
  })
  visit(pickerFolders.value)
  return result
})

function togglePickerFolder(folder: any) {
  if (!folder.children?.length) return
  const next = new Set(pickerExpandedIds.value)
  if (next.has(folder.id)) next.delete(folder.id)
  else next.add(folder.id)
  pickerExpandedIds.value = next
}
function expandAllPickerFolders() {
  pickerExpandedIds.value = new Set(pickerFlatFolders.value.filter((folder) => folder.children?.length).map((folder) => folder.id))
}
function collapseAllPickerFolders() { pickerExpandedIds.value = new Set() }
function expandPickerAncestors(folderId: number | null) {
  let current = pickerFlatFolders.value.find((folder) => folder.id === folderId)
  const next = new Set(pickerExpandedIds.value)
  while (current?.parent_id) {
    next.add(current.parent_id)
    current = pickerFlatFolders.value.find((folder) => folder.id === current.parent_id)
  }
  pickerExpandedIds.value = next
}

function revokePickerBlobs() {
  for (const url of Object.values(pickerBlobs.value)) URL.revokeObjectURL(url)
  pickerBlobs.value = {}
}

async function fetchResourceBlob(url: string) {
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${getAccessToken() || ''}` },
  })
  if (!response.ok) throw new Error('素材加载失败')
  return URL.createObjectURL(await response.blob())
}

async function loadPickerThumbnails(resources: any[]) {
  let cursor = 0
  async function worker() {
    while (cursor < resources.length) {
      const resource = resources[cursor++]
      try {
        pickerBlobs.value[resource.id] = await fetchResourceBlob(resourceApi.thumbUrl(resource.id))
      } catch { /* 单个缩略图失败不影响选择 */ }
    }
  }
  await Promise.all(Array.from({ length: Math.min(6, resources.length) }, () => worker()))
}

async function loadPickerFolderResources() {
  if (!pickerTarget.value || !pickerFolderId.value) return
  pickerLoading.value = true
  pickerItems.value = []
  revokePickerBlobs()
  try {
    const resources = await resourceApi.list({
      media_type: pickerTarget.value.param.type,
      folder_id: pickerFolderId.value,
      limit: 100,
    })
    pickerItems.value = resources
    for (const resource of resources) resourceNames.value[resource.id] = resource.filename
    if (['image', 'video'].includes(pickerTarget.value.param.type)) void loadPickerThumbnails(resources)
  } catch {
    message.error('加载目录素材失败')
  } finally {
    pickerLoading.value = false
  }
}

function selectPickerFolder(folderId: number) {
  if (pickerFolderId.value === folderId) return
  pickerFolderId.value = folderId
  void loadPickerFolderResources()
}

async function openResourcePicker(row: Row, param: any) {
  pickerTarget.value = { row, param }
  pickerItems.value = []
  revokePickerBlobs()
  pickerLoading.value = true
  try {
    pickerFolders.value = await resourceFolderApi.tree()
    const now = new Date()
    const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
    const todayKey = `task_results:${today}`
    const matchingTaskFolders = pickerFlatFolders.value.filter((folder) =>
      folder.folder_type === 'task' && String(folder.system_key || '').startsWith(`${todayKey}:`) && (folder.media_types || []).includes(param.type),
    )
    pickerFolderId.value = matchingTaskFolders.at(-1)?.id
      ?? pickerFlatFolders.value.find((folder) => folder.system_key === todayKey)?.id
      ?? pickerFlatFolders.value.find((folder) => folder.system_key === 'task_results')?.id
      ?? pickerFlatFolders.value[0]?.id
      ?? null
    expandPickerAncestors(pickerFolderId.value)
    await loadPickerFolderResources()
  } catch {
    message.error('加载素材库失败')
  } finally {
    pickerLoading.value = false
  }
}

function selectLibraryResource(resource: any) {
  if (!pickerTarget.value) return
  pickerTarget.value.row.extra[pickerTarget.value.param.key] = resource.id
  resourceNames.value[resource.id] = resource.filename
  void loadInputPreview(pickerTarget.value.row, pickerTarget.value.param.key, resource.id, resource.media_type, resource.filename)
  closeResourcePicker()
}

function closeResourcePicker() {
  pickerTarget.value = null
  pickerItems.value = []
  pickerFolders.value = []
  pickerExpandedIds.value = new Set()
  pickerFolderId.value = null
  revokePickerBlobs()
}

function selectedResourceLabel(id: number) {
  return resourceNames.value[id] || `素材 #${id}`
}

async function loadInputPreview(row: Row, key: string, resourceId: number, mediaType: string, filename = '') {
  const current = row.inputPreviews[key]
  if (current) URL.revokeObjectURL(current.url)
  delete row.inputPreviews[key]
  try {
    const url = mediaType === 'audio'
      ? await fetchResourceBlob(resourceApi.fileUrl(resourceId))
      : await fetchResourceBlob(resourceApi.thumbUrl(resourceId)).catch(() => fetchResourceBlob(resourceApi.fileUrl(resourceId)))
    row.inputPreviews[key] = {
      id: resourceId,
      filename: filename || selectedResourceLabel(resourceId),
      media_type: mediaType as OutputPreview['media_type'],
      mime: '',
      url,
    }
  } catch {
    message.warning(`${resourceSlotLabel({ type: mediaType })}预览加载失败`)
  }
}

function clearRowInputPreviews(row: Row) {
  for (const preview of Object.values(row.inputPreviews || {})) URL.revokeObjectURL(preview.url)
  row.inputPreviews = {}
}

async function restoreRowInputPreviews(row: Row) {
  await Promise.all(extraParams.value.map(async (param) => {
    const resourceId = Number(row.extra[param.key])
    if (resourceId > 0) await loadInputPreview(row, param.key, resourceId, param.type)
  }))
}

onUnmounted(closeResourcePicker)

const showImport = ref(false)
const importFile = ref<File | null>(null)
const importStartRow = ref(1)
const importStartCol = ref(1)
const importMode = ref<'append' | 'clear'>('clear')
function onImportFileChange(event: Event) {
  importFile.value = (event.target as HTMLInputElement).files?.[0] || null
}
async function doImport() {
  if (!importFile.value || !typeId.value) return
  try {
    const batch = await batchApi.create({ name: `${typeInfo.value?.name || '导入'}-${new Date().toLocaleString()}`, generation_type_id: typeId.value, rows: [] })
    const res = await batchApi.importCsv(batch.id, importFile.value, { start_row: importStartRow.value, start_col: importStartCol.value, append: importMode.value === 'append' })
    message.success(`导入 ${res.inserted} 行`); importFile.value = null; showImport.value = false; await loadBatch(batch.id)
  } catch (e: any) { message.error('导入失败：' + (e.response?.data?.message || e.message)) }
}

const showSave = ref(false)
const saveName = ref('')
async function doSave() {
  if (!saveName.value.trim()) { message.warning('请输入任务名称'); return }
  if (!rows.value.length || !typeId.value) return
  try {
    await batchApi.create({ name: saveName.value, generation_type_id: typeId.value, rows: buildRows() })
    message.success(`任务「${saveName.value}」已保存`); saveName.value = ''; showSave.value = false
  } catch (e: any) { message.error('保存失败：' + (e.response?.data?.message || e.message)) }
}

function buildRows() {
  return rows.value.map((r, i) => {
    const params = buildRowParams(r)
    return { row_no: i, generation_type_id: typeId.value, params, workflow_version_id: r.workflow_version_id }
  })
}

function videoLengthFor(duration: number, fps: number) {
  const baseFrames = Math.max(1, Math.round(duration * fps))
  return baseFrames + ((1 - baseFrames) % 4)
}

function buildRowParams(row: Row) {
  const schemeParams = isMotionTransfer.value
    ? (parameterSchemes.value.find((item) => item.id === row.parameter_scheme_id)?.params || {})
    : {}
  const params: any = { ...schemeParams, ...row.extra }
  if (!isMotionTransfer.value && paramSchema.value.some((p) => p.key === 'prompt')) {
    params.prompt = (global1.value ? global1.value + '\n' : '') + (row.prompt || '') + (global2.value ? '\n' + global2.value : '')
  }
  if (paramSchema.value.some((p) => p.key === 'width')) params.width = row.width
  if (paramSchema.value.some((p) => p.key === 'height')) params.height = row.height
  if (hasSeed.value) params.seed = row.random_seed ? Math.floor(Math.random() * 4294967295) : row.seed
  if (hasDuration.value) {
    params.duration = row.duration
  }
  if (paramSchema.value.some((p) => p.key === 'fps')) {
    params.fps = defaultFps.value
    if (paramSchema.value.some((p) => p.key === 'length')) params.length = videoLengthFor(row.duration, defaultFps.value)
  }
  return params
}

async function submit() {
  if (!rows.value.length || !typeId.value) { message.warning('未就绪'); return }
  try {
    for (const row of rows.value) clearRowOutputs(row)
    const batch = await batchApi.create({ name: `${typeInfo.value?.name || '生成'}-${new Date().toLocaleString()}`, generation_type_id: typeId.value, rows: buildRows() })
    const res = await batchApi.submit(batch.id)
    const batchRows = await batchApi.rows(batch.id)
    for (let i = 0; i < rows.value.length && i < batchRows.length; i++) {
      rows.value[i].batch_id = batch.id; rows.value[i].task_id = batchRows[i].id; rows.value[i].status = batchRows[i].status
    }
    message.success(`已提交：成功 ${res.enqueued} 行，无效 ${res.invalid} 行`); pollRows()
  } catch (e: any) { message.error('提交失败：' + (e.response?.data?.message || e.message)) }
}

async function generateSingle(i: number) {
  const row = rows.value[i]; if (!typeId.value) return
  try {
    clearRowOutputs(row)
    row.status = 'PENDING'; row.error = null
    const batch = await batchApi.create({
      name: `${typeInfo.value?.name || '生成'}-单行${i + 1}`, generation_type_id: typeId.value,
      rows: [{ row_no: 0, generation_type_id: typeId.value, params: buildRowParams(row), workflow_version_id: row.workflow_version_id }],
    })
    await batchApi.submit(batch.id)
    const batchRows = await batchApi.rows(batch.id)
    row.batch_id = batch.id; row.task_id = batchRows[0]?.id || null; row.status = batchRows[0]?.status || 'PENDING'
    message.success(`第 ${i + 1} 行已提交`); pollRows()
  } catch (e: any) { message.error('提交失败：' + (e.response?.data?.message || e.message)) }
}

let pollTimer: ReturnType<typeof setInterval> | null = null
function pollRows() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    const pending = rows.value.filter((r) => r.task_id && ['PENDING', 'DISPATCHING', 'QUEUED', 'RUNNING', 'FINALIZING'].includes(r.status))
    if (!pending.length) { if (pollTimer) { clearInterval(pollTimer); pollTimer = null }; return }
    for (const row of pending) {
      try { const t = await taskApi.get(row.task_id!); row.status = t.status; if (t.error) row.error = t.error; if (t.status === 'SUCCESS') await loadRowPreview(row) }
      catch { /* */ }
    }
  }, 2000)
}

async function loadRowPreview(row: Row) {
  if (!row.task_id || row.outputsLoading || row.outputs.length) return
  row.outputsLoading = true
  try {
    const outputs = await taskApi.outputs(row.task_id)
    const previews = await Promise.all(outputs.map(async (output: any) => {
      try {
        let url: string
        if (['image', 'video'].includes(output.media_type)) {
          try {
            url = await fetchResourceBlob(resourceApi.thumbUrl(output.id))
          } catch {
            url = await fetchResourceBlob(resourceApi.fileUrl(output.id))
          }
        } else {
          url = await fetchResourceBlob(resourceApi.fileUrl(output.id))
        }
        return {
          id: output.id,
          filename: output.filename,
          media_type: output.media_type,
          mime: output.mime || '',
          url,
        } as OutputPreview
      } catch {
        return null
      }
    }))
    row.outputs = previews.filter((output): output is OutputPreview => output !== null)
  } catch {
    clearRowOutputs(row)
  } finally {
    row.outputsLoading = false
  }
}

function clearRowOutputs(row: Row) {
  for (const output of row.outputs || []) URL.revokeObjectURL(output.url)
  row.outputs = []
}

async function openOutput(output: OutputPreview) {
  outputPreview.value = output
  outputPreviewLoading.value = true
  if (outputPreviewUrl.value) URL.revokeObjectURL(outputPreviewUrl.value)
  outputPreviewUrl.value = ''
  try {
    outputPreviewUrl.value = await fetchResourceBlob(resourceApi.fileUrl(output.id))
  } catch {
    message.error('预览图片加载失败')
  } finally {
    outputPreviewLoading.value = false
  }
}

function closeOutputPreview() {
  outputPreview.value = null
  outputPreviewLoading.value = false
  if (outputPreviewUrl.value) URL.revokeObjectURL(outputPreviewUrl.value)
  outputPreviewUrl.value = ''
}

async function loadBatch(id: number) {
  try {
    const r = await batchApi.rows(id)
    rows.value = r.map((t: any) => ({
      prompt: t.params?.prompt || '',
      size: `${t.params?.width || defaultWidth.value}x${t.params?.height || defaultHeight.value}`,
      width: t.params?.width || defaultWidth.value, height: t.params?.height || defaultHeight.value,
      duration: Number(t.params?.duration ?? (t.params?.length ? Math.max(1, Math.round((t.params.length - 1) / (t.params?.fps || defaultFps.value))) : defaultDuration.value)),
      seed: t.params?.seed || 0, random_seed: !t.params?.seed,
      workflow_version_id: t.workflow_version_id || defaultWorkflowVersionId.value,
      extra: Object.fromEntries(extraParams.value.filter((p) => t.params?.[p.key]).map((p) => [p.key, t.params[p.key]])),
      status: t.status, task_id: t.id, batch_id: id, outputs: [], inputPreviews: {}, outputsLoading: false, error: t.error,
    }))
    await Promise.all(rows.value.map((row) => restoreRowInputPreviews(row)))
    for (const row of rows.value) if (row.status === 'SUCCESS' && row.task_id) await loadRowPreview(row)
    if (rows.value.some((r) => ['PENDING', 'DISPATCHING', 'QUEUED', 'RUNNING'].includes(r.status))) pollRows()
  } catch { message.error('加载批次失败') }
}

function resourceSlotLabel(p: any): string {
  const labels: Record<string, string> = { image: '图片', video: '视频', audio: '音频' }
  return labels[p.type] || p.type
}
function statusColor(s: string): string {
  if (s === 'SUCCESS') return '#16a34a'
  if (s === 'FAILED') return '#ef4444'
  if (['PENDING', 'DISPATCHING', 'QUEUED', 'RUNNING'].includes(s)) return '#2563eb'
  return '#9ca3af'
}

onUnmounted(() => {
  closeOutputPreview()
  for (const row of rows.value) {
    clearRowOutputs(row)
    clearRowInputPreviews(row)
  }
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<script lang="ts">
import { NH2, NCard, NSpace, NInput, NInputNumber, NButton, NText, NSelect, NCheckbox, NModal, NRadioGroup, NRadioButton, NSpin } from 'naive-ui'
</script>
