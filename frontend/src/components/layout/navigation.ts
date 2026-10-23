import { FileText, FolderKanban, LayoutDashboard, MessageSquareText, Search, Settings, ShieldCheck, type LucideIcon } from 'lucide-react'

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
    items: [
      { to: '/app', label: 'Dashboard', icon: LayoutDashboard },
      { to: '/app/chat', label: 'Chat', icon: MessageSquareText, permission: 'chat:use' },
      { to: '/app/search', label: 'Search', icon: Search, permission: 'search:use' },
    ],
  },
  {
    label: 'Knowledge',
    items: [
      { to: '/app/documents', label: 'Documents', icon: FileText, permission: 'documents:read' },
      { to: '/app/collections', label: 'Collections', icon: FolderKanban, permission: 'collections:read' },
    ],
  },
  {
    label: 'Account',
    items: [
      { to: '/app/settings', label: 'Settings', icon: Settings },
      { to: '/app/admin', label: 'Organization', icon: ShieldCheck, permission: 'members:manage' },
    ],
  },
]
