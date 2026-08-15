<template>
  <AppLayout>
    <div class="users-page">
      <el-card>
        <template #header>
          <div class="page-header">
            <span>用户管理</span>
            <el-button type="primary" @click="showCreate = true">新建用户</el-button>
          </div>
        </template>
        <el-table empty-text="暂无数据" :data="users" stripe v-loading="loading">
          <el-table-column prop="username" label="用户名" width="160" />
          <el-table-column prop="email" label="邮箱" width="220" />
          <el-table-column prop="role" label="角色" width="140">
            <template #default="{ row }">
              <el-select v-model="row.role" size="small" style="width: 110px" @change="updateRole(row)">
                <el-option label="管理员" value="admin" />
                <el-option label="操作员" value="operator" />
                <el-option label="只读" value="viewer" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column prop="is_active" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '禁用' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="date_joined" label="加入时间">
            <template #default="{ row }">{{ formatDate(row.date_joined) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button type="danger" size="small" link @click="removeUser(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-dialog v-model="showCreate" title="新建用户" width="460px">
        <el-form :model="form" label-width="100px">
          <el-form-item label="用户名" required><el-input v-model="form.username" /></el-form-item>
          <el-form-item label="密码" required><el-input v-model="form.password" type="password" show-password /></el-form-item>
          <el-form-item label="邮箱"><el-input v-model="form.email" /></el-form-item>
          <el-form-item label="角色">
            <el-select v-model="form.role" style="width: 100%">
              <el-option label="管理员" value="admin" />
              <el-option label="操作员" value="operator" />
              <el-option label="只读" value="viewer" />
            </el-select>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showCreate = false">取消</el-button>
          <el-button type="primary" :loading="creating" @click="createUser">创建</el-button>
        </template>
      </el-dialog>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '@/components/AppLayout.vue'
import { userApi, type ManagedUser } from '@/api/reports'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const users = ref<ManagedUser[]>([])
const loading = ref(false)
const showCreate = ref(false)
const creating = ref(false)
const form = reactive({ username: '', password: '', email: '', role: 'operator' })

onMounted(() => load())

async function load() {
  loading.value = true
  try {
    const { data } = await userApi.list()
    users.value = Array.isArray(data) ? data : (data as any).results || []
  } finally { loading.value = false }
}

async function createUser() {
  if (!form.username || !form.password) { ElMessage.warning('请填写用户名和密码'); return }
  creating.value = true
  try {
    await userApi.create({ ...form, tenant: auth.user?.tenant.id || '' })
    ElMessage.success('用户创建成功')
    showCreate.value = false
    form.username = ''; form.password = ''; form.email = ''; form.role = 'operator'
    await load()
  } finally { creating.value = false }
}

async function updateRole(row: ManagedUser) {
  await userApi.update(row.id, { role: row.role })
  ElMessage.success('角色已更新')
}

async function removeUser(row: ManagedUser) {
  await ElMessageBox.confirm(`确定删除用户 ${row.username}？`)
  await userApi.delete(row.id)
  ElMessage.success('已删除')
  await load()
}

function formatDate(d: string) { return new Date(d).toLocaleString('zh-CN') }
</script>

<style scoped>
.users-page { padding: 16px; }
.page-header { display: flex; justify-content: space-between; align-items: center; font-size: 16px; font-weight: 600; gap: 8px; }
</style>
