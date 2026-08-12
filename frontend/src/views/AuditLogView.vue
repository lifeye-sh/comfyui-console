<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useMessage, NH2, NSpin, NCard, NText, NInput, NSelect } from 'naive-ui'
import { http } from '@/api/client'

const message = useMessage()
const logs = ref<any[]>([])
const loading = ref(false)
const filterUser = ref('')
const filterAction = ref<string | null>(null)

const actionOptions = [
  { label: '全部', value: '' },
  { label: '登录', value: 'login' },
  { label: '创建任务', value: 'batch.submit' },
  { label: '取消任务', value: 'task.cancel' },
  { label: '删除资源', value: 'resource.delete' },
  { label: '修改工作流', value: 'workflow.update' },
]

async function load() {
  loading.value = true
  try {
    const params: any = { limit: 200 }
    if (filterUser.value) params.user_id = Number(filterUser.value)
    if (filterAction.value) params.action = filterAction.value
    logs.value = await http.get('/audit-logs', { params }).then((r) => r.data)
  } catch {
    message.error('加载审计日志失败')
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <NH2>操作记录</NH2>
    <div class="flex gap-2 mb-2">
      <NInput v-model:value="filterUser" placeholder="用户 ID" style="width: 120px" />
      <NSelect v-model:value="filterAction" :options="actionOptions" placeholder="操作类型" style="width: 180px" clearable />
      <NButton @click="load">查询</NButton>
    </div>
    <NSpin :show="loading">
      <div v-if="!logs.length" class="text-gray-400">暂无记录</div>
      <div v-else class="space-y-1">
        <div v-for="l in logs" :key="l.id" class="border rounded p-2 text-sm">
          <NText strong>{{ l.action }}</NText>
          <NText depth="3" style="margin-left: 8px; font-size: 12px">{{ l.created_at }}</NText>
          <div class="text-xs text-gray-500">用户 {{ l.user_id }} · {{ l.target_type }} {{ l.target_id }} · IP {{ l.ip }}</div>
          <div v-if="l.detail" class="text-xs text-gray-400">{{ l.detail }}</div>
        </div>
      </div>
    </NSpin>
  </div>
</template>

<script lang="ts">
import { NButton } from 'naive-ui'
</script>
