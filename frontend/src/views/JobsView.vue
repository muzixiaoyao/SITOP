<template>
  <AppLayout>
    <div class="jobs-page">
      <el-card>
        <template #header>
          <div class="page-header">
            <span>任务中心</span>
            <el-button type="primary" @click="showCreateJob = true">新建任务</el-button>
          </div>
        </template>
        <el-table empty-text="暂无数据" :data="jobs" stripe v-loading="loading">
          <el-table-column prop="template_name" label="模板" width="180" />
          <el-table-column prop="group_name" label="服务器组" width="150" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="statusColor(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="current_phase" label="当前阶段" width="120">
            <template #default="{ row }">{{ phaseLabel(row.current_phase) }}</template>
          </el-table-column>
          <el-table-column label="进度" width="120">
            <template #default="{ row }">{{ row.completed_servers }}/{{ row.total_servers }}</template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="180">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="80" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="selectJob(row)">详情</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card v-if="selectedJob" class="job-detail" style="margin-top: 16px">
        <template #header>
          <div class="page-header">
            <span>任务详情: {{ selectedJob.template_name }}</span>
            <div>
              <el-button size="small" @click="exportJobLogs">导出全部日志</el-button>
              <el-button v-if="['success','failed','cancelled'].includes(selectedJob.status)" size="small" @click="exportReport('csv')">导出 CSV</el-button>
              <el-button v-if="['success','failed','cancelled'].includes(selectedJob.status)" size="small" @click="exportReport('pdf')">导出 PDF</el-button>
              <el-button v-if="selectedJob.status === 'running' || selectedJob.status === 'pending'" type="danger" size="small" @click="cancelJob">取消任务</el-button>
              <el-button size="small" @click="refreshJob">刷新</el-button>
            </div>
          </div>
        </template>
        <el-steps :active="activePhaseIndex" finish-status="success" simple style="margin-bottom: 16px">
          <el-step title="连通性检查" />
          <el-step title="健康检查" />
          <el-step title="初始化" />
          <el-step title="完成度检查" />
        </el-steps>
        <el-descriptions :column="3" border>
          <el-descriptions-item label="状态"><el-tag :type="statusColor(selectedJob.status)" size="small">{{ statusLabel(selectedJob.status) }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="阶段">{{ phaseLabel(selectedJob.current_phase) }}</el-descriptions-item>
          <el-descriptions-item label="进度">{{ selectedJob.completed_servers }}/{{ selectedJob.total_servers }}</el-descriptions-item>
        </el-descriptions>

        <h4 style="margin: 16px 0 8px">服务器任务</h4>
        <el-table empty-text="暂无数据" :data="selectedJob.server_tasks || []" stripe size="small">
          <el-table-column prop="hostname" label="主机名" width="150" />
          <el-table-column prop="ip" label="IP" width="130" />
          <el-table-column prop="status" label="状态" width="80">
            <template #default="{ row }"><el-tag :type="statusColor(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag></template>
          </el-table-column>
          <el-table-column label="执行日志" min-width="400">
            <template #default="{ row }">
              <div v-for="log in (row.step_logs || [])" :key="log.id" class="log-entry" @click.stop="openLogDrawer(row, log)">
                <el-tag :type="log.status === 'success' ? 'success' : 'danger'" size="small">{{ log.phase }}</el-tag>
                <span v-if="log.script_name" class="log-script-name">{{ log.script_name }}</span>
                <pre class="log-output">{{ log.output || log.error || '(无输出)' }}</pre>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <h4 style="margin: 16px 0 8px">完成度矩阵</h4>
        <el-table empty-text="暂无数据" :data="completionMatrix" stripe size="small" v-if="completionMatrix.length > 0">
          <el-table-column prop="hostname" label="服务器" width="150" />
          <el-table-column label="连通性" width="80">
            <template #default="{ row }"><el-tag :type="row.connectivity === 'success' ? 'success' : 'danger'" size="small">{{ row.connectivity === 'success' ? '✓' : '✗' }}</el-tag></template>
          </el-table-column>
          <el-table-column label="健康检查" width="80">
            <template #default="{ row }"><el-tag :type="row.health === 'success' ? 'success' : row.health === 'skipped' ? 'info' : 'danger'" size="small">{{ row.health === 'success' ? '✓' : row.health === 'skipped' ? '-' : '' }}</el-tag></template>
          </el-table-column>
          <el-table-column v-for="n in maxSteps" :key="n" :label="'步骤' + n" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.steps[n-1]" :type="row.steps[n-1] === 'success' ? 'success' : 'danger'" size="small">{{ row.steps[n-1] === 'success' ? '✓' : '✗' }}</el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="完成度" width="80">
            <template #default="{ row }"><el-tag :type="row.completion === 'success' ? 'success' : row.completion === 'skipped' ? 'info' : 'danger'" size="small">{{ row.completion === 'success' ? '✓' : row.completion === 'skipped' ? '-' : '' }}</el-tag></template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="暂无完成度数据" :image-size="60" />
      </el-card>

      <el-drawer v-model="showLogDrawer" :title="`执行日志 — ${logDrawerTask?.hostname || ''}`" size="55%">
        <div v-for="log in (logDrawerTask?.step_logs || [])" :key="log.id" class="drawer-log">
          <div class="drawer-log-header">
            <el-tag :type="log.status === 'success' ? 'success' : 'danger'" size="small">{{ phaseLabel(log.phase) }}</el-tag>
            <span v-if="log.script_name" class="log-script">{{ log.script_name }}</span>
            <span v-if="log.exit_code !== null && log.exit_code !== undefined" class="log-exit">exit={{ log.exit_code }}</span>
            <span class="log-time">{{ formatDate(log.started_at) }}</span>
          </div>
          <pre class="drawer-log-output">{{ log.output || log.error || '(无输出)' }}</pre>
        </div>
      </el-drawer>

      <el-dialog v-model="showCreateJob" title="新建初始化任务" width="500px">
        <el-form label-width="100px">
          <el-form-item label="选择模板">
            <el-select v-model="newJobTemplate" style="width: 100%">
              <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="选择服务器组">
            <el-select v-model="newJobGroup" style="width: 100%">
              <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
            </el-select>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showCreateJob = false">取消</el-button>
          <el-button type="primary" :loading="creating" @click="createJob">启动任务</el-button>
        </template>
      </el-dialog>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '@/components/AppLayout.vue'
import { jobApi, templateApi, subscribeJob, type InitJob, type InitTemplate, type ServerTask, type StepLog } from '@/api/tasks'
import { serverApi, type ServerGroup } from '@/api/server'
import { downloadReport } from '@/api/reports'

const jobs = ref<InitJob[]>([])
const templates = ref<InitTemplate[]>([])
const groups = ref<ServerGroup[]>([])
const loading = ref(false)
const selectedJob = ref<InitJob | null>(null)
const showCreateJob = ref(false)
const creating = ref(false)
const newJobTemplate = ref('')
const newJobGroup = ref('')
const showLogDrawer = ref(false)
const logDrawerTask = ref<ServerTask | null>(null)

let pollTimer: ReturnType<typeof setInterval> | null = null
let unsubscribeWs: (() => void) | null = null

const PHASES = ['connectivity', 'health', 'init', 'completion']
const activePhaseIndex = computed(() => {
  if (!selectedJob.value) return 0
  if (['success', 'failed', 'cancelled'].includes(selectedJob.value.status)) return 4
  return PHASES.indexOf(selectedJob.value.current_phase)
})

const maxSteps = computed(() => {
  if (!selectedJob.value?.server_tasks) return 0
  let max = 0
  for (const task of selectedJob.value.server_tasks) {
    for (const log of task.step_logs || []) {
      if (log.phase === 'init' && log.step_order && log.step_order > max) max = log.step_order
    }
  }
  return max
})

const completionMatrix = computed(() => {
  if (!selectedJob.value?.server_tasks) return []
  return selectedJob.value.server_tasks.map(task => {
    const logs = task.step_logs || []
    const connLog = logs.find(l => l.phase === 'connectivity')
    const healthLog = logs.find(l => l.phase === 'health')
    const completionLog = logs.find(l => l.phase === 'completion')
    const initLogs = logs.filter(l => l.phase === 'init').sort((a, b) => (a.step_order || 0) - (b.step_order || 0))
    const steps: string[] = []
    for (const log of initLogs) {
      steps.push(log.status)
    }
    return {
      hostname: task.hostname,
      connectivity: connLog?.status || 'pending',
      health: healthLog?.status || 'skipped',
      steps,
      completion: completionLog?.status || 'skipped',
    }
  })
})

onMounted(async () => {
  await Promise.all([loadJobs(), loadTemplates(), loadGroups()])
})

onUnmounted(() => {
  stopLiveUpdates()
})

function startLiveUpdates(job: InitJob) {
  stopLiveUpdates()
  // WebSocket for instant events + polling as reliable fallback
  unsubscribeWs = subscribeJob(job.id, () => refreshJob())
  pollTimer = setInterval(async () => {
    await refreshJob()
    if (selectedJob.value && ['success', 'failed', 'cancelled'].includes(selectedJob.value.status)) {
      stopLiveUpdates()
      await loadJobs()
    }
  }, 2000)
}

function stopLiveUpdates() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  if (unsubscribeWs) { unsubscribeWs(); unsubscribeWs = null }
}

