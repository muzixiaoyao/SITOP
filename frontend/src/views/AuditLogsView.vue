<template>
  <AppLayout>
    <div class="audit-page">
      <el-card>
        <template #header>
          <div class="page-header">
            <span>审计日志</span>
            <div class="filters">
              <el-input v-model="filters.action" placeholder="按操作筛选" clearable style="width: 180px" @change="load" />
              <el-input v-model="filters.resource_type" placeholder="按资源类型筛选" clearable style="width: 180px" @change="load" />
            </div>
          </div>
        </template>
        <el-table empty-text="暂无数据" :data="logs" stripe v-loading="loading">
          <el-table-column prop="created_at" label="时间" width="180">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
          <el-table-column prop="username" label="用户" width="120" />
          <el-table-column prop="action" label="操作" width="160">
            <template #default="{ row }"><el-tag size="small">{{ row.action }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="resource_type" label="资源类型" width="120" />
          <el-table-column prop="resource_id" label="资源 ID" width="280">
            <template #default="{ row }"><span class="mono">{{ row.resource_id }}</span></template>
          </el-table-column>
          <el-table-column prop="ip_address" label="IP" width="130" />
          <el-table-column label="详情">
            <template #default="{ row }">
              <span class="mono details">{{ JSON.stringify(row.details) }}</span>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination
          v-if="total > pageSize"
          style="margin-top: 12px; justify-content: flex-end"
          layout="prev, pager, next"
          :total="total"
          :page-size="pageSize"
          v-model:current-page="page"
          @current-change="load"
        />
      </el-card>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import AppLayout from '@/components/AppLayout.vue'
import { auditApi, type AuditLogEntry } from '@/api/reports'

const logs = ref<AuditLogEntry[]>([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = 20
const filters = reactive({ action: '', resource_type: '' })

onMounted(() => load())

async function load() {
  loading.value = true
  try {
    const { data } = await auditApi.list({
      action: filters.action || undefined,
      resource_type: filters.resource_type || undefined,
      page: page.value,
    })
    logs.value = (data as any).results || []
    total.value = (data as any).count || 0
  } finally { loading.value = false }
}

function formatDate(d: string) { return new Date(d).toLocaleString('zh-CN') }
</script>

<style scoped>
.audit-page { padding: 16px; }
.page-header { display: flex; justify-content: space-between; align-items: center; font-size: 16px; font-weight: 600; gap: 8px; }
.filters { display: flex; gap: 8px; }
.mono { font-family: monospace; font-size: 12px; }
.details { color: #909399; }
</style>
