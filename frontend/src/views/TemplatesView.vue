<template>
  <AppLayout>
    <div class="templates-page">
      <el-card>
        <template #header>
          <div class="page-header">
            <span>模板管理</span>
            <el-button type="primary" @click="showCreateDialog = true">新建模板</el-button>
          </div>
        </template>
        <el-table empty-text="暂无数据" :data="templates" stripe v-loading="loading">
          <el-table-column prop="name" label="名称" width="200" />
          <el-table-column prop="description" label="描述" />
          <el-table-column label="健康检查" width="120">
            <template #default="{ row }">{{ row.health_check_script_name || '-' }}</template>
          </el-table-column>
          <el-table-column label="步骤数" width="80">
            <template #default="{ row }">{{ (row.steps || []).length }}</template>
          </el-table-column>
          <el-table-column label="完成度检查" width="120">
            <template #default="{ row }">{{ row.completion_check_script_name || '-' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="140">
            <template #default="{ row }">
              <el-button type="primary" size="small" link @click="editTemplate(row)">编辑</el-button>
              <el-button type="danger" size="small" link @click="deleteTemplate(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-dialog v-model="showCreateDialog" :title="editingId ? '编辑模板' : '新建模板'" width="900px" top="3vh">
        <el-form :model="form" label-width="100px">
          <el-form-item label="名称" required>
            <el-input v-model="form.name" />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="form.description" type="textarea" :rows="2" />
          </el-form-item>
          <el-form-item label="健康检查脚本">
            <el-select v-model="form.health_check_script" clearable placeholder="选择健康检查脚本" style="width: 100%">
              <el-option v-for="s in healthScripts" :key="s.id" :label="s.name" :value="s.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="完成度检查脚本">
            <el-select v-model="form.completion_check_script" clearable placeholder="选择完成度检查脚本" style="width: 100%">
              <el-option v-for="s in completionScripts" :key="s.id" :label="s.name" :value="s.id" />
            </el-select>
          </el-form-item>

          <el-divider content-position="left">初始化步骤</el-divider>
          <div class="steps-container">
            <div v-for="(step, idx) in form.steps" :key="idx" class="step-row">
              <el-tag type="info" class="step-order">步骤 {{ idx + 1 }}</el-tag>
              <el-select v-model="step.script" placeholder="选择脚本" style="flex: 1" @change="onStepScriptChange(idx)">
                <el-option v-for="s in initScripts" :key="s.id" :label="s.name" :value="s.id" />
              </el-select>
              <el-input-number v-model="step.timeout_seconds" :min="10" :max="3600" :step="30" size="small" style="width: 120px" />
              <el-select v-model="step.on_failure" size="small" style="width: 100px">
                <el-option label="中断" value="abort" />
                <el-option label="继续" value="continue" />
                <el-option label="重试" value="retry" />
              </el-select>
              <el-button type="danger" size="small" circle @click="removeStep(idx)" :disabled="form.steps.length <= 1">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </div>
          <el-button type="primary" plain size="small" @click="addStep" style="margin-top: 8px">+ 添加步骤</el-button>
        </el-form>
        <template #footer>
          <el-button @click="showCreateDialog = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveTemplate">保存</el-button>
        </template>
      </el-dialog>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import AppLayout from '@/components/AppLayout.vue'
import { templateApi, scriptApi, type InitTemplate, type TemplateStep, type Script } from '@/api/tasks'

const templates = ref<InitTemplate[]>([])
const allScripts = ref<Script[]>([])
const loading = ref(false)
const saving = ref(false)
const showCreateDialog = ref(false)
const editingId = ref<string | null>(null)

const form = reactive({
  name: '',
  description: '',
  health_check_script: null as string | null,
  completion_check_script: null as string | null,
  steps: [{ step_order: 1, script: '', parameters: {}, timeout_seconds: 60, on_failure: 'abort' as const, max_retries: 3 }] as TemplateStep[],
})

const healthScripts = computed(() => allScripts.value.filter(s => s.script_type === 'health_check'))
const initScripts = computed(() => allScripts.value.filter(s => s.script_type === 'init_step'))
const completionScripts = computed(() => allScripts.value.filter(s => s.script_type === 'completion_check'))

onMounted(async () => {
  await Promise.all([loadTemplates(), loadScripts()])
})

async function loadTemplates() {
  loading.value = true
  try {
    const { data } = await templateApi.list()
    templates.value = Array.isArray(data) ? data : (data as any).results || []
  } finally { loading.value = false }
}

async function loadScripts() {
  const { data } = await scriptApi.list()
  allScripts.value = Array.isArray(data) ? data : (data as any).results || []
}

function addStep() {
  form.steps.push({ step_order: form.steps.length + 1, script: '', parameters: {}, timeout_seconds: 60, on_failure: 'abort', max_retries: 3 })
}

function removeStep(idx: number) {
  form.steps.splice(idx, 1)
  form.steps.forEach((s, i) => s.step_order = i + 1)
}

function onStepScriptChange(_idx: number) {
  // Auto-set timeout based on script
}

function editTemplate(t: InitTemplate) {
  editingId.value = t.id
  form.name = t.name
  form.description = t.description
  form.health_check_script = t.health_check_script
  form.completion_check_script = t.completion_check_script
  form.steps = t.steps.length > 0
    ? t.steps.map(s => ({ ...s }))
    : [{ step_order: 1, script: '', parameters: {}, timeout_seconds: 60, on_failure: 'abort', max_retries: 3 }]
  showCreateDialog.value = true
}

async function saveTemplate() {
  if (!form.name) { ElMessage.warning('请输入模板名称'); return }
  if (form.steps.some(s => !s.script)) { ElMessage.warning('请为所有步骤选择脚本'); return }
  saving.value = true
  try {
    const payload = {
      name: form.name,
      description: form.description,
      health_check_script: form.health_check_script,
      completion_check_script: form.completion_check_script,
      steps: form.steps.map((s, i) => ({ ...s, step_order: i + 1 })),
    }
    if (editingId.value) {
      await templateApi.update(editingId.value, payload)
      ElMessage.success('模板已更新')
    } else {
      await templateApi.create(payload)
      ElMessage.success('模板已创建')
    }
    showCreateDialog.value = false; editingId.value = null
    resetForm(); await loadTemplates()
  } finally { saving.value = false }
}

async function deleteTemplate(id: string) {
  await ElMessageBox.confirm('确定删除此模板？')
  await templateApi.delete(id)
  ElMessage.success('已删除'); await loadTemplates()
}

function resetForm() {
  form.name = ''; form.description = ''
  form.health_check_script = null; form.completion_check_script = null
  form.steps = [{ step_order: 1, script: '', parameters: {}, timeout_seconds: 60, on_failure: 'abort', max_retries: 3 }]
}
</script>

<style scoped>
.templates-page { padding: 16px; }
.page-header { display: flex; justify-content: space-between; align-items: center; font-size: 16px; font-weight: 600; gap: 8px; }
.steps-container { display: flex; flex-direction: column; gap: 8px; }
.step-row { display: flex; align-items: center; gap: 8px; }
.step-order { width: 60px; text-align: center; flex-shrink: 0; }
</style>
