import request from './request'

export interface Ticket {
  id: string
  ticket_no: string
  title: string
  description?: string
  type: 'fault' | 'request' | 'internal' | 'change'
  type_display: string
  priority: 'critical' | 'high' | 'medium' | 'low'
  priority_display: string
  status: string
  status_display: string
  submitter: string
  submitter_name: string
  assignee: string | null
  assignee_name: string
  current_node?: string
  current_node_name?: string
  related_job?: string | null
  first_response_at?: string
  assigned_at?: string
  resolved_at?: string
  closed_at?: string
  created_at: string
  updated_at: string
  comments?: TicketComment[]
  transitions?: TicketTransition[]
  sla_policy_detail?: SLAPolicy
}

export interface TicketComment {
  id: string
  author: string
  author_name: string
  content: string
  is_system: boolean
  created_at: string
}

export interface TicketTransition {
  id: string
  from_node: string | null
  from_node_name: string
  to_node: string | null
  to_node_name: string
  operator: string
  operator_name: string
  comment: string
  duration_seconds: number
  created_at: string
}

export interface SLAPolicy {
  id: string
  name: string
  priority: string
  response_minutes: number
  resolve_minutes: number
}

export interface TicketFlow {
  id: string
  name: string
  ticket_type: string
  is_active: boolean
  nodes: TicketFlowNode[]
  created_at: string
}

export interface TicketFlowNode {
  id: string
  name: string
  order: number
  role_required: string
  is_terminal: boolean
  sla_hours: number
  auto_assign_rule: string
}

export interface Notification {
  id: string
  type: string
  title: string
  content: string
  ticket: string | null
  is_read: boolean
  created_at: string
}

export const ticketsApi = {
  list(params?: { type?: string; status?: string; priority?: string; search?: string; page?: number }) {
    return request.get('/tickets/', { params })
  },
  get(id: string) {
    return request.get<Ticket>(`/tickets/${id}/`)
  },
  create(data: { title: string; description?: string; type: string; priority: string; related_job?: string }) {
    return request.post<Ticket>('/tickets/', data)
  },
  assign(id: string, assigneeId: string) {
    return request.post(`/tickets/${id}/assign/`, { assignee_id: assigneeId })
  },
  transition(id: string, nodeId: string, comment?: string) {
    return request.post(`/tickets/${id}/transition/`, { node_id: nodeId, comment })
  },
  resolve(id: string, resolution?: string) {
    return request.post(`/tickets/${id}/resolve/`, { resolution })
  },
  close(id: string) {
    return request.post(`/tickets/${id}/close/`)
  },
  cancel(id: string, reason?: string) {
    return request.post(`/tickets/${id}/cancel/`, { reason })
  },
  addComment(id: string, content: string) {
    return request.post(`/tickets/${id}/comments/`, { content })
  },
  getTransitions(id: string) {
    return request.get<TicketTransition[]>(`/tickets/${id}/transitions/`)
  },
  listFlows() {
    return request.get<TicketFlow[]>('/tickets/flows/')
  },
  createFlow(data: Partial<TicketFlow>) {
    return request.post('/tickets/flows/', data)
  },
  listSLAPolicies() {
    return request.get<SLAPolicy[]>('/tickets/sla-policies/')
  },
  createSLAPolicy(data: Partial<SLAPolicy>) {
    return request.post('/tickets/sla-policies/', data)
  },
}

export const notificationsApi = {
  list() {
    return request.get<Notification[]>('/notifications/')
  },
  markRead(id: string) {
    return request.post(`/notifications/${id}/read/`)
  },
  markAllRead() {
    return request.post('/notifications/read-all/')
  },
  unreadCount() {
    return request.get<{ count: number }>('/notifications/unread-count/')
  },
}
