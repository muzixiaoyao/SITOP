<template>
  <AppLayout>
    <div class="dashboard-page">
      <div class="stat-cards">
        <el-card class="stat-card">
          <div class="stat-value">{{ stats?.total_jobs ?? '-' }}</div>
          <div class="stat-label">总任务数</div>
        </el-card>
        <el-card class="stat-card">
          <div class="stat-value">{{ stats?.recent_jobs ?? '-' }}</div>
          <div class="stat-label">近 7 天任务</div>
        </el-card>
        <el-card class="stat-card">
          <div class="stat-value success">{{ stats?.success_rate ?? '-' }}%</div>
          <div class="stat-label">成功率</div>
        </el-card>
        <el-card class="stat-card">
          <div class="stat-value">{{ stats?.total_servers ?? '-' }}</div>
          <div class="stat-label">服务器总数</div>
        </el-card>
        <el-card class="stat-card">
          <div class="stat-value">{{ stats?.total_groups ?? '-' }}</div>
          <div class="stat-label">活跃分组</div>
        </el-card>
      </div>

      <div class="charts">
        <el-card class="chart-card">
          <template #header><span>近 7 天任务趋势</span></template>
          <div ref="trendChartRef" class="chart" />
        </el-card>
        <el-card class="chart-card small">
          <template #header><span>任务状态分布</span></template>
          <div ref="pieChartRef" class="chart" />
        </el-card>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import AppLayout from '@/components/AppLayout.vue'
import { statsApi, type DashboardStats } from '@/api/reports'

const stats = ref<DashboardStats | null>(null)
const trendChartRef = ref<HTMLElement>()
const pieChartRef = ref<HTMLElement>()
let trendChart: echarts.ECharts | null = null
let pieChart: echarts.ECharts | null = null

onMounted(async () => {
  const { data } = await statsApi.dashboard()
  stats.value = data
  renderCharts()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  trendChart?.dispose()
  pieChart?.dispose()
})

function handleResize() {
  trendChart?.resize()
  pieChart?.resize()
}

function renderCharts() {
  if (!stats.value) return
  // Trend line chart
  if (trendChartRef.value) {
    trendChart = echarts.init(trendChartRef.value)
    trendChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['任务总数', '成功数'] },
      grid: { left: 40, right: 20, top: 40, bottom: 30 },
      xAxis: { type: 'category', data: stats.value.trend.map((t) => t.date) },
      yAxis: { type: 'value', minInterval: 1 },
      series: [
        { name: '任务总数', type: 'line', smooth: true, data: stats.value.trend.map((t) => t.total), itemStyle: { color: '#409eff' } },
        { name: '成功数', type: 'line', smooth: true, data: stats.value.trend.map((t) => t.success), itemStyle: { color: '#67c23a' } },
      ],
    })
  }
  // Status pie chart
  if (pieChartRef.value) {
    pieChart = echarts.init(pieChartRef.value)
    const dist = stats.value.status_distribution
    const labelMap: Record<string, string> = {
      pending: '等待中', running: '运行中', success: '成功', failed: '失败', cancelled: '已取消',
    }
    pieChart.setOption({
      tooltip: { trigger: 'item' },
      series: [{
        type: 'pie',
        radius: ['40%', '70%'],
        data: Object.entries(dist)
          .filter(([, v]) => v > 0)
          .map(([k, v]) => ({ name: labelMap[k] || k, value: v })),
      }],
    })
  }
}
</script>

<style scoped>
.dashboard-page { padding: 16px; }
.stat-cards { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 16px; }
.stat-card { text-align: center; transition: transform 0.2s, box-shadow 0.2s; }
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08); }
.stat-value { font-size: 28px; font-weight: 700; color: #303133; }
.stat-value.success { color: #67c23a; }
.stat-label { font-size: 13px; color: #909399; margin-top: 4px; }
.charts { display: grid; grid-template-columns: 2fr 1fr; gap: 12px; }
.chart { height: 320px; }
@media (max-width: 900px) {
  .stat-cards { grid-template-columns: repeat(2, 1fr); }
  .charts { grid-template-columns: 1fr; }
}
</style>
