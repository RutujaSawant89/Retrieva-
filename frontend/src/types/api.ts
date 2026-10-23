/* Types mirroring backend/app/schemas. Keep in sync with the OpenAPI spec (/api/openapi.json). */

export type RoleName = 'admin' | 'analyst' | 'researcher' | 'viewer'

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface UserOut {
  id: string
  email: string
  full_name: string
  created_at: string
  last_login_at: string | null
}

export interface OrganizationSummary {
  id: string
  name: string
  slug: string
  role: RoleName
}

export interface SessionOut {
  access_token: string
  token_type: string
  expires_at: string
  user: UserOut
  organization: OrganizationSummary
  organizations: OrganizationSummary[]
  permissions: string[]
}

export interface MessageOut {
  message: string
}

export interface MemberOut {
  user_id: string
  email: string
  full_name: string
  role: RoleName
  is_active: boolean
  joined_at: string
  last_login_at: string | null
}

export interface InvitationOut {
  id: string
  email: string
  role: RoleName
  expires_at: string
  accepted_at: string | null
  created_at: string
  token: string | null
}

export interface AuditLogOut {
  id: string
  user_id: string | null
  user_email: string | null
  action: string
  resource_type: string | null
  resource_id: string | null
  ip_address: string | null
  correlation_id: string | null
  details: Record<string, unknown>
  created_at: string
}

export interface RoleOut {
  name: RoleName
  description: string
  permissions: string[]
}

export interface OrganizationOut {
  id: string
  name: string
  slug: string
  created_at: string
}
