<script setup lang="ts">
import { darkTheme } from 'naive-ui'
import { onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { getAccessToken } from '@/api/client'
import { connectWs } from '@/ws/client'

const palette = getComputedStyle(document.documentElement)
const tone = (name:string) => palette.getPropertyValue('--ws-'+name).trim()
const componentTheme = {
  common: { bodyColor:tone('bg'), cardColor:tone('surface'), modalColor:tone('surface'), popoverColor:tone('bg-elevated'),
    textColorBase:tone('text'), textColor1:tone('text'), textColor2:tone('text-muted'), borderColor:tone('border'),
    primaryColor:tone('primary'), primaryColorHover:tone('primary-strong'), primaryColorPressed:tone('primary-strong'),
    fontFamily:palette.getPropertyValue('--ws-font'), fontSize:'14px', heightMedium:'42px', borderRadius:'8px' },
  Card:{borderRadius:'14px'}, Button:{heightMedium:'42px',borderRadiusMedium:'8px',textColorPrimary:tone('on-primary')}
}
const auth = useAuthStore()
onMounted(async () => {
  if (getAccessToken()) {
    await auth.fetchMe()
    connectWs()
  }
})
</script>

<template>
  <NConfigProvider :theme="darkTheme" :theme-overrides="componentTheme">
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
