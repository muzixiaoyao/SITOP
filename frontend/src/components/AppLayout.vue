<template>
  <el-container style="min-height: 100vh">
    <el-header class="app-header">
      <div class="header-left">
        <h1 class="logo">智枢 SITOP</h1>
        <el-menu :default-active="currentRoute" mode="horizontal" :ellipsis="false" router class="nav-menu">
          <el-menu-item index="/dashboard">仪表盘</el-menu-item>
          <el-menu-item index="/servers">服务器管理</el-menu-item>
          <el-menu-item index="/scripts">脚本库</el-menu-item>
          <el-menu-item index="/templates">模板管理</el-menu-item>
          <el-menu-item index="/repository">软件仓库</el-menu-item>
          <el-menu-item index="/jobs">任务中心</el-menu-item>
          <el-menu-item v-if="isAdmin" index="/audit-logs">审计日志</el-menu-item>
          <el-menu-item v-if="isAdmin" index="/users">用户管理</el-menu-item>
        </el-menu>
      </div>
      <div class="header-right">
        <el-tag>{{ auth.tenantName }}</el-tag>
        <el-tag v-if="roleLabel" type="info" effect="plain">{{ roleLabel }}</el-tag>
        <el-dropdown @command="handleCommand">
          <span class="user-info">{{ auth.user?.username }}</span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-header>
    <el-main><slot /></el-main>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const currentRoute = computed(() => route.path)
const isAdmin = computed(() => auth.user?.role === 'admin')
const roleLabel = computed(() => {
  const map: Record<string, string> = { admin: '管理员', operator: '操作员', viewer: '只读' }
  return map[auth.user?.role || ''] || ''
})

function handleCommand(command: string) {
  if (command === 'logout') {
    auth.logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.app-header {
  display: flex; align-items: center; justify-content: space-between;
  background: #fff; border-bottom: 1px solid #e4e7ed; padding: 0 20px;
}
.header-left { display: flex; align-items: center; gap: 24px; }
.logo { font-size: 20px; color: #409eff; margin: 0; white-space: nowrap; }
.nav-menu { border-bottom: none !important; }
.header-right { display: flex; align-items: center; gap: 12px; }
.user-info { cursor: pointer; color: #606266; }
</style>
