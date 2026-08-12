<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { resourceApi, resourceFolderApi } from '@/api/modules'
import { getAccessToken } from '@/api/client'

const message = useMessage()
const items = ref<any[]>([])
const loading = ref(false)
const loadingMore = ref(false)
const hasMore = ref(true)
const preview = ref<any>(null)
const previewBlob = ref('')
const generationInfo = ref<any>(null)
const infoLoading = ref(false)
const mediaType = ref<string | null>(null)
const folderTree = ref<any[]>([])
const expandedFolderIds = ref<Set<number>>(new Set())
const currentFolderId = ref<number | null>(null)
const selectedIds = ref<number[]>([])
const showFolderEditor = ref(false)
const folderName = ref('')
const editingFolder = ref<any>(null)
const showMove = ref(false)
const moveTargetId = ref<number | null>(null)
const blobs = ref<Record<number, string>>({})
const PAGE_SIZE = 30
const THUMBNAIL_CONCURRENCY = 6
const mediaOptions = [
  { label: '全部素材', value: '' },
  { label: '图片', value: 'image' },
  { label: '视频', value: 'video' },
  { label: '音频', value: 'audio' },
]
const flatFolders = computed(() => {
  const result: any[] = []
  const visit = (nodes: any[], depth = 0) => nodes.forEach((node) => {
    result.push({ ...node, depth })
    visit(node.children || [], depth + 1)
  })
  visit(folderTree.value)
  return result
})
const visibleFolders = computed(() => {
  const result: any[] = []
  const visit = (nodes: any[], depth = 0) => nodes.forEach((node) => {
    result.push({ ...node, depth })
    if (expandedFolderIds.value.has(node.id)) visit(node.children || [], depth + 1)
  })
  visit(folderTree.value)
  return result
})
const currentFolder = computed(() => flatFolders.value.find((folder) => folder.id === currentFolderId.value))
const moveFolderOptions = computed(() => flatFolders.value.map((folder) => ({
  label: `${'　'.repeat(folder.depth)}${folder.name}`,
  value: folder.id,
})))

function localDateText() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

function expandAncestors(folderId: number | null) {
  let current = flatFolders.value.find((folder) => folder.id === folderId)
  const next = new Set(expandedFolderIds.value)
  while (current?.parent_id) {
    next.add(current.parent_id)
    current = flatFolders.value.find((folder) => folder.id === current.parent_id)
  }
  expandedFolderIds.value = next
}

function toggleFolder(folder: any) {
  if (!folder.children?.length) return
  const next = new Set(expandedFolderIds.value)
  if (next.has(folder.id)) next.delete(folder.id)
  else next.add(folder.id)
  expandedFolderIds.value = next
}

function expandAllFolders() {
  expandedFolderIds.value = new Set(flatFolders.value.filter((folder) => folder.children?.length).map((folder) => folder.id))
}

function collapseAllFolders() {
  expandedFolderIds.value = new Set()
}

async function loadFolders(selectDefault = false) {
  folderTree.value = await resourceFolderApi.tree()
  if (selectDefault || !flatFolders.value.some((folder) => folder.id === currentFolderId.value)) {
    const todayKey = `task_results:${localDateText()}`
    currentFolderId.value = flatFolders.value.find((folder) => folder.system_key === todayKey)?.id
      ?? flatFolders.value.find((folder) => folder.system_key === 'task_results')?.id
      ?? flatFolders.value[0]?.id
      ?? null
    expandAncestors(currentFolderId.value)
  }
}

async function fetchBlob(url: string) {
  const r = await fetch(url, {
    headers: { Authorization: `Bearer ${getAccessToken() || ''}` },
  })
  if (!r.ok) throw new Error('fetch failed')
  return URL.createObjectURL(await r.blob())
}

async function loadThumbnails(resources: any[]) {
  let cursor = 0
  async function worker() {
    while (cursor < resources.length) {
      const current = resources[cursor++]
      try {
        const url = await fetchBlob(resourceApi.thumbUrl(current.id))
        if (blobs.value[current.id]) URL.revokeObjectURL(blobs.value[current.id])
        blobs.value[current.id] = url
      } catch {
        // 单张缩略图失败不阻塞其余素材显示
      }
    }
  }
  const workerCount = Math.min(THUMBNAIL_CONCURRENCY, resources.length)
  await Promise.all(Array.from({ length: workerCount }, () => worker()))
}

