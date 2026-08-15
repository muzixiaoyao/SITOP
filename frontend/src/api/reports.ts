import request from './request'

export interface DashboardStats {
  total_jobs: number
  recent_jobs: number
  success_count: number
  success_rate: number
  total_servers: number
  total_groups: number
  trend: { date: string; total: number; success: number }[]
  status_distribution: Record<string, number>
}

export interface AuditLogEntry {
  id: string
  username: string | null
  action: string
  resource_type: string
  resource_id: string
  details: Record<string, any>
  ip_address: string | null
  created_at: string
}

export interface ManagedUser {
  id: string
  username: string
  email: string
  role: string
  tenant: string
  tenant_name?: string
  is_active: boolean
  date_joined: string
}

export const statsApi = {
  dashboard() { return request.get<DashboardStats>('/stats/dashboard/') },
}

export const auditApi = {
  list(params?: { action?: string; resource_type?: string; page?: number }) {
    return request.get('/auth/audit-logs/', { params })
  },
}

export const userApi = {
  list() { return request.get<ManagedUser[]>('/auth/users/') },
  create(data: { username: string; password: string; role: string; tenant: string; email?: string }) {
    return request.post('/auth/users/', data)
  },
  update(id: string, data: Partial<ManagedUser>) { return request.patch(`/auth/users/${id}/`, data) },
  delete(id: string) { return request.delete(`/auth/users/${id}/`) },
}

export function downloadReport(jobId: string, format: 'csv' | 'pdf') {
  // Direct link download — browser handles the attachment
  const token = localStorage.getItem('access_token')
  const url = `/api/jobs/${jobId}/report/?format=${format}`
  return fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    .then((resp) => resp.blob())
    .then((blob) => {
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `sitop_report_${jobId}.${format}`
      a.click()
      URL.revokeObjectURL(a.href)
    })
}
