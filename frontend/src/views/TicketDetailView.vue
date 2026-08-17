<template>
  <AppLayout>
    <div class="ticket-detail" v-loading="loading">
      <template v-if="ticket">
        <el-button text @click="$router.back()" style="margin-bottom: 12px;">← 返回</el-button>

        <div class="ticket-header-row">
          <span class="ticket-no">{{ ticket.ticket_no }}</span>
          <el-tag :type="typeTagMap[ticket.type]" size="small">{{ ticket.type_display }}</el-tag>
          <el-tag :type="priorityTagMap[ticket.priority]" size="small" effect="dark">{{ ticket.priority_display }}</el-tag>
          <el-tag :type="statusTagMap[ticket.status]" size="small">{{ ticket.status_display }}</el-tag>
        </div>
        <h2 class="ticket-title">{{ ticket.title }}</h2>

        <el-descriptions :column="3" border>
          <el-descriptions-item label="提交人">{{ ticket.submitter_name }}</el-descriptions-item>
          <el-descriptions-item label="处理人">{{ ticket.assignee_name || '未分派' }}</el-descriptions-item>
          <el-descriptions-item label="当前节点">{{ ticket.current_node_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDate(ticket.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="首次响应">{{ ticket.first_response_at ? formatDate(ticket.first_response_at) : '-' }}</el-descriptions-item>
          <el-descriptions-item label="关联任务">{{ ticket.related_job ? 'Job #' + ticket.related_job : '-' }}</el-descriptions-item>
        </el-descriptions>

        <el-card class="section-card">
          <template #header><span style="font-weight: 500;">流程进度</span></template>
          <div class="progress-bar">
            <div v-for="(step, i) in flowSteps" :key="i" class="progress-step">
              <div :class="['dot', { done: step.done, active: step.active }]">{{ step.done ? '✓' : step.active ? '●' : '' }}</div>
              <div :class="['label', { active: step.active }]">{{ step.label }}</div>
            </div>
          </div>
          <div class="sla-panel">
            <div class="sla-item">
              <div class="sla-label">响应 SLA</div>
              <div class="sla-value" :style="{ color: ticket.first_response_at ? '#67c23a' : '#e6a23c' }">
                {{ ticket.first_response_at ? '✅ 已响应' : '⏳ 等待响应' }}
              </div>
            </div>
            <div class="sla-item">
              <div class="sla-label">处理 SLA</div>
              <div class="sla-value" style="color: #e6a23c;">
                {{ ticket.assigned_at ? '处理中' : '等待分派' }}
              </div>
            </div>
          </div>
        </el-card>

        <el-card v-if="ticket.description" class="section-card">
          <template #header><span style="font-weight: 500;">问题描述</span></template>
          <div style="line-height: 1.8; white-space: pre-wrap;">{{ ticket.description }}</div>
        </el-card>

        <el-card class="section-card" v-if="showActions">
          <template #header><span style="font-weight: 500;">操作</span></template>
          <el-space>
            <el-button type="primary" @click="handleTransition">流转到下一节点</el-button>
            <el-button type="success" @click="handleResolve">解决工单</el-button>
            <el-button @click="showAssignDialog = true">转派给...</el-button>
            <el-button type="danger" plain @click="handleCancel">取消工单</el-button>
          </el-space>
        </el-card>

        <el-card class="section-card">
          <template #header><span style="font-weight: 500;">沟通记录</span></template>
          <div v-for="item in timelineItems" :key="item.id" class="timeline-item">
            <div :class="['timeline-avatar', { system: item.is_system }]">{{ item.is_system ? '系' : item.author_name[0] }}</div>
            <div class="timeline-content">
              <div class="timeline-meta">
                <strong>{{ item.is_system ? '系统' : item.author_name }}</strong>
                <span v-if="!item.is_system"> ({{ item.roleLabel || '用户' }})</span>
                · {{ formatDate(item.created_at) }}
              </div>
              <div :class="['timeline-text', { system: item.is_system }]">{{ item.content }}</div>
            </div>
          </div>
          <el-divider />
          <div>
            <el-input v-model="newComment" type="textarea" :rows="3" placeholder="输入评论..." />
            <el-button type="primary" @click="handleComment" :disabled="!newComment.trim()" style="margin-top: 8px;">发送评论</el-button>
          </div>
        </el-card>
      </template>
    </div>

    <!-- Assign Dialog -->
    <el-dialog v-model="showAssignDialog" title="转派工单" width="400px">
      <el-input v-model="assigneeName" placeholder="输入处理人用户名" />
      <template #footer>
        <el-button @click="showAssignDialog = false">取消</el-button>
        <el-button type="primary" @click="handleAssign">确认转派</el-button>
      </template>
    </el-dialog>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '@/components/AppLayout.vue'
import { ticketsApi, type Ticket } from '@/api/tickets'

const route = useRoute()
const loading = ref(false)
const ticket = ref<Ticket | null>(null)
const newComment = ref('')
const showAssignDialog = ref(false)
const assigneeName = ref('')

const typeTagMap: Record<string, string> = { fault: 'danger', request: '', internal: 'info', change: 'warning' }
const priorityTagMap: Record<string, string> = { critical: 'danger', high: 'warning', medium: '', low: 'info' }
const statusTagMap: Record<string, string> = { pending: 'info', assigned: '', processing: 'warning', resolved: 'success', closed: 'info', cancelled: 'info' }

const showActions = computed(() => ticket.value && !['closed', 'cancelled'].includes(ticket.value.status))

const flowSteps = computed(() => {
  const steps = [
    { label: '待受理', key: 'pending' },
    { label: '已分派', key: 'assigned' },
    { label: '处理中', key: 'processing' },
    { label: '已解决', key: 'resolved' },
    { label: '已关闭', key: 'closed' },
  ]
  const statusOrder = ['pending', 'assigned', 'processing', 'resolved', 'closed']
  const currentIdx = statusOrder.indexOf(ticket.value?.status || '')
  return steps.map((s, i) => ({
    ...s,
    done: i < currentIdx,
    active: i === currentIdx,
  }))
})

interface TimelineItem {
  id: string
  author_name: string
  content: string
  is_system: boolean
  created_at: string
  roleLabel: string
}

const timelineItems = computed<TimelineItem[]>(() => {
  if (!ticket.value) return []
  const comments: TimelineItem[] = (ticket.value.comments || []).map(c => ({
    id: c.id, author_name: c.author_name, content: c.content, is_system: c.is_system,
    created_at: c.created_at, roleLabel: '',
  }))
  const transitions: TimelineItem[] = (ticket.value.transitions || []).map(t => ({
    id: 't-' + t.id, author_name: t.operator_name, content: `流转：${t.from_node_name || '开始'} → ${t.to_node_name}${t.comment ? ' - ' + t.comment : ''}`,
    is_system: true, created_at: t.created_at, roleLabel: '',
  }))
  return [...comments, ...transitions].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
})

function formatDate(d: string) { return new Date(d).toLocaleString('zh-CN') }

async function fetchTicket() {
  loading.value = true
  try {
    const { data } = await ticketsApi.get(route.params.id as string)
    ticket.value = data
  } finally { loading.value = false }
}

async function handleTransition() {
  if (!ticket.value) return
  const { value } = await ElMessageBox.prompt('请输入备注', '流转到下一节点', { confirmButtonText: '确认', cancelButtonText: '取消' })
  await ticketsApi.transition(ticket.value.id, ticket.value.current_node || '', value)
  ElMessage.success('工单已流转')
  fetchTicket()
}

async function handleResolve() {
  if (!ticket.value) return
  const { value } = await ElMessageBox.prompt('请输入解决方案', '解决工单', { confirmButtonText: '解决', cancelButtonText: '取消' })
  await ticketsApi.resolve(ticket.value.id, value)
  ElMessage.success('工单已解决')
  fetchTicket()
}

async function handleAssign() {
  if (!ticket.value || !assigneeName.value) return
  ElMessage.info('转派功能需要用户搜索，后续实现')
  showAssignDialog.value = false
}

async function handleCancel() {
  if (!ticket.value) return
  const { value } = await ElMessageBox.prompt('请输入取消原因', '取消工单', { confirmButtonText: '取消工单', cancelButtonText: '返回' })
  await ticketsApi.cancel(ticket.value.id, value)
  ElMessage.success('工单已取消')
  fetchTicket()
}

async function handleComment() {
  if (!ticket.value || !newComment.value.trim()) return
  await ticketsApi.addComment(ticket.value.id, newComment.value)
  newComment.value = ''
  ElMessage.success('评论已发送')
  fetchTicket()
}

onMounted(fetchTicket)
</script>

<style scoped>
.ticket-detail { max-width: 1000px; }
.ticket-header-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.ticket-no { font-size: 14px; color: #909399; font-family: monospace; }
.ticket-title { font-size: 22px; color: #303133; margin-bottom: 16px; }
.section-card { margin-top: 16px; }
.progress-bar { display: flex; align-items: center; margin: 16px 0; }
.progress-step { display: flex; flex-direction: column; align-items: center; flex: 1; }
.progress-step .dot { width: 24px; height: 24px; border-radius: 50%; border: 2px solid #dcdfe6; background: #fff; display: flex; align-items: center; justify-content: center; font-size: 12px; }
.progress-step .dot.active { border-color: #409eff; background: #409eff; color: #fff; }
.progress-step .dot.done { border-color: #67c23a; background: #67c23a; color: #fff; }
.progress-step .label { font-size: 12px; color: #909399; margin-top: 4px; }
.progress-step .label.active { color: #409eff; font-weight: bold; }
.sla-panel { display: flex; gap: 24px; margin-top: 12px; }
.sla-item { flex: 1; }
.sla-item .sla-label { font-size: 13px; color: #909399; margin-bottom: 4px; }
.sla-item .sla-value { font-size: 15px; font-weight: 500; }
.timeline-item { display: flex; gap: 12px; padding: 12px 0; border-bottom: 1px solid #f0f0f0; }
.timeline-item:last-child { border-bottom: none; }
.timeline-avatar { width: 36px; height: 36px; border-radius: 50%; background: #409eff; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 14px; flex-shrink: 0; }
.timeline-avatar.system { background: #909399; }
.timeline-content { flex: 1; }
.timeline-meta { font-size: 12px; color: #909399; margin-bottom: 4px; }
.timeline-meta strong { color: #303133; }
.timeline-text { font-size: 14px; color: #303133; line-height: 1.6; }
.timeline-text.system { color: #909399; font-size: 13px; }
</style>
