<template>
  <el-container style="min-height: 100vh">
    <el-header class="app-header">
      <div class="header-left">
        <h1 class="logo">智枢 SITOP</h1>
        <div class="top-nav">
          <a class="top-nav-item" :class="{ active: topNav === 'dashboard' }" @click="switchTopNav('dashboard')">仪表盘</a>
          <a class="top-nav-item" :class="{ active: topNav === 'ops' }" @click="switchTopNav('ops')">运维管理</a>
          <a class="top-nav-item" :class="{ active: topNav === 'tickets' }" @click="switchTopNav('tickets')">工单管理</a>
          <a class="top-nav-item" :class="{ active: topNav === 'kb' }" @click="switchTopNav('kb')">知识库</a>
        </div>
      </div>
      <div class="header-right">
        <el-badge :value="unreadCount" :hidden="unreadCount === 0" class="notification-badge">
          <el-icon style="cursor: pointer; font-size: 18px;" @click="showNotifications = true"><Bell /></el-icon>
        </el-badge>
        <el-tag size="small">{{ auth.tenantName }}</el-tag>
        <el-dropdown @command="handleCommand">
          <span class="user-info">{{ auth.user?.username }} <el-icon style="font-size: 12px;"><ArrowDown /></el-icon></span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="settings"><el-icon><Setting /></el-icon> 系统设置</el-dropdown-item>
              <el-dropdown-item command="users" v-if="isAdmin"><el-icon><User /></el-icon> 用户管理</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-header>

    <div class="main-wrapper">
      <!-- Sidebar -->
      <div class="sidebar" v-if="topNav !== 'dashboard'" :class="{ collapsed: sidebarCollapsed }">
        <div class="sidebar-group-title">{{ sidebarTitle }}</div>
        <div
          v-for="item in sidebarItems"
          :key="item.path"
          class="sidebar-item"
          :class="{ active: route.path === item.path }"
          @click="router.push(item.path)"
        >
          <el-icon><component :is="iconMap[item.icon]" /></el-icon>
          <span class="sidebar-toggle-text">{{ item.label }}</span>
        </div>
        <!-- Config section for tickets -->
        <template v-if="topNav === 'tickets' && isAdmin">
          <div style="border-top: 1px solid #e4e7ed; margin: 8px 0;"></div>
          <div class="sidebar-group-title">配置</div>
          <div class="sidebar-item" :class="{ active: route.path === '/tickets/flows' }" @click="router.push('/tickets/flows')">
            <el-icon><SetUp /></el-icon>
            <span class="sidebar-toggle-text">流程模板</span>
          </div>
          <div class="sidebar-item" :class="{ active: route.path === '/tickets/sla' }" @click="router.push('/tickets/sla')">
            <el-icon><Timer /></el-icon>
            <span class="sidebar-toggle-text">SLA 策略</span>
          </div>
          <div class="sidebar-item" :class="{ active: route.path === '/tickets/templates' }" @click="router.push('/tickets/templates')">
            <el-icon><DocumentCopy /></el-icon>
            <span class="sidebar-toggle-text">工单模板</span>
          </div>
        </template>
        <!-- Toggle button -->
        <div class="sidebar-toggle" @click="sidebarCollapsed = !sidebarCollapsed">
          <svg v-if="sidebarCollapsed" width="10" height="12" viewBox="0 0 10 12" fill="currentColor"><polygon points="0,0 10,6 0,12" /></svg>
          <svg v-else width="10" height="12" viewBox="0 0 10 12" fill="currentColor"><polygon points="10,0 0,6 10,12" /></svg>
          <span class="sidebar-toggle-text">{{ sidebarCollapsed ? '展开' : '收起' }}</span>
        </div>
      </div>

      <!-- Content -->
      <div class="content-area" :class="{ 'sidebar-collapsed': sidebarCollapsed && topNav !== 'dashboard' }">
        <slot />
      </div>
    </div>

    <!-- Notification Drawer -->
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
import { Bell, ArrowDown, Setting, User, Monitor, Document, Files, Folder, List, Notebook, Tickets, SetUp, Timer, DocumentCopy } from '@element-plus/icons-vue'

// Icon map for dynamic sidebar icons
const iconMap: Record<string, any> = { Monitor, Document, Files, Folder, List, Notebook, Tickets, SetUp, Timer, DocumentCopy }
import { useAuthStore } from '@/stores/auth'
import { notificationsApi, type Notification } from '@/api/tickets'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const isAdmin = computed(() => ['admin', 'platform_admin'].includes(auth.user?.role || ''))

// Top nav state
const topNav = ref('dashboard')

// Determine topNav from current route
function syncTopNav() {
  const path = route.path
  if (path.startsWith('/tickets')) topNav.value = 'tickets'
  else if (path.startsWith('/kb')) topNav.value = 'kb'
  else if (['/servers', '/scripts', '/templates', '/repository', '/jobs', '/audit-logs', '/users'].some(p => path.startsWith(p))) topNav.value = 'ops'
  else topNav.value = 'dashboard'
}
syncTopNav()
watch(() => route.path, syncTopNav)

