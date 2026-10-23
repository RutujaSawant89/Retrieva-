import {
  BarChart3,
  FileSearch,
  FileText,
  FlaskConical,
  FolderKanban,
  GitCompareArrows,
  LayoutDashboard,
  MessageSquareText,
  Search,
  Settings,
  ShieldCheck,
  type LucideIcon,
} from 'lucide-react'

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
      { to: '/app/research', label: 'Research', icon: FileSearch, permission: 'research:use' },
      { to: '/app/compare', label: 'Compare', icon: GitCompareArrows, permission: 'documents:read' },
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
    label: 'Insights',
    items: [
      { to: '/app/analytics', label: 'Analytics', icon: BarChart3, permission: 'analytics:read' },
      { to: '/app/evaluation', label: 'Evaluation', icon: FlaskConical, permission: 'evaluation:read' },
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
