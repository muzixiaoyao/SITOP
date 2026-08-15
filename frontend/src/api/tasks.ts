import request from './request'

export interface Script {
  id: string
  name: string
  description: string
  script_type: 'health_check' | 'init_step' | 'completion_check'
  language: 'shell' | 'python'
  content: string
  version: number
  parameter_schema: Record<string, any>
  created_at: string
  updated_at: string
}

export interface TemplateStep {
  id?: string
  step_order: number
  script: string
  script_name?: string
  parameters: Record<string, any>
  timeout_seconds: number
  on_failure: 'abort' | 'continue' | 'retry'
  max_retries: number
}

export interface InitTemplate {
  id: string
  name: string
  description: string
  health_check_script: string | null
  health_check_script_name: string | null
  completion_check_script: string | null
  completion_check_script_name: string | null
  steps: TemplateStep[]
  created_at: string
  updated_at: string
}

export interface StepLog {
  id: string
  phase: string
  step_order: number | null
  script_name: string
  output: string
  error: string
  exit_code: number | null
  status: string
  started_at: string
  ended_at: string | null
}

export interface ServerTask {
  id: string
  server: string
  hostname: string
  ip: string
  status: string
  current_step: number
  connectivity_result: Record<string, any>
  health_result: Record<string, any>
  completion_result: Record<string, any>
  start_time: string | null
  end_time: string | null
  step_logs: StepLog[]
}

export interface InitJob {
  id: string
  template: string
  template_name: string
  group: string
  group_name: string
  status: string
  current_phase: string
  summary: Record<string, number>
  total_servers: number
  completed_servers: number
  start_time: string | null
  end_time: string | null
  created_at: string
  server_tasks?: ServerTask[]
}

export const scriptApi = {
  list(scriptType?: string) {
    return request.get<Script[]>('/scripts/', { params: scriptType ? { script_type: scriptType } : {} })
  },
  create(data: Partial<Script>) { return request.post<Script>('/scripts/', data) },
  get(id: string) { return request.get<Script>(`/scripts/${id}/`) },
  update(id: string, data: Partial<Script>) { return request.put<Script>(`/scripts/${id}/`, data) },
  delete(id: string) { return request.delete(`/scripts/${id}/`) },
  versions(id: string) { return request.get<ScriptVersion[]>(`/scripts/${id}/versions/`) },
  testRun(id: string, data: { server_id: string; content?: string }) {
    return request.post<{ exit_code: number; output: string; error: string }>(`/scripts/${id}/test-run/`, data)
  },
}

export interface ScriptVersion {
  id: string
  version: number
  content: string
  created_at: string
}

export const templateApi = {
  list() { return request.get<InitTemplate[]>('/templates/') },
  create(data: Partial<InitTemplate>) { return request.post<InitTemplate>('/templates/', data) },
  get(id: string) { return request.get<InitTemplate>(`/templates/${id}/`) },
  update(id: string, data: Partial<InitTemplate>) { return request.put<InitTemplate>(`/templates/${id}/`, data) },
  delete(id: string) { return request.delete(`/templates/${id}/`) },
}

export const jobApi = {
  list() { return request.get<InitJob[]>('/jobs/') },
  create(data: { template: string; group: string }) { return request.post<InitJob>('/jobs/', data) },
  get(id: string) { return request.get<InitJob>(`/jobs/${id}/`) },
  cancel(id: string) { return request.post(`/jobs/${id}/cancel/`) },
  completionMatrix(id: string) {
    return request.get<CompletionMatrix>(`/jobs/${id}/completion-matrix/`)
  },
}

export interface CompletionMatrix {
  step_names: string[]
  rows: {
    server_id: string
    hostname: string
    ip: string
    task_status: string
    steps: Record<string, string>
  }[]
}

/** Subscribe to real-time job updates via WebSocket. Returns an unsubscribe function. */
export function subscribeJob(jobId: string, onEvent: (evt: { job_id: string; event: string; payload: any }) => void): () => void {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  let ws: WebSocket | null = null
  try {
    ws = new WebSocket(`${proto}://${location.host}/ws/jobs/${jobId}/`)
    ws.onmessage = (msg) => {
      try { onEvent(JSON.parse(msg.data)) } catch { /* ignore malformed */ }
    }
  } catch {
    /* WebSocket unavailable — caller falls back to polling */
  }
  return () => {
    closed = true
    ws?.close()
  }
}
