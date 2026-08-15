<template>
  <div class="login-container">
    <div class="login-panel">
      <div class="login-header">
        <h1 class="logo">智枢 SITOP</h1>
        <p class="subtitle">服务器智能任务编排平台</p>
      </div>
      <el-form
        :model="form"
        :rules="rules"
        ref="formRef"
        label-position="top"
        class="login-form"
        @submit.prevent="handleLogin"
      >
        <el-form-item prop="username" label="用户名">
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            size="large"
            :prefix-icon="User"
          />
        </el-form-item>
        <el-form-item prop="password" label="密码">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            size="large"
            :prefix-icon="Lock"
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            size="large"
            class="login-btn"
            :loading="loading"
            @click="handleLogin"
          >
            登 录
          </el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const formRef = ref<FormInstance>()
const loading = ref(false)

const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid: boolean) => {
    if (!valid) return
    loading.value = true
    try {
      await auth.login(form.username, form.password)
      ElMessage.success('登录成功')
      router.push('/dashboard')
    } catch (e: any) {
      ElMessage.error(e.response?.data?.detail || '登录失败')
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-right: 8%;
  background: url('/bg-tunnel.jpg') center/cover no-repeat;
  position: relative;
}

.login-container::before {
  content: '';
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
}

.login-panel {
  position: relative;
  z-index: 1;
  width: 420px;
  padding: 48px 40px 40px;
  background: rgba(15, 20, 35, 0.65);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.login-header {
  text-align: center;
  margin-bottom: 36px;
}

.logo {
  margin: 0 0 8px;
  font-size: 28px;
  font-weight: 600;
  color: #fff;
  letter-spacing: 2px;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.subtitle {
  margin: 0;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.8);
  letter-spacing: 1px;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.2);
}

.login-form :deep(.el-form-item__label) {
  color: rgba(255, 255, 255, 0.7);
  font-size: 14px;
  padding-bottom: 8px;
}

.login-form :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.08);
  box-shadow: none;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  padding: 10px 14px;
}

.login-form :deep(.el-input__wrapper:hover) {
  border-color: rgba(64, 158, 255, 0.5);
}

.login-form :deep(.el-input__wrapper.is-focus) {
  border-color: #409eff;
  background: rgba(255, 255, 255, 0.12);
}

.login-form :deep(.el-input__inner) {
  color: #fff;
}

.login-form :deep(.el-input__inner::placeholder) {
  color: rgba(255, 255, 255, 0.3);
}

.login-form :deep(.el-input__prefix) {
  color: rgba(255, 255, 255, 0.4);
}

.login-btn {
  width: 100%;
  margin-top: 8px;
  height: 44px;
  font-size: 16px;
  letter-spacing: 4px;
  border-radius: 6px;
}
</style>
