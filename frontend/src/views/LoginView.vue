<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { connectWs } from '@/ws/client'

const router = useRouter()
const auth = useAuthStore()

const form = reactive({ username: 'admin', password: 'admin123' })
const loading = ref(false)
const error = ref('')

async function submit() {
  loading.value = true
  error.value = ''
  try {
    await auth.login(form.username, form.password)
    connectWs()
    router.push('/')
  } catch (e: any) {
    error.value = e.response?.data?.message || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-100 p-4">
    <NCard title="comfyui-console" style="width: 100%; max-width: 360px">
      <NSpace vertical :size="16">
        <NInput v-model:value="form.username" placeholder="用户名" />
        <NInput
          v-model:value="form.password"
          type="password"
          placeholder="密码"
          show-password-on="click"
          @keyup.enter="submit"
        />
        <NButton type="primary" block :loading="loading" @click="submit">登录</NButton>
        <NText v-if="error" type="error" style="font-size: 12px">{{ error }}</NText>
        <NText depth="3" style="font-size: 12px">默认管理员：admin / admin123</NText>
      </NSpace>
    </NCard>
  </div>
</template>

<script lang="ts">
import { NCard, NSpace, NInput, NButton, NText } from 'naive-ui'
</script>
