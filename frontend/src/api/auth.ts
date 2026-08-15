import request from './request'

export interface LoginParams {
  username: string
  password: string
}

export interface TokenResponse {
  access: string
  refresh: string
}

export interface UserInfo {
  id: string
  username: string
  email: string
  role: string
  tenant: {
    id: string
    name: string
    status: string
  }
}

export interface SSHCredential {
  id: string
  name: string
  auth_type: 'password' | 'key' | 'key_with_passphrase' | 'token'
  username: string
  use_ssh_agent: boolean
  jump_host: string
  jump_port: number
  jump_username: string
  connect_timeout: number
  created_at: string
  updated_at: string
}

export interface SSHCredentialInput {
  name: string
  auth_type: SSHCredential['auth_type']
  username: string
  password?: string
  private_key_content?: string
  passphrase_content?: string
  token_content?: string
  use_ssh_agent?: boolean
  jump_host?: string
  jump_port?: number
  jump_username?: string
  connect_timeout?: number
}

export const authApi = {
  login(data: LoginParams) {
    return request.post<TokenResponse>('/auth/login/', data)
  },
  refresh(data: { refresh: string }) {
    return request.post<TokenResponse>('/auth/refresh/', data)
  },
  getMe() {
    return request.get<UserInfo>('/auth/me/')
  },
  // SSH Credentials
  listCredentials() {
    return request.get<SSHCredential[]>('/auth/credentials/')
  },
  createCredential(data: SSHCredentialInput) {
    return request.post<SSHCredential>('/auth/credentials/', data)
  },
  updateCredential(id: string, data: Partial<SSHCredentialInput>) {
    return request.put<SSHCredential>(`/auth/credentials/${id}/`, data)
  },
  deleteCredential(id: string) {
    return request.delete(`/auth/credentials/${id}/`)
  },
}
