<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { getAccessToken } from '@/api/client'
import { connectWs } from '@/ws/client'

const auth = useAuthStore()
onMounted(async () => {
  if (getAccessToken()) {
    await auth.fetchMe()
    connectWs()
  }
})
</script>

<template>
  <NConfigProvider>
    <NLoadingBarProvider>
      <NDialogProvider>
        <NMessageProvider>
          <RouterView />
        </NMessageProvider>
      </NDialogProvider>
    </NLoadingBarProvider>
  </NConfigProvider>
</template>

<script lang="ts">
import { NConfigProvider, NLoadingBarProvider, NDialogProvider, NMessageProvider } from 'naive-ui'
import { RouterView } from 'vue-router'
</script>