async function load(reset = true) {
  if (reset) loading.value = true
  else loadingMore.value = true
  try {
    if (reset) {
      for (const url of Object.values(blobs.value)) URL.revokeObjectURL(url)
      blobs.value = {}
      items.value = []
    }
    const page = await resourceApi.list({
      media_type: mediaType.value || undefined,
      limit: PAGE_SIZE,
      offset: items.value.length,
      folder_id: currentFolderId.value || undefined,
    })
    items.value.push(...page)
    hasMore.value = page.length === PAGE_SIZE
    void loadThumbnails(page.filter((item: any) => ['image', 'video'].includes(item.media_type)))
  } catch {
    message.error('加载素材库失败')
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}
onMounted(async () => { await loadFolders(true); await load(true) })
watch(mediaType, () => void load(true))
watch(currentFolderId, () => { selectedIds.value = []; void load(true) })
onUnmounted(() => {
  for (const url of Object.values(blobs.value)) URL.revokeObjectURL(url)
  if (previewBlob.value) URL.revokeObjectURL(previewBlob.value)
})

async function openPreview(resource: any) {
  preview.value = resource
  generationInfo.value = null
  if (previewBlob.value) URL.revokeObjectURL(previewBlob.value)
  previewBlob.value = ''
  const filePromise = fetchBlob(resourceApi.fileUrl(resource.id))
    .then((url) => { previewBlob.value = url })
    .catch(() => { message.error('素材加载失败') })
  if (resource.direction === 'output') {
    infoLoading.value = true
    void resourceApi.generationInfo(resource.id)
      .then((info) => { generationInfo.value = info })
      .catch(() => { generationInfo.value = null })
      .finally(() => { infoLoading.value = false })
  }
  await filePromise
}

function closePreview() {
  preview.value = null
  generationInfo.value = null
  infoLoading.value = false
  if (previewBlob.value) URL.revokeObjectURL(previewBlob.value)
  previewBlob.value = ''
}

function formatParamValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

async function del(id: number) {
  try {
    await resourceApi.delete(id)
    if (blobs.value[id]) URL.revokeObjectURL(blobs.value[id])
    delete blobs.value[id]
    items.value = items.value.filter((item) => item.id !== id)
    if (preview.value?.id === id) closePreview()
    message.success('已删除')
  } catch {
    message.error('删除失败')
  }
}

async function download(r: any) {
  try {
    const url = await fetchBlob(resourceApi.fileUrl(r.id))
    const a = document.createElement('a')
    a.href = url
    a.download = r.filename
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 2000)
  } catch {
    message.error('下载失败')
  }
}

