<template>
  <AppLayout>
    <div class="repo-page">
      <el-card>
        <template #header>
          <div class="page-header">
            <span>软件仓库</span>
            <div class="header-actions">
              <el-input v-model="searchQuery" clearable size="small" placeholder="搜索当前目录" style="width: 200px">
                <template #prefix><el-icon><search /></el-icon></template>
              </el-input>
              <el-button size="small" @click="toggleHelp">使用说明</el-button>
              <el-button size="small" :loading="loading" @click="refresh">刷新</el-button>
              <el-button v-if="canWrite" type="primary" size="small" @click="openUpload">上传文件</el-button>
              <el-button v-if="canDelete" type="danger" size="small" :disabled="!selectedRows.length" @click="batchDelete">批量删除</el-button>
            </div>
          </div>
        </template>

        <el-alert v-if="showHelp" type="info" :closable="false" style="margin-bottom: 12px">
          <template #title>软件包变量使用说明</template>
          <p style="margin: 4px 0">1. 每个文件自动生成变量名：<code>PKG_</code> + 文件名大写 + 非字母数字转下划线，如 <code>mysql-8.0.26.tar.gz → PKG_MYSQL_8_0_26_TAR_GZ</code></p>
          <p style="margin: 4px 0">2. SITOP 执行脚本时自动注入这些变量（export），脚本里可直接使用：<code>curl -fsSL -O "$PKG_MYSQL_8_0_26_TAR_GZ"</code></p>
          <p style="margin: 4px 0">3. 脚本编辑器中可使用"插入软件包"按钮一键插入下载命令</p>
          <p style="margin: 4px 0">4. 删除需管理员权限；删除为不可恢复操作，界面会二次确认</p>
        </el-alert>

        <el-breadcrumb separator="/" style="margin-bottom: 12px">
          <el-breadcrumb-item><a @click.prevent="navigate('')">仓库根目录</a></el-breadcrumb-item>
          <el-breadcrumb-item v-for="(seg, idx) in pathSegments" :key="idx">
            <a @click.prevent="navigate(segmentsUpTo(idx))">{{ seg }}</a>
          </el-breadcrumb-item>
        </el-breadcrumb>

        <el-table :data="filteredFiles" stripe v-loading="loading" empty-text="仓库为空（无文件）" @selection-change="(rows: RepoItem[]) => selectedRows = rows">
          <el-table-column v-if="canDelete" type="selection" width="42" />
          <el-table-column label="名称" min-width="240" sortable="custom" @sort-change="() => toggleSort('name')">
            <template #default="{ row }">
              <el-button link type="primary" @click="enterDir(row)" v-if="row.is_dir">
                <el-icon><folder /></el-icon> {{ row.name }}
              </el-button>
              <span v-else><el-icon><component :is="fileIcon(row)" /></el-icon> {{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="大小" width="110" sortable="custom" @sort-change="() => toggleSort('size')">
            <template #default="{ row }">{{ row.is_dir ? '-' : formatSize(row.size) }}</template>
          </el-table-column>
          <el-table-column label="变量名" min-width="260">
            <template #default="{ row }">
              <span v-if="!row.is_dir" style="font-family: monospace">{{ row.variable }}</span>
            </template>
          </el-table-column>
          <el-table-column label="修改时间" width="170" sortable="custom" @sort-change="() => toggleSort('mtime')">
            <template #default="{ row }">{{ formatTime(row.mtime) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <template v-if="!row.is_dir">
                <el-button size="small" link type="primary" @click="copyVariable(row)">复制变量</el-button>
                <el-button size="small" link type="success" @click="downloadFile(row)">下载</el-button>
              </template>
              <el-button v-if="canDelete" size="small" link type="danger" @click="deleteFile(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-dialog v-model="showUploadDialog" title="上传文件" width="560px" @close="resetUpload">
        <el-alert :title="`上传到：/${currentPath}`" type="info" :closable="false" style="margin-bottom: 12px" />
        <el-upload
          drag multiple :auto-upload="false" :on-change="onFileChange" :on-remove="onFileRemove"
          :file-list="uploadFileList"
        >
          <el-icon class="el-icon--upload"><upload-filled /></el-icon>
          <div class="el-upload__text">将文件拖到此处，或<em>点击选择</em></div>
          <template #tip><div class="el-upload__tip">同名文件将自动重命名为 name(1).ext；单文件最大 1GB</div></template>
        </el-upload>
        <template #footer>
          <el-button @click="closeUploadDialog">取消</el-button>
          <el-button type="primary" :loading="uploading" :disabled="uploadFiles.length === 0" @click="doUpload">
            上传 ({{ uploadFiles.length }})
          </el-button>
        </template>
      </el-dialog>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Folder, UploadFilled, Search } from '@element-plus/icons-vue'
import AppLayout from '@/components/AppLayout.vue'
import { repositoryApi, listFilesDirect, type RepoItem } from '@/api/repository'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const canWrite = computed(() => ['admin', 'operator'].includes(auth.user?.role || ''))
// 删除仅管理员（比上传更严格）
const canDelete = computed(() => auth.user?.role === 'admin')
const selectedRows = ref<RepoItem[]>([])
const loading = ref(false)
const currentPath = ref('')
const files = ref<RepoItem[]>([])
const rootPath = ref('/data/initpackages')
const showHelp = ref(false)
const pathSegments = computed(() => currentPath.value.split('/').filter(Boolean))

// 搜索/排序/目录缓存
const searchQuery = ref('')
const sortKey = ref<'name' | 'size' | 'mtime'>('name')
const sortAsc = ref(true)
const dirCache = new Map<string, RepoItem[]>()

const filteredFiles = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  let list = files.value
  if (q) list = list.filter((f) => f.name.toLowerCase().includes(q))
  const dir = sortAsc.value ? 1 : -1
  return [...list].sort((a, b) => {
    if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1
    if (sortKey.value === 'size') return (a.size - b.size) * dir
    if (sortKey.value === 'mtime') return (a.mtime - b.mtime) * dir
    return a.name.localeCompare(b.name) * dir
  })
})

