<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useMessage, NH2, NCard, NSpin, NText, NButton, NInput } from 'naive-ui'
import { getAccessToken } from '@/api/client'

const route = useRoute()
const message = useMessage()
const token = route.params.token as string
const info = ref<any>(null)
const loading = ref(true)
const password = ref('')
const needPassword = ref(false)
const fileUrl = ref('')

async function load() {
  loading.value = true
  try {
    const r = await fetch(`/s/${token}?password=${encodeURIComponent(password.value)}`)
    if (r.status === 403) {
      needPassword.value = true
      loading.value = false
      return
    }
    if (r.status === 404) {
      message.error('分享已过期或不存在')
      loading.value = false
      return
    }
    info.value = await r.json()
    fileUrl.value = `/s/${token}/file${password.value ? `?password=${encodeURIComponent(password.value)}` : ''}`
  } catch {
    message.error('加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function submitPassword() {
  await load()
}

async function download() {
  const r = await fetch(fileUrl.value)
  if (!r.ok) {
    message.error('下载失败')
    return
  }
  const blob = await r.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = info.value?.filename || 'download'
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-100 p-4">
    <NCard title="分享内容" style="max-width: 600px; width: 100%">
      <NSpin :show="loading">
        <template v-if="needPassword">
          <NSpace vertical :size="12">
            <NText>此分享需要密码</NText>
            <NInput v-model:value="password" type="password" placeholder="输入密码" @keyup.enter="submitPassword" />
            <NButton type="primary" block @click="submitPassword">确认</NButton>
          </NSpace>
        </template>
        <template v-else-if="info">
          <NSpace vertical :size="12">
            <NText strong>{{ info.filename }}</NText>
            <NText depth="3">类型：{{ info.media_type }} · 大小：{{ (info.size / 1024).toFixed(1) }} KB</NText>
            <template v-if="info.media_type === 'image'">
              <img :src="fileUrl" style="max-width: 100%; border-radius: 8px" />
            </template>
            <template v-else-if="info.media_type === 'video'">
              <video :src="fileUrl" controls style="max-width: 100%; border-radius: 8px" />
            </template>
            <template v-else-if="info.media_type === 'audio'">
              <audio :src="fileUrl" controls style="width: 100%" />
            </template>
            <NButton v-if="info.allow_download" type="primary" @click="download">下载</NButton>
            <NText v-else depth="3">此分享不允许下载</NText>
          </NSpace>
        </template>
      </NSpin>
    </NCard>
  </div>
</template>

<script lang="ts">
import { NSpace } from 'naive-ui'
</script>