function openNewFolder() {
  editingFolder.value = null; folderName.value = ''; showFolderEditor.value = true
}
function openRenameFolder() {
  if (!currentFolder.value || currentFolder.value.folder_type !== 'normal') return
  editingFolder.value = currentFolder.value; folderName.value = currentFolder.value.name; showFolderEditor.value = true
}
async function saveFolder() {
  if (!folderName.value.trim()) { message.warning('请输入文件夹名称'); return }
  try {
    if (editingFolder.value) await resourceFolderApi.patch(editingFolder.value.id, { name: folderName.value })
    else await resourceFolderApi.create({ name: folderName.value, parent_id: currentFolder.value?.folder_type === 'normal' ? currentFolderId.value : null })
    showFolderEditor.value = false; await loadFolders(); message.success('文件夹已保存')
  } catch (e: any) { message.error(e.response?.data?.message || '文件夹保存失败') }
}
async function deleteCurrentFolder() {
  if (!currentFolder.value || currentFolder.value.folder_type !== 'normal') return
  if (!confirm(`删除文件夹“${currentFolder.value.name}”？其中素材将移到“上传素材”。`)) return
  try { await resourceFolderApi.delete(currentFolder.value.id); await loadFolders(true); message.success('文件夹已删除') }
  catch (e: any) { message.error(e.response?.data?.message || '删除失败') }
}
function openMoveDialog(resourceId?: number) {
  if (resourceId) selectedIds.value = [resourceId]
  if (!selectedIds.value.length) return
  moveTargetId.value = currentFolderId.value; showMove.value = true
}
async function moveSelected() {
  if (!moveTargetId.value) { message.warning('请选择目标文件夹'); return }
  try {
    await resourceApi.batchMove(selectedIds.value, moveTargetId.value)
    showMove.value = false; selectedIds.value = []; await Promise.all([load(true), loadFolders()]); message.success('素材已移动')
  } catch (e: any) { message.error(e.response?.data?.message || '移动失败') }
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div><NH2 style="margin: 0">素材库</NH2><div class="text-xs text-gray-500 mt-1">{{ currentFolder?.name || '目录' }}</div></div>
      <div class="flex gap-2">
        <NButton size="small" @click="openNewFolder">新建文件夹</NButton>
        <NButton v-if="currentFolder?.folder_type === 'normal'" size="small" @click="openRenameFolder">重命名</NButton>
        <NButton v-if="currentFolder?.folder_type === 'normal'" size="small" type="error" quaternary @click="deleteCurrentFolder">删除目录</NButton>
        <NSelect v-model:value="mediaType" :options="mediaOptions" clearable style="width: 150px" />
      </div>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-[240px_minmax(0,1fr)] gap-4">
      <aside class="border rounded bg-white p-2 max-h-[78vh] overflow-auto">
        <div class="flex items-center justify-between px-2 py-1">
          <span class="text-xs text-gray-400">文件夹</span>
          <span class="flex gap-2"><button class="text-xs text-blue-500" @click="expandAllFolders">全部展开</button><button class="text-xs text-gray-500" @click="collapseAllFolders">全部折叠</button></span>
        </div>
        <div
          v-for="folder in visibleFolders" :key="folder.id"
          class="flex items-center w-full rounded text-sm hover:bg-gray-100"
          :class="{ 'bg-green-50 text-green-700 font-medium': currentFolderId === folder.id }"
          :style="{ paddingLeft: `${8 + folder.depth * 18}px` }"
        >
          <button class="w-5 h-8 shrink-0 text-xs text-gray-500" @click.stop="toggleFolder(folder)">{{ folder.children?.length ? (expandedFolderIds.has(folder.id) ? '▼' : '▶') : '' }}</button>
          <button class="flex-1 text-left py-2 pr-2 truncate" @click="currentFolderId = folder.id">📁 {{ folder.name }} <span class="text-xs text-gray-400">({{ folder.resource_count }})</span></button>
        </div>
      </aside>
      <main class="min-w-0">
      <div v-if="selectedIds.length" class="border rounded bg-blue-50 px-3 py-2 mb-3 flex justify-between items-center">
        <span class="text-sm">已选择 {{ selectedIds.length }} 项</span>
        <div class="flex gap-2"><NButton size="small" type="primary" @click="openMoveDialog()">移动到</NButton><NButton size="small" @click="selectedIds = []">取消选择</NButton></div>
      </div>
      <NSpin :show="loading">
      <div v-if="!items.length" class="text-gray-400">暂无资源</div>
      <div v-else class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
        <div v-for="r in items" :key="r.id" class="border rounded overflow-hidden relative" :class="{ 'ring-2 ring-blue-500': selectedIds.includes(r.id) }">
          <input v-model="selectedIds" type="checkbox" :value="r.id" class="absolute top-2 left-2 z-10 w-4 h-4" />
          <img
            v-if="r.media_type === 'image' && blobs[r.id]"
            :src="blobs[r.id]"
            :alt="r.filename"
            class="w-full h-32 object-contain bg-gray-100 cursor-pointer"
            loading="lazy"
            decoding="async"
            @click="openPreview(r)"
          />
          <button
            v-else-if="r.media_type === 'video' && blobs[r.id]"
            class="relative block w-full h-32 bg-gray-100 cursor-pointer"
            @click="openPreview(r)"
          >
            <img :src="blobs[r.id]" :alt="r.filename" class="w-full h-full object-contain" loading="lazy" decoding="async" />
            <span class="absolute inset-0 flex items-center justify-center"><i class="w-10 h-10 rounded-full bg-black/60 text-white not-italic flex items-center justify-center text-lg">▶</i></span>
          </button>
          <div v-else-if="r.media_type === 'image' || r.media_type === 'video'" class="w-full h-32 bg-gray-100 animate-pulse" />
          <button
            v-else
            class="w-full h-32 bg-gray-100 text-gray-500 text-sm cursor-pointer"
            @click="openPreview(r)"
          >
            {{ r.media_type === 'video' ? '视频素材' : '音频素材' }}
          </button>
          <div class="p-1 text-xs truncate">{{ r.filename }}</div>
          <div class="flex justify-between p-1">
            <div class="flex gap-2">
              <button class="text-blue-500 text-xs" @click="download(r)">下载</button>
              <button v-if="r.direction === 'output'" class="text-indigo-500 text-xs" @click="openPreview(r)">参数</button>
              <button class="text-green-600 text-xs" @click="openMoveDialog(r.id)">移动</button>
            </div>
            <button class="text-red-500 text-xs" @click="del(r.id)">删除</button>
          </div>
        </div>
      </div>
      <div v-if="hasMore" class="flex justify-center mt-4">
        <NButton :loading="loadingMore" @click="load(false)">加载更多</NButton>
      </div>
      </NSpin>
      </main>
    </div>

    <NModal v-model:show="showFolderEditor" preset="card" :title="editingFolder ? '重命名文件夹' : '新建文件夹'" style="max-width: 420px">
      <NSpace vertical>
        <NInput v-model:value="folderName" placeholder="文件夹名称" @keyup.enter="saveFolder" />
        <NButton type="primary" block @click="saveFolder">保存</NButton>
      </NSpace>
    </NModal>

    <NModal v-model:show="showMove" preset="card" title="移动素材" style="max-width: 480px">
      <NSpace vertical>
        <NSelect v-model:value="moveTargetId" :options="moveFolderOptions" filterable placeholder="选择目标文件夹" />
        <NButton type="primary" block @click="moveSelected">移动 {{ selectedIds.length }} 项素材</NButton>
      </NSpace>
    </NModal>

    <NModal :show="!!preview" @update:show="closePreview" preset="card" title="素材详情" style="width: 90%; max-width: 1000px">
      <NSpin :show="!!preview && !previewBlob">
        <img v-if="previewBlob && preview?.media_type === 'image'" :src="previewBlob" class="w-full max-h-[65vh] object-contain" />
        <video v-else-if="previewBlob && preview?.media_type === 'video'" :src="previewBlob" controls class="w-full max-h-[65vh]" />
        <audio v-else-if="previewBlob && preview?.media_type === 'audio'" :src="previewBlob" controls class="w-full mt-4" />
      </NSpin>
      <div v-if="preview" class="mt-4 space-y-3">
        <div class="text-sm text-gray-500">{{ preview.filename }}</div>
        <NSpin v-if="preview.direction === 'output'" :show="infoLoading">
          <div v-if="generationInfo" class="space-y-3">
            <div class="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
              <div><span class="text-gray-400">任务：</span>#{{ generationInfo.task_id }}</div>
              <div><span class="text-gray-400">生成类型：</span>{{ generationInfo.generation_type_name || '—' }}</div>
              <div><span class="text-gray-400">状态：</span>{{ generationInfo.task_status }}</div>
              <div><span class="text-gray-400">工作流版本：</span>{{ generationInfo.workflow_version_id || '—' }}</div>
            </div>
            <div class="font-medium">生成参数</div>
            <div class="border rounded divide-y max-h-72 overflow-auto">
              <div v-for="(value, key) in generationInfo.params" :key="key" class="grid grid-cols-[150px_1fr] gap-3 p-2 text-sm">
                <div class="font-medium break-all">{{ key }}</div>
                <pre class="whitespace-pre-wrap break-all font-sans">{{ formatParamValue(value) }}</pre>
              </div>
            </div>
          </div>
          <div v-else-if="!infoLoading" class="text-sm text-gray-400">未找到来源任务参数</div>
        </NSpin>
      </div>
    </NModal>
  </div>
</template>

<script lang="ts">
import { NH2, NSpin, NModal, NButton, NSelect, NSpace, NInput } from 'naive-ui'
</script>