function toggleSort(key: 'name' | 'size' | 'mtime') {
  if (sortKey.value === key) sortAsc.value = !sortAsc.value
  else { sortKey.value = key; sortAsc.value = true }
}

function fileIcon(row: RepoItem) {
  if (row.is_dir) return 'folder'
  if (/\.(tar|gz|tgz|zip|rar|7z|xz)$/i.test(row.name)) return 'box'
  if (/\.(sh|py|txt|conf|cfg|json|yaml|yml|md)$/i.test(row.name)) return 'document'
  return 'document'
}

const showUploadDialog = ref(false)
const uploadFileList = ref<any[]>([])
const uploadFiles = ref<File[]>([])
const uploading = ref(false)

onMounted(loadFiles)

async function loadFiles(force = false) {
  loading.value = true
  try {
    // 目录缓存命中（非强制）直接返回
    if (!force && dirCache.has(currentPath.value)) {
      files.value = dirCache.get(currentPath.value)!
      return
    }
    let items: RepoItem[] | null = null
    try {
      // 优先浏览器直连仓库 nginx JSON
      items = await listFilesDirect(currentPath.value)
    } catch {
      // 直连失败：回退后端 API
      const { data } = await repositoryApi.listFiles(currentPath.value)
      items = data.items || []
      if (data.root_path) rootPath.value = data.root_path
    }
    files.value = items
    dirCache.set(currentPath.value, items)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '仓库加载失败')
  } finally { loading.value = false }
}

function refresh() {
  loadFiles(true)
}

function navigate(path: string) {
  currentPath.value = path
  loadFiles()
}

function segmentsUpTo(idx: number) {
  return pathSegments.value.slice(0, idx + 1).join('/')
}

function enterDir(row: RepoItem) {
  navigate(row.rel_path)
}

function formatSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  if (size < 1024 * 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  return `${(size / 1024 / 1024 / 1024).toFixed(2)} GB`
}

function formatTime(mtime: number) {
  return new Date(mtime * 1000).toLocaleString()
}

async function copyText(text: string, label?: string) {
  // HTTPS 环境可用的 clipboard API
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      ElMessage.success(label ? `已复制 ${label}` : `已复制`)
      return
    } catch {}
  }
  // HTTP 环境：textArea + execCommand 回退
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    if (document.execCommand('copy')) {
      ElMessage.success(label ? `已复制 ${label}` : `已复制`)
      document.body.removeChild(ta)
      return
    }
    document.body.removeChild(ta)
  } catch {}
  ElMessage.error('复制失败，请手动复制')
}

