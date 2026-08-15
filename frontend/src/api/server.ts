import request from './request'

export interface ServerGroupBrief {
  id: string
  name: string
  description: string
}

export interface ServerGroup {
  id: string
  name: string
  description: string
  server_count: number
  default_credential?: string | null
  auto_patrol?: boolean
  created_at: string
  updated_at: string
  servers?: Server[]
}

export interface Server {
  id: string
  hostname: string
  ip: string
  ssh_port: number
  protocol: 'ssh' | 'rdp' | 'telnet' | 'vnc'
  platform: 'linux' | 'windows' | 'unix' | 'network' | 'other'
  os_info: string
  connect_timeout: number
  exec_timeout: number
  ssh_options: Record<string, any>
  labels: string[]
  tags: string[]
  custom_fields: Record<string, any>
  comment: string
  ssh_credential: string | null
  connectivity_status: 'unknown' | 'success' | 'failed'
  last_check_time: string | null
  groups: ServerGroupBrief[]
  group_ids?: string[]
  created_at: string
  updated_at: string
}

export interface ConnectivityResult {
  server_id: string
  hostname: string
  ip: string
  status: 'success' | 'failed'
  message: string
  latency_ms: number | null
}

export interface CommandResult {
  server_id: string
  hostname: string
  exit_code: number
  output: string
  error: string
}

export interface BatchOperationResult {
  results?: any[]
  total?: number
  updated?: number
  deleted?: number
  created?: any[]
  errors?: any[]
}

export const serverApi = {
  listGroups() {
    return request.get<ServerGroup[]>('/groups/')
  },
  createGroup(data: { name: string; description: string; default_credential?: string | null; auto_patrol?: boolean }) {
    return request.post<ServerGroup>('/groups/', data)
  },
  getGroup(id: string) {
    return request.get<ServerGroup>(`/groups/${id}/`)
  },
  updateGroup(id: string, data: Partial<ServerGroup>) {
    return request.put<ServerGroup>(`/groups/${id}/`, data)
  },
  deleteGroup(id: string) {
    return request.delete(`/groups/${id}/`)
  },
  listServers(groupId: string) {
    return request.get<Server[]>(`/groups/${groupId}/servers/`, { params: { page_size: 999999 } })
  },
  listAllServers() {
    return request.get<Server[]>('/servers/', { params: { page_size: 999999 } })
  },
  getServer(id: string) {
    return request.get<Server>(`/servers/${id}/`)
  },
  updateServer(id: string, data: Partial<Server>) {
    return request.put<Server>(`/servers/${id}/`, data)
  },
  deleteServer(id: string) {
    return request.delete(`/servers/${id}/`)
  },
  batchCreateServers(groupId: string, servers: Partial<Server>[]) {
    return request.post<BatchOperationResult>(`/groups/${groupId}/servers/batch/`, { servers })
  },
  // Batch operations
  batchConnectivity(serverIds: string[]) {
    return request.post<BatchOperationResult>('/servers/batch/connectivity/', { server_ids: serverIds })
  },
  batchUpdateCredential(serverIds: string[], credentialId: string) {
    return request.post<BatchOperationResult>('/servers/batch/credential/', {
      server_ids: serverIds,
      credential_id: credentialId,
    })
  },
  batchDelete(serverIds: string[]) {
    return request.post<BatchOperationResult>('/servers/batch/delete/', { server_ids: serverIds })
  },
  // Batch group operations
  batchGroupMove(serverIds: string[], groupIds: string[]) {
    return request.post<BatchOperationResult>('/servers/batch/group-move/', {
      server_ids: serverIds,
      group_ids: groupIds,
    })
  },
  batchGroupAdd(serverIds: string[], groupIds: string[]) {
    return request.post<BatchOperationResult>('/servers/batch/group-add/', {
      server_ids: serverIds,
      group_ids: groupIds,
    })
  },
  // Import/Export
  importServers(groupId: string, file: File) {
    const formData = new FormData()
    formData.append('file', file)
    return request.post<BatchOperationResult>(`/groups/${groupId}/servers/import/`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  exportServers(groupId: string) {
    return request.get(`/groups/${groupId}/servers/export/`, { responseType: 'blob' })
  },
  // Connectivity & Commands
  checkConnectivity(groupId: string) {
    return request.post<ConnectivityResult[]>(`/groups/${groupId}/check-connectivity/`)
  },
  executeCommand(groupId: string, command: string) {
    return request.post<CommandResult[]>(`/groups/${groupId}/execute-command/`, { command })
  },
  // Patrol
  patrolGroup(groupId: string) {
    return request.post(`/groups/${groupId}/patrol/`)
  },
}
