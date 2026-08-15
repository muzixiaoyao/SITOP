import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi, type UserInfo } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserInfo | null>(null)
  const accessToken = ref<string | null>(localStorage.getItem('access_token'))

  const isAuthenticated = computed(() => !!accessToken.value)
  const tenantName = computed(() => user.value?.tenant.name ?? '')

  async function login(username: string, password: string) {
    const { data } = await authApi.login({ username, password })
    accessToken.value = data.access
    localStorage.setItem('access_token', data.access)
    localStorage.setItem('refresh_token', data.refresh)
    await fetchUser()
  }

  async function fetchUser() {
    const { data } = await authApi.getMe()
    user.value = data
  }

  function logout() {
    user.value = null
    accessToken.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }

  return { user, accessToken, isAuthenticated, tenantName, login, fetchUser, logout }
})
