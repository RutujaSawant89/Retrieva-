import {
  Activity,
  BarChart3,
  Building2,
  FileSearch,
  FileText,
  FlaskConical,
  FolderKanban,
  GitCompareArrows,
  LayoutDashboard,
  MessageSquareText,
  Search,
  UserCog,
  Users,
  type LucideIcon,
} from 'lucide-react'

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  /** One-line explanation shown as the page description and in the collapsed-sidebar tooltip. */
  description: string
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
      { to: '/app', label: 'Dashboard', icon: LayoutDashboard, description: 'Overview of your workspace' },
      {
        to: '/app/documents',
        label: 'Documents',
        icon: FileText,
        description: 'Upload and manage the files Retrieva answers from',
        permission: 'documents:read',
      },
      {
        to: '/app/collections',
        label: 'Collections',
        icon: FolderKanban,
        description: 'Group related documents and ask questions across them',
        permission: 'collections:read',
      },
      {
        to: '/app/chat',
        label: 'AI Chat',
        icon: MessageSquareText,
        description: 'Ask questions and get answers with verified sources',
        permission: 'chat:use',
      },
      {
        to: '/app/research',
        label: 'Research',
        icon: FileSearch,
        description: 'Multi-step investigations with a cited, exportable report',
        permission: 'research:use',
      },
    ],
  },
  {
    label: 'Intelligence',
    items: [
      {
        to: '/app/search',
        label: 'Search Explorer',
        icon: Search,
        description: 'See exactly which passages are found for a query, and why',
        permission: 'search:use',
      },
      {
        to: '/app/compare',
        label: 'Compare Documents',
        icon: GitCompareArrows,
        description: 'Find what changed between two documents',
        permission: 'documents:read',
      },
      {
        to: '/app/evaluation',
        label: 'Search Quality',
        icon: FlaskConical,
        description: 'Measure and compare search quality on known questions',
        permission: 'evaluation:read',
      },
      {
        to: '/app/analytics',
        label: 'Analytics',
        icon: BarChart3,
        description: 'Usage, speed and answer quality over time',
        permission: 'analytics:read',
      },
    ],
  },
  {
    label: 'Administration',
    items: [
      {
        to: '/app/admin?tab=members',
        label: 'Users & Roles',
        icon: Users,
        description: 'Invite people and control what they can do',
        permission: 'members:manage',
      },
      {
        to: '/app/admin?tab=audit',
        label: 'Activity & Audit Log',
        icon: Activity,
        description: 'Security-relevant activity in this workspace',
        permission: 'audit:read',
      },
      {
        to: '/app/admin?tab=organization',
        label: 'Workspace Settings',
        icon: Building2,
        description: 'Name and details of this workspace',
        permission: 'members:manage',
      },
      { to: '/app/settings', label: 'My Account', icon: UserCog, description: 'Profile, password and appearance' },
    ],
  },
]

export interface RouteMeta {
  section: string
  title: string
  description: string
  parent?: { title: string; to: string }
}

/** Page title, section and description for the breadcrumb bar. */
export function routeMeta(pathname: string, search: string): RouteMeta | null {
  const tab = normalizeTab(new URLSearchParams(search).get('tab'))
  for (const section of NAVIGATION) {
    for (const item of section.items) {
      const [path, query] = item.to.split('?')
      if (query) {
        const itemTab = new URLSearchParams(query).get('tab')
        if (pathname === path && tab === itemTab) {
          return { section: section.label, title: item.label, description: item.description }
        }
        continue
      }
      if (pathname === path) return { section: section.label, title: item.label, description: item.description }
      if (path !== '/app' && pathname.startsWith(`${path}/`)) {
        const detail =
          path === '/app/documents' ? 'Document' : path === '/app/chat' ? 'Conversation' : path === '/app/research' ? 'Report' : 'Details'
        return {
          section: section.label,
          title: detail,
          description: item.description,
          parent: { title: item.label, to: path },
        }
      }
    }
  }
  return null
}

/** Whether a nav entry is the current page (query-aware for the admin tabs). */
export function isNavActive(item: NavItem, pathname: string, search: string): boolean {
  const [path, query] = item.to.split('?')
  if (query) {
    if (pathname !== path) return false
    const tab = normalizeTab(new URLSearchParams(search).get('tab'))
    return tab === new URLSearchParams(query).get('tab')
  }
  return path === '/app' ? pathname === '/app' : pathname === path || pathname.startsWith(`${path}/`)
}

/** Invitations live under "Users & Roles"; a missing tab means the default (members) tab. */
function normalizeTab(tab: string | null): string {
  return !tab || tab === 'invitations' ? 'members' : tab
}
