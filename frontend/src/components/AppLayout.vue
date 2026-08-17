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
          <el-menu-item index="/tickets">工单管理</el-menu-item>
          <el-menu-item v-if="isAdmin" index="/audit-logs">审计日志</el-menu-item>
          <el-menu-item v-if="isAdmin" index="/users">用户管理</el-menu-item>
        </el-menu>
      </div>
      <div class="header-right">
        <a href="/docs/index.html" target="_blank" class="guide-link" title="用户指南">
          <el-icon><question-filled /></el-icon>
          <span>用户指南</span>
        </a>
        <el-badge :value="unreadCount" :hidden="unreadCount === 0" class="notification-badge">
          <el-icon style="cursor: pointer; font-size: 18px;" @click="showNotifications = true"><Bell /></el-icon>
        </el-badge>
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

    <el-drawer v-model="showNotifications" title="通知" direction="rtl" size="360px">
      <div v-for="n in notifications" :key="n.id" style="padding: 12px 0; border-bottom: 1px solid #f0f0f0;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <el-tag :type="n.tagType" size="small">{{ n.type }}</el-tag>
          <span style="font-size: 12px; color: #909399;">{{ n.time }}</span>
        </div>
        <div style="margin-top: 6px; font-size: 14px; color: #303133;">{{ n.title }}</div>
      </div>
      <el-empty v-if="notifications.length === 0" description="暂无通知" :image-size="80" />
    </el-drawer>
  </el-container>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { QuestionFilled, Bell } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { notificationsApi, type Notification } from '@/api/tickets'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const currentRoute = computed(() => route.path)
const isAdmin = computed(() => ['admin', 'platform_admin'].includes(auth.user?.role || ''))
const roleLabel = computed(() => {
  const map: Record<string, string> = {
    admin: '平台管理员', operator: '运维员', viewer: '只读',
    enterprise_admin: '企业管理员', enterprise_user: '企业员工',
  }
  return map[auth.user?.role || ''] || ''
})

// Notification state
const unreadCount = ref(0)
const showNotifications = ref(false)
const notifications = ref<Array<{ id: string; type: string; tagType: '' | 'success' | 'warning' | 'danger' | 'info'; time: string; title: string }>>([])
let pollTimer: ReturnType<typeof setInterval> | null = null

const tagTypeMap: Record<string, '' | 'success' | 'warning' | 'danger' | 'info'> = {
  fault: 'danger', critical: 'danger', high: 'warning',
  assigned: 'info', resolved: 'success', closed: 'success',
}

async function fetchUnreadCount() {
  try {
    const { data } = await notificationsApi.unreadCount()
    unreadCount.value = data.count
  } catch {
    // silently ignore
  }
}

async function fetchNotifications() {
  try {
    const { data } = await notificationsApi.list()
    notifications.value = (data as Notification[]).map((n) => ({
      id: n.id,
      type: n.type,
      tagType: tagTypeMap[n.type] || 'info',
      time: new Date(n.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }),
      title: n.title,
    }))
  } catch {
    // silently ignore
  }
}

watch(showNotifications, (val) => {
  if (val) fetchNotifications()
})

function handleCommand(command: string) {
  if (command === 'logout') {
    if (pollTimer) clearInterval(pollTimer)
    auth.logout()
    router.push('/login')
  }
}

onMounted(() => {
  fetchUnreadCount()
  pollTimer = setInterval(fetchUnreadCount, 60_000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
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
.guide-link {
  display: inline-flex; align-items: center; gap: 4px;
  color: #909399; font-size: 13px; text-decoration: none;
  padding: 4px 10px; border-radius: 4px; transition: all .2s;
}
.guide-link:hover { color: #409eff; background: #ecf5ff; }
.notification-badge { line-height: 1; }
</style>
