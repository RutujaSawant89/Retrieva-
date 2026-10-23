import { LayoutDashboard, Settings, ShieldCheck, type LucideIcon } from 'lucide-react'

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  /** Permission required to see the entry (all entries require authentication). */
  permission?: string
}

export interface NavSection {
  label: string
  items: NavItem[]
}

export const NAVIGATION: NavSection[] = [
  {
    label: 'Workspace',
    items: [{ to: '/app', label: 'Dashboard', icon: LayoutDashboard }],
  },
  {
    label: 'Account',
    items: [
      { to: '/app/settings', label: 'Settings', icon: Settings },
      { to: '/app/admin', label: 'Organization', icon: ShieldCheck, permission: 'members:manage' },
    ],
  },
]
