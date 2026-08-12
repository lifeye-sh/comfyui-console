<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useMessage, NH2, NSpin, NText, NButton, NInputNumber, NUpload } from 'naive-ui'
import { http } from '@/api/client'

const message = useMessage()
const videos = ref<any[]>([])
const loading = ref(false)
const selected = ref<any>(null)
const interval = ref(1.0)

async function load() {
  loading.value = true
  try {
    videos.value = await http.get('/resources', { params: { media_type: 'video', limit: 100 } }).then((r) => r.data)
  } catch {
    message.error('加载视频失败')
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function onUpload(file: File) {
  const fd = new FormData()
  fd.append('file', file)
  try {
    await http.post('/resources', fd, {
      params: { media_type: 'video', direction: 'input' },
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    await load()
    message.success('上传成功')
  } catch {
    message.error('上传失败')
  }
}

async function extractFrames(video: any) {
  try {
    const res = await http.post(`/resources/${video.id}/frames`, null, {
      params: { interval: interval.value },
    })
    message.success(`已抽帧 ${res.data.length} 张`)
  } catch (e: any) {
    message.error('抽帧失败：' + (e.response?.data?.detail || '需要 ffmpeg'))
  }
}
</script>

<template>
  <div class="space-y-4">
    <NH2>参考视频</NH2>
    <div class="flex gap-2 items-center">
      <NUpload accept="video/*" :show-file-list="false" @change="(f: any) => f?.file && onUpload(f.file)">
        <NButton>上传视频</NButton>
      </NUpload>
      <NText depth="3" style="font-size: 12px">上传视频后可按间隔抽帧生成参考图</NText>
    </div>
    <NSpin :show="loading">
      <div v-if="!videos.length" class="text-gray-400">暂无视频</div>
      <div v-else class="space-y-2">
        <div v-for="v in videos" :key="v.id" class="border rounded p-3 flex justify-between items-center">
          <div>
            <NText strong>{{ v.filename }}</NText>
            <NText depth="3" style="font-size: 12px; margin-left: 8px">{{ (v.size / 1024 / 1024).toFixed(1) }} MB</NText>
          </div>
          <div class="flex gap-2 items-center">
            <NText style="font-size: 12px">间隔</NText>
            <NInputNumber v-model:value="interval" :step="0.5" :min="0.1" size="small" style="width: 80px" />
            <NButton size="small" @click="extractFrames(v)">抽帧</NButton>
          </div>
        </div>
      </div>
    </NSpin>
  </div>
</template>