import request from './request'

// 仓库 HTTP 直连地址（构建时注入；浏览器需可访问）
const REPO_HTTP_URL = (import.meta.env.VITE_REPO_HTTP_URL as string | undefined) || 'http://192.168.1.1:8081/'

interface NginxAutoIndexItem {
  name: string
  type: 'directory' | 'file'
  mtime: string
  size: number
}

/** 与后端 variable_name 规则一致：PKG_ + 相对路径大写化 + 非字母数字转下划线 */
export function variableName(relPath: string): string {
  return `PKG_${relPath.replace(/[^A-Za-z0-9]+/g, '_').replace(/^_+|_+$/g, '').toUpperCase()}`
}

/** 浏览器直连仓库 nginx JSON 列目录（5s 超时） */
export async function listFilesDirect(path = ''): Promise<RepoItem[]> {
  const base = REPO_HTTP_URL.replace(/\/+$/, '')
  const url = path ? `${base}/${path}/` : `${base}/`
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 5000)
  try {
    const resp = await fetch(url, { headers: { Accept: 'application/json' }, signal: controller.signal })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const raw = (await resp.json()) as NginxAutoIndexItem[]
    return raw
      .filter((i) => i.name !== '../')
      .map((i) => {
        const rel = path ? `${path}/${i.name}` : i.name
        return {
          name: i.name,
          rel_path: rel,
          is_dir: i.type === 'directory',
          size: i.size || 0,
          mtime: new Date(i.mtime).getTime() / 1000 || 0,
          variable: i.type === 'file' ? variableName(rel) : '',
          http_url: i.type === 'file' ? `${base}/${rel}` : '',
        } as RepoItem
      })
  } finally {
    clearTimeout(timer)
  }
}

export interface RepoItem {
  name: string
  rel_path: string
  is_dir: boolean
  size: number
  mtime: number
  variable: string
  http_url: string
}

export interface RepoFileList {
  path: string
  parent: string
  root_path?: string
  items: RepoItem[]
}

export interface UploadResult {
  original_name: string
  saved_name: string
  variable: string
  size: number
}

export const repositoryApi = {
  listFiles(path = '') {
    return request.get<RepoFileList>('/repository/files/', { params: { path } })
  },

  deleteFiles(paths: string[]) {
    return request.post<{ deleted: string[]; errors: { path: string; error: string }[] }>('/repository/files/delete/', { paths })
  },
  uploadFiles(path: string, files: File[]) {
    const formData = new FormData()
    files.forEach((f) => formData.append('files', f))
    return request.post<{ results: UploadResult[]; errors: any[] }>('/repository/files/upload/', formData, {
      params: { path },
    })
  },
  download(path: string) {
    return request.get('/repository/files/download/', { params: { path }, responseType: 'blob' })
  },
}
