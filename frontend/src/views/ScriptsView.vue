<template>
  <AppLayout>
    <div class="scripts-page">
      <el-card>
        <template #header>
          <div class="page-header">
            <span>脚本库</span>
            <el-button type="primary" @click="showCreateDialog = true">新建脚本</el-button>
          </div>
        </template>
        <el-table :data="scripts" stripe v-loading="loading">
          <el-table-column prop="name" label="名称" width="200" />
          <el-table-column prop="script_type" label="类型" width="120">
            <template #default="{ row }">
              <el-tag :type="typeTagColor(row.script_type)" size="small">{{ typeLabel(row.script_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="language" label="语言" width="80" />
          <el-table-column prop="version" label="版本" width="60" />
          <el-table-column prop="description" label="描述" />
          <el-table-column prop="updated_at" label="更新时间" width="180">
            <template #default="{ row }">{{ formatDate(row.updated_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="200">
            <template #default="{ row }">
              <el-button type="success" size="small" link @click="openTestRun(row)">测试运行</el-button>
              <el-button type="primary" size="small" link @click="editScript(row)">编辑</el-button>
              <el-button type="danger" size="small" link @click="deleteScript(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-dialog v-model="showCreateDialog" :title="editingId ? '编辑脚本' : '新建脚本'" width="800px" top="5vh" @close="closeScriptDialog">
        <el-form :model="form" label-width="100px">
          <el-form-item label="名称" required>
            <el-input v-model="form.name" />
          </el-form-item>
          <el-form-item label="类型" required>
            <el-select v-model="form.script_type" style="width: 100%">
              <el-option label="健康检查" value="health_check" />
              <el-option label="初始化步骤" value="init_step" />
              <el-option label="完成度检查" value="completion_check" />
            </el-select>
          </el-form-item>
          <el-form-item label="语言">
            <el-radio-group v-model="form.language">
              <el-radio value="shell">Shell</el-radio>
              <el-radio value="python">Python</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="form.description" type="textarea" :rows="2" />
          </el-form-item>
          <el-form-item label="内容" required>
            <el-input v-model="form.content" type="textarea" :rows="12" class="code-editor" ref="contentInputRef" />
          </el-form-item>
          <el-form-item label="软件包">
            <el-button size="small" type="primary" plain @click="openPkgPicker">插入软件包变量</el-button>
            <span style="color: #909399; font-size: 12px; margin-left: 8px">在光标处插入 curl 下载命令（变量由 SITOP 自动注入）</span>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="closeScriptDialog">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveScript">保存</el-button>
        </template>
      </el-dialog>

      <el-dialog v-model="showTestRun" :title="`测试运行 — ${testRunScript?.name || ''}`" width="700px">
        <el-form label-width="100px">
          <el-form-item label="选择服务器">
            <el-select v-model="testRunGroupId" placeholder="选择分组" style="width: 45%; margin-right: 8px" @change="loadTestServers">
              <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
            </el-select>
            <el-select v-model="testRunServerId" placeholder="选择服务器" style="width: 45%">
              <el-option v-for="s in testServers" :key="s.id" :label="`${s.hostname} (${s.ip})`" :value="s.id" />
            </el-select>
          </el-form-item>
        </el-form>
        <div v-if="testRunResult" class="test-run-result">
          <el-alert
            :title="`执行完成 (exit=${testRunResult.exit_code})`"
            :type="testRunResult.exit_code === 0 ? 'success' : 'error'"
            :closable="false"
            style="margin-bottom: 8px"
          />
          <pre class="test-run-output">{{ testRunResult.output || testRunResult.error || '(无输出)' }}</pre>
        </div>
        <template #footer>
          <el-button @click="showTestRun = false">关闭</el-button>
          <el-button type="primary" :loading="testRunning" :disabled="!testRunServerId" @click="runTest">执行</el-button>
        </template>
      </el-dialog>

      <!-- Software Package Picker -->
      <el-dialog v-model="showPkgPicker" title="插入软件包变量" width="640px">
        <el-breadcrumb separator="/" style="margin-bottom: 10px">
          <el-breadcrumb-item><a @click.prevent="pkgNavigate('')">仓库根目录</a></el-breadcrumb-item>
          <el-breadcrumb-item v-for="(seg, idx) in pkgPathSegments" :key="idx">
            <a @click.prevent="pkgNavigate(pkgSegmentsUpTo(idx))">{{ seg }}</a>
          </el-breadcrumb-item>
        </el-breadcrumb>
        <el-table :data="pkgFiles" size="small" max-height="360" v-loading="pkgLoading" empty-text="暂无文件">
          <el-table-column label="名称" min-width="220">
            <template #default="{ row }">
              <el-button link type="primary" @click="pkgEnterDir(row)" v-if="row.is_dir">{{ row.name }}/</el-button>
              <span v-else>{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变量名" min-width="240">
            <template #default="{ row }">
              <span v-if="!row.is_dir" style="font-family: monospace; font-size: 12px">{{ row.variable }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button v-if="!row.is_dir" size="small" type="primary" link @click="insertPkg(row)">插入</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-dialog>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '@/components/AppLayout.vue'
import { scriptApi, type Script } from '@/api/tasks'
import { serverApi, type ServerGroup, type Server } from '@/api/server'
import { repositoryApi, type RepoItem } from '@/api/repository'

const scripts = ref<Script[]>([])
const loading = ref(false)
const showCreateDialog = ref(false)
const saving = ref(false)
const editingId = ref<string | null>(null)
const form = reactive({ name: '', script_type: 'init_step' as Script['script_type'], language: 'shell' as Script['language'], description: '', content: '' })
const contentInputRef = ref<{ textarea?: HTMLTextAreaElement } | null>(null)

// Test run state
const showTestRun = ref(false)
const testRunScript = ref<Script | null>(null)
const testRunGroupId = ref('')
const testRunServerId = ref('')
const testServers = ref<Server[]>([])
const groups = ref<ServerGroup[]>([])
const testRunning = ref(false)
const testRunResult = ref<{ exit_code: number; output: string; error: string } | null>(null)

// 插入软件包变量
const showPkgPicker = ref(false)
const pkgLoading = ref(false)
const pkgPath = ref('')
const pkgFiles = ref<RepoItem[]>([])
const pkgPathSegments = computed(() => pkgPath.value.split('/').filter(Boolean))

function pkgSegmentsUpTo(idx: number) {
  return pkgPathSegments.value.slice(0, idx + 1).join('/')
}

async function pkgNavigate(path: string) {
  pkgPath.value = path
  pkgLoading.value = true
  try {
    const { data } = await repositoryApi.listFiles(path)
    pkgFiles.value = data.items || []
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '仓库加载失败')
  } finally { pkgLoading.value = false }
}

function openPkgPicker() {
  pkgPath.value = ''
  pkgFiles.value = []
  showPkgPicker.value = true
  pkgNavigate('')
}

function pkgEnterDir(row: RepoItem) {
  pkgNavigate(row.rel_path)
}

function insertPkg(row: RepoItem) {
  const line = `curl -fsSL -O "$${row.variable}"`
  const comment = `# 下载软件包: ${row.name}（SITOP 自动注入仓库变量）`
  const snippet = `${comment}\n${line}\n`
  const el = contentInputRef.value?.textarea
  if (el && document.activeElement === el) {
    // 光标处插入
    const start = el.selectionStart ?? form.content.length
    const end = el.selectionEnd ?? start
    form.content = form.content.slice(0, start) + snippet + form.content.slice(end)
    // 恢复光标到插入内容之后
    requestAnimationFrame(() => {
      const pos = start + snippet.length
      el.setSelectionRange(pos, pos)
    })
  } else {
    // 未聚焦编辑器时追加到末尾
    form.content = form.content ? `${form.content}\n${snippet}` : snippet
  }
  ElMessage.success(`已插入 ${row.variable}`)
  showPkgPicker.value = false
}

onMounted(() => loadScripts())

async function loadScripts() {
  loading.value = true
  try {
    const { data } = await scriptApi.list()
    scripts.value = Array.isArray(data) ? data : (data as any).results || []
  } finally { loading.value = false }
}

function editScript(s: Script) {
  resetForm()
  editingId.value = s.id
  form.name = s.name; form.script_type = s.script_type; form.language = s.language
  form.description = s.description; form.content = s.content
  showCreateDialog.value = true
}

async function saveScript() {
  saving.value = true
  try {
    if (editingId.value) {
      await scriptApi.update(editingId.value, form)
      ElMessage.success('脚本已更新')
    } else {
      await scriptApi.create(form)
      ElMessage.success('脚本已创建')
    }
    showCreateDialog.value = false; editingId.value = null
    resetForm(); await loadScripts()
  } finally { saving.value = false }
}

function closeScriptDialog() {
  showCreateDialog.value = false
  editingId.value = null
  resetForm()
}

async function deleteScript(id: string) {
  await ElMessageBox.confirm('确定删除此脚本？')
  await scriptApi.delete(id)
  ElMessage.success('已删除'); await loadScripts()
}

async function openTestRun(script: Script) {
  testRunScript.value = script
  testRunResult.value = null
  testRunGroupId.value = ''
  testRunServerId.value = ''
  testServers.value = []
  showTestRun.value = true
  if (groups.value.length === 0) {
    const { data } = await serverApi.listGroups()
    groups.value = Array.isArray(data) ? data : (data as any).results || []
  }
}

async function loadTestServers() {
  testRunServerId.value = ''
  if (!testRunGroupId.value) { testServers.value = []; return }
  const { data } = await serverApi.listServers(testRunGroupId.value)
  testServers.value = Array.isArray(data) ? data : (data as any).results || []
}

async function runTest() {
  if (!testRunScript.value || !testRunServerId.value) return
  testRunning.value = true
  try {
    const { data } = await scriptApi.testRun(testRunScript.value.id, {
      server_id: testRunServerId.value,
      content: testRunScript.value.content,
    })
    testRunResult.value = data
  } finally { testRunning.value = false }
}

function resetForm() { form.name = ''; form.script_type = 'init_step'; form.language = 'shell'; form.description = ''; form.content = '' }
function typeLabel(t: string) { return { health_check: '健康检查', init_step: '初始化步骤', completion_check: '完成度检查' }[t] || t }
function typeTagColor(t: string) { return { health_check: 'success', init_step: 'primary', completion_check: 'warning' }[t] || 'info' }
function formatDate(d: string) { return new Date(d).toLocaleString('zh-CN') }
</script>

<style scoped>
.scripts-page { padding: 16px; }
.page-header { display: flex; justify-content: space-between; align-items: center; font-size: 16px; font-weight: 600; gap: 8px; }
.code-editor :deep(textarea) { font-family: 'Menlo', 'Monaco', 'Courier New', monospace; font-size: 13px; line-height: 1.5; }
.test-run-output {
  background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 4px;
  font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-all;
  max-height: 320px; overflow-y: auto; margin: 0;
}
</style>
