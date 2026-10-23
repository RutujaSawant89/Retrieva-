import type {
  AuditLogOut,
  InvitationOut,
  MemberOut,
  MessageOut,
  OrganizationOut,
  Page,
  RoleName,
  RoleOut,
} from '@/types/api'

import { http } from './http'

export const adminApi = {
  organization: () => http.get<OrganizationOut>('/admin/organization'),
  renameOrganization: (name: string) => http.patch<OrganizationOut>('/admin/organization', { name }),
  roles: () => http.get<RoleOut[]>('/admin/roles'),
  users: (params: { page?: number; q?: string }) => http.get<Page<MemberOut>>('/admin/users', params),
  setRole: (userId: string, role: RoleName) => http.patch<MessageOut>(`/admin/users/${userId}`, { role }),
  removeMember: (userId: string) => http.delete<MessageOut>(`/admin/users/${userId}`),
  invitations: () => http.get<InvitationOut[]>('/admin/invitations'),
  invite: (email: string, role: RoleName) => http.post<InvitationOut>('/admin/invitations', { email, role }),
  revokeInvitation: (id: string) => http.delete<MessageOut>(`/admin/invitations/${id}`),
  auditLogs: (params: { page?: number; action?: string }) => http.get<Page<AuditLogOut>>('/admin/audit-logs', params),
}
