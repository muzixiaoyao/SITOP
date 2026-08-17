import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { requiresAuth: false },
    },
    {
      path: '/',
      redirect: '/dashboard',
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('@/views/DashboardView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/servers',
      name: 'servers',
      component: () => import('@/views/ServersView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/scripts',
      name: 'scripts',
      component: () => import('@/views/ScriptsView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/templates',
      name: 'templates',
      component: () => import('@/views/TemplatesView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/jobs',
      name: 'jobs',
      component: () => import('@/views/JobsView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/audit-logs',
      name: 'audit-logs',
      component: () => import('@/views/AuditLogsView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/users',
      name: 'users',
      component: () => import('@/views/UsersView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/repository',
      name: 'repository',
      component: () => import('@/views/RepositoryView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/tickets',
      name: 'tickets',
      component: () => import('@/views/TicketsView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/tickets/create',
      name: 'ticket-create',
      component: () => import('@/views/TicketDetailView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/tickets/:id',
      name: 'ticket-detail',
      component: () => import('@/views/TicketDetailView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/kb',
      name: 'kb',
      component: () => import('@/views/KnowledgeBaseView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/kb/:slug',
      name: 'kb-article',
      component: () => import('@/views/ArticleDetailView.vue'),
      meta: { requiresAuth: true },
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'login' }
  }
  if (to.meta.requiresAuth && !auth.user) {
    try {
      await auth.fetchUser()
    } catch {
      auth.logout()
      return { name: 'login' }
    }
  }
})

export default router
