<template>
  <AppLayout>
    <div class="tickets-page">
      <div class="page-header">
        <h2>工单管理</h2>
        <div>
          <el-button><el-icon><Upload /></el-icon> 导入</el-button>
          <el-button><el-icon><Download /></el-icon> 导出</el-button>
          <el-button type="primary" @click="$router.push('/tickets/create')">
            <el-icon><Plus /></el-icon> 创建工单
          </el-button>
        </div>
      </div>

      <div class="filter-bar">
        <el-form :inline="true">
          <el-form-item label="类型">
            <el-select v-model="filters.type" clearable placeholder="全部" @change="fetchTickets" style="width: 120px;">
              <el-option label="故障" value="fault" />
              <el-option label="需求" value="request" />
              <el-option label="内部请求" value="internal" />
              <el-option label="变更" value="change" />
            </el-select>
          </el-form-item>
          <el-form-item label="优先级">
            <el-select v-model="filters.priority" clearable placeholder="全部" @change="fetchTickets" style="width: 100px;">
              <el-option label="紧急" value="critical" />
              <el-option label="高" value="high" />
              <el-option label="中" value="medium" />
              <el-option label="低" value="low" />
            </el-select>
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="filters.status" clearable placeholder="全部" @change="fetchTickets" style="width: 120px;">
              <el-option label="待受理" value="pending" />
              <el-option label="已分派" value="assigned" />
              <el-option label="处理中" value="processing" />
              <el-option label="已解决" value="resolved" />
              <el-option label="已关闭" value="closed" />
              <el-option label="已取消" value="cancelled" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-input v-model="filters.search" placeholder="搜索标题/编号" clearable @clear="fetchTickets" @keyup.enter="fetchTickets" style="width: 200px;">
              <template #prefix><el-icon><Search /></el-icon></template>
            </el-input>
          </el-form-item>
        </el-form>
      </div>

      <div class="table-card">
        <el-table :data="tickets" v-loading="loading" stripe @row-click="goDetail" style="cursor: pointer;">
          <el-table-column type="selection" width="40" />
          <el-table-column prop="ticket_no" label="工单编号" width="180">
            <template #default="{ row }">
              <span style="font-family: monospace; color: #409eff;">{{ row.ticket_no }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
          <el-table-column prop="type" label="类型" width="90">
            <template #default="{ row }">
              <el-tag :type="typeTagMap[row.type]" size="small">{{ row.type_display }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="priority" label="优先级" width="90">
            <template #default="{ row }">
              <el-tag :type="priorityTagMap[row.priority]" size="small" effect="dark">{{ row.priority_display }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="statusTagMap[row.status]" size="small">{{ row.status_display }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="SLA" width="70">
            <template #default="{ row }">
              <span :class="'sla-dot sla-' + (row.slaStatus || 'green')"></span>
            </template>
          </el-table-column>
          <el-table-column prop="submitter_name" label="提交人" width="90" />
          <el-table-column prop="assignee_name" label="处理人" width="90">
            <template #default="{ row }">{{ row.assignee_name || '-' }}</template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="160">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
        </el-table>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 16px;">
          <div>
            <el-button size="small" disabled>批量分派</el-button>
            <el-button size="small" disabled>批量关闭</el-button>
          </div>
          <el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="total, prev, pager, next" @current-change="fetchTickets" />
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Upload, Download, Plus, Search } from '@element-plus/icons-vue'
import AppLayout from '@/components/AppLayout.vue'
import { ticketsApi, type Ticket } from '@/api/tickets'

const router = useRouter()
const loading = ref(false)
const tickets = ref<Ticket[]>([])
const total = ref(0)
const page = ref(1)
const filters = ref({ type: '', priority: '', status: '', search: '' })

const typeTagMap: Record<string, string> = { fault: 'danger', request: 'primary', internal: 'info', change: 'warning' }
const priorityTagMap: Record<string, string> = { critical: 'danger', high: 'warning', medium: '', low: 'info' }
const statusTagMap: Record<string, string> = { pending: 'info', assigned: '', processing: 'warning', resolved: 'success', closed: 'info', cancelled: 'info' }

function formatDate(d: string) {
  return new Date(d).toLocaleString('zh-CN')
}

async function fetchTickets() {
  loading.value = true
  try {
    const { data } = await ticketsApi.list({ ...filters.value, page: page.value })
    tickets.value = data.results || data
    total.value = data.count || tickets.value.length
  } finally {
    loading.value = false
  }
}

function goDetail(row: Ticket) {
  router.push(`/tickets/${row.id}`)
}

onMounted(fetchTickets)
</script>

<style scoped>
.tickets-page { max-width: 1400px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.filter-bar { margin-bottom: 16px; background: #fff; padding: 16px; border-radius: 4px; }
.table-card { background: #fff; border-radius: 4px; padding: 16px; }
.sla-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; }
.sla-green { background: #67c23a; }
.sla-yellow { background: #e6a23c; }
.sla-red { background: #f56c6c; }
.sla-gray { background: #909399; }
</style>