async function copyVariable(row: RepoItem) {
  await copyText(row.variable, row.variable)
}

async function downloadFile(row: RepoItem) {
  // 优先 HTTP 直链（HEAD 预检可达性），失败回退后端代理下载
  try {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 5000)
    const head = await fetch(row.http_url, { method: 'HEAD', mode: 'no-cors', signal: controller.signal })
    clearTimeout(timer)
    // no-cors 下无法读状态码：opaque 响应 = 请求已到达服务器
    if (head.type === 'opaque' || head.ok) {
      const a = document.createElement('a')
      a.href = row.http_url
      a.target = '_blank'
      a.rel = 'noopener'
      a.click()
      return
    }
  } catch {
    // 直链不可达，走代理
  }
  await proxyDownload(row)
}

async function proxyDownload(row: RepoItem) {
  try {
    const { data } = await repositoryApi.download(row.rel_path)
    const blob = new Blob([data])
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = row.name
    a.click()
    // 延迟释放，避免 Safari 下载中断
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '下载失败')
  }
}

async function deleteFile(row: RepoItem) {
  // 二次确认：删除不可恢复
  try {
    await ElMessageBox.confirm(
      `确定删除 ${row.name} 吗？此操作不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch { return }
  try {
    const { data } = await repositoryApi.deleteFiles([row.rel_path])
    if (data.errors?.length) {
      ElMessage.warning(`已删除 ${data.deleted.length} 个，${data.errors.length} 个失败：${data.errors[0].error}`)
    } else {
      ElMessage.success(`已删除 ${row.name}`)
    }
    dirCache.delete(currentPath.value)
    await loadFiles(true)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

async function batchDelete() {
  if (!selectedRows.value.length) return
  const names = selectedRows.value.slice(0, 5).map((r) => r.name).join('、')
  const more = selectedRows.value.length > 5 ? ` 等 ${selectedRows.value.length} 项` : ''
  // 二次确认：列出数量与部分名称
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${selectedRows.value.length} 个文件/目录吗？此操作不可恢复。\n\n${names}${more}`,
      '批量删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch { return }
  try {
    const { data } = await repositoryApi.deleteFiles(selectedRows.value.map((r) => r.rel_path))
    if (data.errors?.length) {
      ElMessage.warning(`已删除 ${data.deleted.length} 个，${data.errors.length} 个失败`)
    } else {
      ElMessage.success(`已删除 ${data.deleted.length} 个`)
    }
    selectedRows.value = []
    dirCache.delete(currentPath.value)
    await loadFiles(true)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '批量删除失败')
  }
}

function openUpload() {
  uploadFileList.value = []
  uploadFiles.value = []
  showUploadDialog.value = true
}

function closeUploadDialog() {
  showUploadDialog.value = false
}

function resetUpload() {
  uploadFileList.value = []
  uploadFiles.value = []
}

function onFileChange(file: any) {
  if (file.raw) uploadFiles.value.push(file.raw)
}

function onFileRemove(file: any) {
  uploadFiles.value = uploadFiles.value.filter((f) => f !== file.raw)
}

async function doUpload() {
  if (uploadFiles.value.length === 0) return
  uploading.value = true
  try {
    const { data } = await repositoryApi.uploadFiles(currentPath.value, uploadFiles.value)
    const renamed = data.results.filter((r) => r.saved_name !== r.original_name)
    if (renamed.length > 0) {
      ElMessage.warning(`同名文件已自动重命名: ${renamed.map((r) => `${r.original_name} → ${r.saved_name}`).join(', ')}`)
    }
    if (data.errors.length > 0) {
      ElMessage.warning(`${data.results.length} 个成功，${data.errors.length} 个失败: ${data.errors[0].error}`)
    } else {
      ElMessage.success(`上传成功 ${data.results.length} 个文件`)
    }
    closeUploadDialog()
    dirCache.delete(currentPath.value)
    await loadFiles(true)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '上传失败')
  } finally { uploading.value = false }
}

function toggleHelp() {
  showHelp.value = !showHelp.value
}
</script>

<style scoped>
.repo-page { padding: 16px; }
.page-header { display: flex; justify-content: space-between; align-items: center; font-size: 16px; font-weight: 600; gap: 8px; }
.header-actions { display: flex; gap: 8px; align-items: center; }
</style>