// 导出全部日志为自包含 HTML（双击即可查看，含命令执行记录与输出）
function exportJobLogs() {
  if (!selectedJob.value) return
  const job = selectedJob.value
  const esc = (s: string) => (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
  const statusColor: Record<string, string> = { success: '#67c23a', failed: '#f56c6c', running: '#409eff', pending: '#909399', cancelled: '#e6a23c' }
  const badge = (s: string) => '<span class="badge" style="background:' + (statusColor[s] || '#909399') + '">' + esc(statusLabel(s)) + '</span>'
  // 日志排序：连通性 → 健康检查 → 初始化(按 step_order) → 完成度
  const phaseOrder: Record<string, number> = { connectivity: 0, health: 1, init: 2, completion: 3 }
  const sortLogs = (logs: StepLog[]) => [...logs].sort((a, b) =>
    (phaseOrder[a.phase] ?? 9) - (phaseOrder[b.phase] ?? 9) || (a.step_order || 0) - (b.step_order || 0))

  const tasks = job.server_tasks || []
  const sections = tasks.map((task, idx) => {
    const logs = sortLogs(task.step_logs || []).map(log => {
      const content = log.output || log.error || '(无输出)'
      const exit = log.exit_code !== null && log.exit_code !== undefined ? '<span class="exit">exit=' + log.exit_code + '</span>' : ''
      const time = log.started_at
        ? '<span class="time">' + esc(formatDate(log.started_at)) + (log.ended_at ? ' ~ ' + esc(formatDate(log.ended_at)) : '') + '</span>'
        : ''
      const stepNo = log.phase === 'init' && log.step_order ? ' #' + log.step_order : ''
      return '<div class="log">' +
        '<div class="log-meta">' +
          '<span class="phase ' + (log.status === 'success' ? 'ok' : 'err') + '">' + esc(phaseLabel(log.phase)) + stepNo + '</span>' +
          (log.script_name ? '<span class="script">' + esc(log.script_name) + '</span>' : '') +
          exit + badge(log.status) + time +
        '</div>' +
        '<pre class="output">' + esc(content) + '</pre>' +
      '</div>'
    }).join('\n')
    const st = task.status || 'pending'
    return '<section class="server' + (st === 'failed' ? ' failed' : '') + '" id="srv-' + idx + '" data-status="' + st + '" data-hostname="' + esc((task.hostname || '').toLowerCase()) + '" data-ip="' + esc(task.ip || '') + '">' +
      '<h2>' + esc(task.hostname || '(未知主机)') + ' <span class="ip">' + esc(task.ip || '') + '</span> ' + badge(st) + '</h2>' +
      (logs || '<p class="empty">(无执行日志)</p>') +
    '</section>'
  }).join('\n')

  // 统计与导航 chips
  const statCount = (s: string) => tasks.filter(t => (t.status || 'pending') === s).length
  const okCount = statCount('success')
  const rate = tasks.length ? Math.round((okCount / tasks.length) * 1000) / 10 : 0
  const presentStatuses = ['success', 'failed', 'running', 'pending', 'cancelled'].filter(s => statCount(s) > 0)
  const chipsHtml = tasks.map((t, i) =>
    '<a class="chip" data-target="srv-' + i + '" data-status="' + (t.status || 'pending') + '" data-hostname="' + esc((t.hostname || '').toLowerCase()) + '" data-ip="' + esc(t.ip || '') + '">' +
      '<span class="dot" style="background:' + (statusColor[t.status || ''] || '#909399') + '"></span>' + esc(t.hostname || '(未知)') +
    '</a>').join('')
  const filterBtnsHtml = '<button class="fbtn active" data-status="all">全部</button>' +
    presentStatuses.map(s => '<button class="fbtn" data-status="' + s + '">' + esc(statusLabel(s)) + ' ' + statCount(s) + '</button>').join('')
  const statCardsHtml =
    '<div class="stat-card"><div class="num" style="color:' + (rate === 100 ? '#67c23a' : '#e6a23c') + '">' + rate + '%</div><div class="lbl">成功率</div></div>' +
    '<div class="stat-card"><div class="num">' + tasks.length + '</div><div class="lbl">总节点</div></div>' +
    presentStatuses.map(s => '<div class="stat-card"><div class="num" style="color:' + (statusColor[s] || '#909399') + '">' + statCount(s) + '</div><div class="lbl">' + esc(statusLabel(s)) + '</div></div>').join('')

  const ts = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '')
  const html = '<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="utf-8">' +
    '<title>任务日志 - ' + esc(job.template_name) + '</title>' +
    '<style>' +
    'body{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;margin:0;background:#f5f7fa;color:#303133}' +
    '.wrap{max-width:1100px;margin:0 auto;padding:24px}' +
    'header{background:#fff;border-radius:8px;padding:20px 24px;margin-bottom:16px;box-shadow:0 1px 4px rgba(0,0,0,.06)}' +
    'header h1{margin:0 0 12px;font-size:20px}' +
    '.meta-line{color:#606266;font-size:13px;line-height:1.9}' +
    '.stats{display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap}' +
    '.stat-card{background:#fff;border-radius:8px;padding:14px 22px;box-shadow:0 1px 4px rgba(0,0,0,.06);min-width:100px;text-align:center}' +
    '.stat-card .num{font-size:24px;font-weight:700}' +
    '.stat-card .lbl{font-size:12px;color:#909399;margin-top:2px}' +
    '.toolbar{position:sticky;top:0;z-index:10;background:#f5f7fa;padding:10px 0;display:flex;gap:8px;align-items:center;flex-wrap:wrap}' +
    '.fbtn{border:1px solid #dcdfe6;background:#fff;border-radius:16px;padding:4px 14px;font-size:13px;cursor:pointer;color:#606266}' +
    '.fbtn.active{background:#409eff;color:#fff;border-color:#409eff}' +
    '#nodeSearch{border:1px solid #dcdfe6;border-radius:16px;padding:5px 12px;font-size:13px;width:200px;outline:none}' +
    '#filterCount{color:#909399;font-size:13px;margin-left:auto}' +
    '.chips{display:flex;gap:6px;flex-wrap:wrap;margin:4px 0 16px}' +
    '.chip{display:inline-flex;align-items:center;gap:5px;background:#fff;border:1px solid #ebeef5;border-radius:14px;padding:3px 10px;font-size:12px;cursor:pointer;color:#606266;text-decoration:none}' +
    '.chip:hover{border-color:#409eff;color:#409eff}' +
    '.chip .dot{width:8px;height:8px;border-radius:50%;display:inline-block}' +
    '.badge{display:inline-block;color:#fff;border-radius:4px;padding:1px 8px;font-size:12px;margin-right:4px}' +
    '.server{background:#fff;border-radius:8px;padding:16px 24px;margin-bottom:16px;box-shadow:0 1px 4px rgba(0,0,0,.06);scroll-margin-top:70px}' +
    '.server.failed{border-left:4px solid #f56c6c}' +
    '.server h2{margin:0 0 12px;font-size:16px;border-bottom:1px solid #ebeef5;padding-bottom:10px}' +
    '.ip{color:#909399;font-weight:normal;font-size:13px}' +
    '.log{margin-bottom:14px}' +
    '.log-meta{display:flex;align-items:center;gap:8px;font-size:12px;margin-bottom:4px;flex-wrap:wrap}' +
    '.phase{font-weight:600;padding:1px 6px;border-radius:4px}' +
    '.phase.ok{color:#67c23a;background:#f0f9eb}' +
    '.phase.err{color:#f56c6c;background:#fef0f0}' +
    '.script{font-family:monospace;color:#409eff}' +
    '.exit{font-family:monospace;color:#909399}' +
    '.time{color:#909399}' +
    '.output{background:#1e1e1e;color:#d4d4d4;border-radius:6px;padding:12px;font-family:Menlo,Consolas,monospace;font-size:12px;line-height:1.6;white-space:pre-wrap;word-break:break-all;margin:4px 0 0;max-height:480px;overflow:auto}' +
    '.empty{color:#909399}' +
    '</style></head><body><div class="wrap">' +
    '<header>' +
      '<h1>任务执行日志：' + esc(job.template_name) + ' ' + badge(job.status) + '</h1>' +
      '<div class="meta-line">导出时间：' + esc(new Date().toLocaleString('zh-CN')) +
      '　进度：' + job.completed_servers + '/' + job.total_servers + '</div>' +
    '</header>' +
    '<div class="stats">' + statCardsHtml + '</div>' +
    '<div class="toolbar">' + filterBtnsHtml +
      '<input id="nodeSearch" type="text" placeholder="搜索主机名 / IP">' +
      '<span id="filterCount"></span>' +
    '</div>' +
    '<div class="chips">' + chipsHtml + '</div>' +
    sections +
    '</div>' +
    '<script>(function(){' +
    'var secs=Array.prototype.slice.call(document.querySelectorAll("section.server"));' +
    'var chips=Array.prototype.slice.call(document.querySelectorAll(".chip"));' +
    'var cur="all",q="";' +
    'var countEl=document.getElementById("filterCount");' +
    'function apply(){var n=0;' +
    'secs.forEach(function(s){var ms=cur==="all"||s.dataset.status===cur;var mq=!q||s.dataset.hostname.indexOf(q)!==-1||s.dataset.ip.indexOf(q)!==-1;var show=ms&&mq;s.style.display=show?"":"none";if(show)n++;});' +
    'chips.forEach(function(c){var ms=cur==="all"||c.dataset.status===cur;var mq=!q||c.dataset.hostname.indexOf(q)!==-1||c.dataset.ip.indexOf(q)!==-1;c.style.display=(ms&&mq)?"":"none";});' +
    'countEl.textContent="匹配 "+n+" / "+secs.length+" 台";}' +
    'Array.prototype.forEach.call(document.querySelectorAll(".fbtn"),function(b){b.addEventListener("click",function(){Array.prototype.forEach.call(document.querySelectorAll(".fbtn"),function(x){x.classList.remove("active")});b.classList.add("active");cur=b.dataset.status;apply();});});' +
    'document.getElementById("nodeSearch").addEventListener("input",function(e){q=e.target.value.trim().toLowerCase();apply();});' +
    'chips.forEach(function(c){c.addEventListener("click",function(){var el=document.getElementById(c.dataset.target);if(el)el.scrollIntoView({behavior:"smooth",block:"start"});});});' +
    'apply();' +
    '})();</scr' + 'ipt>' +
    '</body></html>'

  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = '任务日志_' + (job.template_name || 'job') + '_' + ts + '.html'
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('日志已导出')
}

