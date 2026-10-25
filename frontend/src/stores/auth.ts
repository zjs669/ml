import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import * as authApi from '@/api/auth'
import { clearToken, getToken, setToken } from '@/api/token'
import type { UserProfile } from '@/api/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserProfile | null>(null)
  const ready = ref(false)
  const loading = ref(false)

  const isLoggedIn = computed(() => user.value !== null)

  function applyToken(token: string): void {
    setToken(token)
  }

  async function bootstrap(): Promise<void> {
    if (ready.value) return
    if (!getToken()) {
      ready.value = true
      return
    }
    try {
      user.value = await authApi.me()
    } catch {
      // 令牌过期且 refresh 也失败：静默退出登录态
      clearToken()
      user.value = null
    } finally {
      ready.value = true
    }
  }

  async function login(email: string, password: string): Promise<void> {
    loading.value = true
    try {
      const data = await authApi.login(email, password)
      applyToken(data.access_token)
      user.value = data.user
      ready.value = true
    } finally {
      loading.value = false
    }
  }

  async function register(email: string, password: string, displayName?: string): Promise<void> {
    loading.value = true
    try {
      const data = await authApi.register({
        email,
        password,
        display_name: displayName || null,
      })
      applyToken(data.access_token)
      user.value = data.user
      ready.value = true
    } finally {
      loading.value = false
    }
  }

  async function logout(): Promise<void> {
    try {
      await authApi.logout()
    } catch {
      // 即使后端不可达，本地也必须清掉
    } finally {
      clearToken()
      user.value = null
    }
  }

  function setUser(next: UserProfile): void {
    user.value = next
  }

  return { user, ready, loading, isLoggedIn, bootstrap, login, register, logout, setUser }
})
