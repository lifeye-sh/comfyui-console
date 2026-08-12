<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useMessage, NH2, NSpin, NText, NButton } from 'naive-ui'
import { http } from '@/api/client'

const message = useMessage()
const items = ref<any[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    items.value = await http.get('/resources/recycle/list').then((r) => r.data)
  } catch {
    message.error('加载回收站失败')
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function restore(id: number) {
  try {
    await http.post(`/resources/${id}/restore`)
    await load()
    message.success('已恢复')
  } catch {
    message.error('恢复失败')
  }
}

async function permanent(id: number) {
  try {
    await http.delete(`/resources/${id}/permanent`)
    await load()
    message.success('已彻底删除')
  } catch {
    message.error('删除失败')
  }
}
</script>

<template>
  <div class="space-y-4">
    <NH2>回收站</NH2>
    <NSpin :show="loading">
      <div v-if="!items.length" class="text-gray-400">回收站为空</div>
      <div v-else class="space-y-1">
        <div v-for="r in items" :key="r.id" class="border rounded p-2 flex justify-between items-center">
          <div>
            <NText strong>{{ r.filename }}</NText>
            <NText depth="3" style="font-size: 12px; margin-left: 8px">{{ r.media_type }}</NText>
          </div>
          <div class="flex gap-2">
            <NButton size="small" @click="restore(r.id)">恢复</NButton>
            <NButton size="small" type="error" @click="permanent(r.id)">彻底删除</NButton>
          </div>
        </div>
      </div>
    </NSpin>
  </div>
</template>