function openLogDrawer(task: ServerTask, _log: StepLog | null) {
  logDrawerTask.value = task
  showLogDrawer.value = true
}

async function loadJobs() {
  loading.value = true
  try {
    const { data } = await jobApi.list()
    jobs.value = Array.isArray(data) ? data : (data as any).results || []
  } finally { loading.value = false }
}

async function loadTemplates() {
  const { data } = await templateApi.list()
  templates.value = Array.isArray(data) ? data : (data as any).results || []
}

async function loadGroups() {
  const { data } = await serverApi.listGroups()
  groups.value = Array.isArray(data) ? data : (data as any).results || []
}

async function selectJob(row: InitJob) {
  const { data } = await jobApi.get(row.id)
  selectedJob.value = data as InitJob
  if (['pending', 'running'].includes(selectedJob.value.status)) {
    startLiveUpdates(selectedJob.value)
  }
  // 滚动到详情卡片
  await nextTick()
  const detailEl = document.querySelector('.job-detail')
  if (detailEl) detailEl.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function refreshJob() {
  if (selectedJob.value) {
    const { data } = await jobApi.get(selectedJob.value.id)
    selectedJob.value = data as InitJob
  }
}

async function cancelJob() {
  if (!selectedJob.value) return
  await ElMessageBox.confirm('确定取消该任务？正在执行的步骤将在当前阶段结束后停止。')
  await jobApi.cancel(selectedJob.value.id)
  ElMessage.success('任务已取消')
  await refreshJob()
  await loadJobs()
}

async function exportReport(format: 'csv' | 'pdf') {
  if (!selectedJob.value) return
  try {
    await downloadReport(selectedJob.value.id, format)
    ElMessage.success('报告已开始下载')
  } catch {
    ElMessage.error('报告下载失败')
  }
}

async function createJob() {
  if (!newJobTemplate.value || !newJobGroup.value) { ElMessage.warning('请选择模板和服务器组'); return }
  creating.value = true
  try {
    await jobApi.create({ template: newJobTemplate.value, group: newJobGroup.value })
    ElMessage.success('任务已创建并开始执行')
    showCreateJob.value = false; newJobTemplate.value = ''; newJobGroup.value = ''
    await loadJobs()
    // Open the newest job with live updates
    if (jobs.value.length > 0) await selectJob(jobs.value[0])
  } finally { creating.value = false }
}

function statusColor(s: string) { return { success: 'success', failed: 'danger', running: 'warning', pending: 'info', cancelled: 'info' }[s] || 'info' }
function statusLabel(s: string) { return { success: '成功', failed: '失败', running: '运行中', pending: '等待中', cancelled: '已取消' }[s] || s }
function phaseLabel(p: string) { return { connectivity: '连通性检查', health: '健康检查', init: '初始化', completion: '完成度检查' }[p] || p }
function formatDate(d: string) { return new Date(d).toLocaleString('zh-CN') }
</script>

<style scoped>
.jobs-page { padding: 16px; }
.page-header { display: flex; justify-content: space-between; align-items: center; font-size: 16px; font-weight: 600; gap: 8px; }
.log-entry { margin: 4px 0; font-size: 12px; display: flex; align-items: flex-start; gap: 6px; }
.log-script-name { font-weight: 600; color: #409eff; font-family: monospace; font-size: 11px; white-space: nowrap; }
.log-output { font-family: monospace; color: #303133; white-space: pre-wrap; word-break: break-all; margin: 0; font-size: 12px; line-height: 1.5; flex: 1; }
.log-entry { cursor: pointer; }
.drawer-log { margin-bottom: 16px; }
.drawer-log-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.log-script { font-weight: 600; color: #303133; }
.log-exit { color: #909399; font-family: monospace; font-size: 12px; }
.log-time { margin-left: auto; color: #909399; font-size: 12px; }
.drawer-log-output {
  background: #1e1e1e; color: #d4d4d4; padding: 10px; border-radius: 4px;
  font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-all;
  max-height: 300px; overflow-y: auto; margin: 0;
}
</style>
