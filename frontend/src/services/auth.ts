import type { MessageOut, SessionOut, UserOut } from '@/types/api'

import { http, request } from './http'

export interface RegisterInput {
  email: string
  full_name: string
  password: string
  organization_name?: string
  invitation_token?: string
}

export const authApi = {
  register: (input: RegisterInput) =>
    request<SessionOut>('/auth/register', { method: 'POST', body: input, noRetry: true }),
  login: (email: string, password: string, organization_id?: string) =>
    request<SessionOut>('/auth/login', { method: 'POST', body: { email, password, organization_id }, noRetry: true }),
  refresh: () => request<SessionOut>('/auth/refresh', { method: 'POST', noRetry: true }),
  switchOrganization: (organization_id: string) =>
    request<SessionOut>('/auth/switch-organization', { method: 'POST', body: { organization_id }, noRetry: true }),
  logout: () => request<MessageOut>('/auth/logout', { method: 'POST', noRetry: true }),
  updateProfile: (full_name: string) => http.patch<UserOut>('/auth/me', { full_name }),
  changePassword: (current_password: string, new_password: string) =>
    http.post<MessageOut>('/auth/me/password', { current_password, new_password }),
}
