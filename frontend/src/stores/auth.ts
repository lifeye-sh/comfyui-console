import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authApi } from '@/api/modules'
import { clearTokens, getAccessToken, setTokens } from '@/api/client'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<any>(null)
  const token = ref<string | null>(getAccessToken())

  async function login(username: string, password: string) {
    const data = await authApi.login(username, password)
    setTokens(data.access_token, data.refresh_token)
    token.value = data.access_token
    await fetchMe()
  }

  async function fetchMe() {
    try {
      user.value = await authApi.me()
    } catch {
      logout()
    }
  }

  function logout() {
    user.value = null
    token.value = null
    clearTokens()
  }

  return { user, token, login, fetchMe, logout }
})
