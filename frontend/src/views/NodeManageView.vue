<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { nodeApi } from '@/api/modules'

const message = useMessage()
const nodes = ref<any[]>([])
const loading = ref(false)
const showAdd = ref(false)
const form = reactive({
  name: '本地节点',
  base_url: 'http://127.0.0.1:8188',
  ws_url: 'ws://127.0.0.1:8188/ws',
  tags: [] as string[],
  max_concurrent: 1,
})

async function load() {
  loading.value = true
  try {
    nodes.value = await nodeApi.list()
  } catch {
    message.error('加载节点失败')
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function add() {
  try {
    await nodeApi.create({ ...form })
    showAdd.value = false
    await load()
    message.success('已添加')
  } catch (e: any) {
    message.error(e.response?.data?.message || '添加失败')
  }
}

async function probe(id: number) {
  try {
    await nodeApi.probe(id)
    message.success('节点在线')
    await load()
  } catch {
    message.error('探测失败')
    await load()
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex justify-between items-center mb-4">
      <NH2 style="margin: 0">节点管理</NH2>
      <NButton type="primary" @click="showAdd = true">添加节点</NButton>
    </div>

    <NSpin :show="loading">
      <div v-if="!nodes.length" class="text-gray-400">暂无节点，请添加本地 ComfyUI 节点（默认 http://127.0.0.1:8188）</div>
      <div v-else class="space-y-2">
        <div
          v-for="n in nodes"
          :key="n.id"
          class="border rounded p-3 flex justify-between items-center"
        >
          <div>
            <NText strong>{{ n.name }}</NText>
            <NTag :type="n.status === 'online' ? 'success' : 'default'" size="small" style="margin-left: 8px"
              >{{ n.status }}</NTag>
            <div class="text-xs text-gray-500">{{ n.base_url }} · 并发 {{ n.max_concurrent }}</div>
          </div>
          <NButton size="small" @click="probe(n.id)">探测</NButton>
        </div>
      </div>
    </NSpin>

    <NModal :show="showAdd" @update:show="showAdd = false" preset="card" title="添加节点" style="max-width: 480px">
      <NSpace vertical :size="12">
        <NInput v-model:value="form.name" placeholder="节点名称" />
        <NInput v-model:value="form.base_url" placeholder="HTTP 地址" />
        <NInput v-model:value="form.ws_url" placeholder="WebSocket 地址" />
        <NInputNumber v-model:value="form.max_concurrent" :min="1" :max="8" />
        <NButton type="primary" block @click="add">保存</NButton>
      </NSpace>
    </NModal>
  </div>
</template>

<script lang="ts">
import { NH2, NSpace, NSpin, NText, NTag, NButton, NModal, NInput, NInputNumber } from 'naive-ui'
</script>