function switchTopNav(nav: string) {
  topNav.value = nav
  const defaultRoutes: Record<string, string> = {
    dashboard: '/dashboard',
    ops: '/servers',
    tickets: '/tickets',
    kb: '/kb',
  }
  router.push(defaultRoutes[nav])
}

// Sidebar
const sidebarCollapsed = ref(false)

const sidebarTitle = computed(() => {
  const map: Record<string, string> = { ops: '运维管理', tickets: '工单管理', kb: '知识库' }
  return map[topNav.value] || ''
})

const sidebarItems = computed(() => {
  const items: Record<string, Array<{ path: string; label: string; icon: string }>> = {
    ops: [
      { path: '/servers', label: '服务器管理', icon: 'Monitor' },
      { path: '/scripts', label: '脚本库', icon: 'Document' },
      { path: '/templates', label: '模板编排', icon: 'Files' },
      { path: '/repository', label: '软件仓库', icon: 'Folder' },
      { path: '/jobs', label: '任务中心', icon: 'List' },
    ],
    tickets: [
      { path: '/tickets', label: '全部工单', icon: 'List' },
      { path: '/tickets/create', label: '创建工单', icon: 'Tickets' },
    ],
    kb: [
      { path: '/kb', label: '知识库首页', icon: 'Notebook' },
    ],
  }
  return items[topNav.value] || []
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
  } catch { /* ignore */ }
}

async function fetchNotifications() {
  try {
    const { data } = await notificationsApi.list()
    notifications.value = (data as Notification[]).map((n) => ({
      id: n.id, type: n.type,
      tagType: tagTypeMap[n.type] || 'info',
      time: new Date(n.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }),
      title: n.title,
    }))
  } catch { /* ignore */ }
}

watch(showNotifications, (val) => { if (val) fetchNotifications() })

function handleCommand(command: string) {
  if (command === 'logout') {
    if (pollTimer) clearInterval(pollTimer)
    auth.logout()
    router.push('/login')
  } else if (command === 'users') {
    router.push('/users')
  } else if (command === 'settings') {
    // TODO: settings page
  }
}

onMounted(() => { fetchUnreadCount(); pollTimer = setInterval(fetchUnreadCount, 60_000) })
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
</script>

<style scoped>
.app-header {
  display: flex; align-items: center; justify-content: space-between;
  background: #fff; border-bottom: 1px solid #e4e7ed; padding: 0 20px; height: 56px;
  position: fixed; top: 0; left: 0; right: 0; z-index: 100;
}
.header-left { display: flex; align-items: center; gap: 32px; }
.logo { font-size: 18px; color: #409eff; margin: 0; white-space: nowrap; font-weight: 600; }
.top-nav { display: flex; gap: 0; }
.top-nav-item {
  padding: 0 20px; height: 56px; display: flex; align-items: center;
  font-size: 14px; color: #606266; cursor: pointer; border-bottom: 2px solid transparent;
  transition: all 0.2s; text-decoration: none;
}
.top-nav-item:hover { color: #409eff; background: #ecf5ff; }
.top-nav-item.active { color: #409eff; border-bottom-color: #409eff; font-weight: 500; }
.header-right { display: flex; align-items: center; gap: 12px; }
.user-info { cursor: pointer; color: #606266; display: flex; align-items: center; gap: 4px; font-size: 13px; }
.notification-badge { line-height: 1; }

.main-wrapper { display: flex; margin-top: 56px; min-height: calc(100vh - 56px); }
.sidebar {
  width: 200px; background: #fff; border-right: 1px solid #e4e7ed;
  padding-top: 8px; flex-shrink: 0; position: fixed; top: 56px; bottom: 0;
  overflow-y: auto; overflow-x: hidden; transition: width 0.25s ease;
  display: flex; flex-direction: column; z-index: 10;
}
.sidebar.collapsed { width: 56px !important; }
.sidebar.collapsed .sidebar-item { padding: 12px 0; justify-content: center; }
.sidebar.collapsed .sidebar-item .el-icon { font-size: 20px; }
.sidebar.collapsed .sidebar-group-title { display: none; }
.sidebar.collapsed .sidebar-toggle-text { display: none; opacity: 0; width: 0; }
.sidebar-group-title { padding: 12px 20px 6px; font-size: 11px; color: #909399; text-transform: uppercase; letter-spacing: 1px; }
.sidebar-item {
  padding: 12px 20px; font-size: 14px; color: #606266; cursor: pointer;
  transition: all 0.15s; display: flex; align-items: center; gap: 8px;
}
.sidebar-item:hover { background: #ecf5ff; color: #409eff; }
.sidebar-item.active { background: #ecf5ff; color: #409eff; font-weight: 500; border-right: 2px solid #409eff; }
.sidebar-toggle {
  margin-top: auto; padding: 12px 16px; border-top: 1px solid #e4e7ed;
  cursor: pointer; display: flex; align-items: center; gap: 8px;
  color: #909399; font-size: 13px; transition: all 0.15s;
}
.sidebar-toggle:hover { background: #f5f7fa; color: #409eff; }
.sidebar.collapsed .sidebar-toggle { justify-content: center; padding: 12px 0; }
.content-area { flex: 1; margin-left: 200px; padding: 20px; transition: margin-left 0.25s ease; }
.content-area.sidebar-collapsed { margin-left: 56px; }
</style>
