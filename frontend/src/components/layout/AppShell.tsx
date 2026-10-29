import { AnimatePresence, motion } from 'framer-motion'
import {
  BookOpen,
  Building2,
  Check,
  ChevronRight,
  ChevronsUpDown,
  LogOut,
  Menu,
  Monitor,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Sun,
  User,
  X,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { Logo, LogoMark } from '@/components/brand/Logo'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Tooltip,
} from '@/components/ui/overlays'
import { useAuth } from '@/contexts/AuthContext'
import { useTheme, type ThemePreference } from '@/contexts/ThemeContext'
import { cn } from '@/utils/cn'
import { initials } from '@/utils/format'

import { isNavActive, NAVIGATION, routeMeta } from './navigation'

const COLLAPSED_KEY = 'retrieva.sidebar.collapsed'

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === '1'
  } catch {
    return false
  }
}

function SidebarNav({ collapsed, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const { can } = useAuth()
  const { pathname, search } = useLocation()
  return (
    <nav className="scroll-thin flex-1 space-y-5 overflow-y-auto px-3 py-4" aria-label="Main">
      {NAVIGATION.map((section) => {
        const items = section.items.filter((item) => !item.permission || can(item.permission))
        if (items.length === 0) return null
        return (
          <div key={section.label}>
            {collapsed ? (
              <div className="mx-2 mb-2 h-px bg-border" aria-hidden />
            ) : (
              <p className="px-2 pb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground/80">
                {section.label}
              </p>
            )}
            <ul className="space-y-0.5">
              {items.map((item) => {
                const active = isNavActive(item, pathname, search)
                const link = (
                  <Link
                    to={item.to}
                    onClick={onNavigate}
                    aria-current={active ? 'page' : undefined}
                    aria-label={collapsed ? item.label : undefined}
                    className={cn(
                      'group relative flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-[13.5px] font-medium transition-colors',
                      collapsed && 'justify-center px-0 py-2',
                      active
                        ? 'bg-primary-soft text-primary'
                        : 'text-muted-foreground hover:bg-surface-2 hover:text-foreground',
                    )}
                  >
                    {active && !collapsed && (
                      <span className="absolute -left-3 top-1.5 bottom-1.5 w-0.5 rounded-full bg-primary" aria-hidden />
                    )}
                    <item.icon className="size-4 shrink-0" aria-hidden />
                    {!collapsed && <span className="truncate">{item.label}</span>}
                  </Link>
                )
                return (
                  <li key={item.to}>
                    {collapsed ? (
                      <Tooltip
                        content={
                          <span>
                            <span className="block font-medium">{item.label}</span>
                            <span className="block text-white/70">{item.description}</span>
                          </span>
                        }
                      >
                        {link}
                      </Tooltip>
                    ) : (
                      link
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
        )
      })}
    </nav>
  )
}

function OrganizationSwitcher({ collapsed }: { collapsed?: boolean }) {
  const { session, switchOrganization } = useAuth()
  if (!session) return null
  const { organization, organizations } = session
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={`Workspace: ${organization.name}`}
          className={cn(
            'flex w-full items-center gap-2 rounded-lg border border-border bg-surface px-2.5 py-2 text-left hover:bg-surface-2',
            collapsed && 'justify-center px-0',
          )}
        >
          <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-primary-soft text-[11px] font-semibold text-primary">
            {initials(organization.name) || <Building2 className="size-3.5" />}
          </span>
          {!collapsed && (
            <>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] font-medium">{organization.name}</span>
                <span className="block text-[11px] capitalize text-muted-foreground">{organization.role}</span>
              </span>
              <ChevronsUpDown className="size-3.5 text-muted-foreground" />
            </>
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-60">
        <DropdownMenuLabel>Workspaces</DropdownMenuLabel>
        {organizations.map((org) => (
          <DropdownMenuItem
            key={org.id}
            onSelect={async () => {
              if (org.id === organization.id) return
              try {
                await switchOrganization(org.id)
                toast.success(`Switched to ${org.name}`)
              } catch (error) {
                toast.error(error instanceof Error ? error.message : 'Could not switch workspace')
              }
            }}
          >
            <span className="flex-1 truncate">{org.name}</span>
            {org.id === organization.id && <Check className="text-primary" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

const THEME_OPTIONS: { value: ThemePreference; label: string; icon: typeof Sun }[] = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'System', icon: Monitor },
]

function UserMenu() {
  const { session, logout } = useAuth()
  const { preference, setPreference } = useTheme()
  const navigate = useNavigate()
  if (!session) return null
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="flex size-8 items-center justify-center rounded-full bg-navy text-[12px] font-semibold text-white ring-offset-2 hover:ring-2 hover:ring-primary/30 dark:bg-primary-soft dark:text-primary"
          aria-label="Account menu"
        >
          {initials(session.user.full_name) || <User className="size-4" />}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-60">
        <div className="px-2 py-1.5">
          <p className="truncate text-[13px] font-medium">{session.user.full_name}</p>
          <p className="truncate text-xs text-muted-foreground">{session.user.email}</p>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuLabel>Theme</DropdownMenuLabel>
        {THEME_OPTIONS.map((option) => (
          <DropdownMenuItem key={option.value} onSelect={() => setPreference(option.value)}>
            <option.icon />
            <span className="flex-1">{option.label}</span>
            {preference === option.value && <Check className="text-primary" />}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => navigate('/app/settings')}>
          <User /> My account
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => navigate('/case-study')}>
          <BookOpen /> How Retrieva works
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={async () => {
            await logout()
            navigate('/login', { replace: true })
          }}
        >
          <LogOut /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function Breadcrumbs() {
  const { pathname, search } = useLocation()
  const meta = routeMeta(pathname, search)
  if (!meta) return null
  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex min-w-0 items-center gap-1.5 text-[13px]">
        <li className="hidden text-muted-foreground sm:block">{meta.section}</li>
        <li className="hidden text-muted-foreground/60 sm:block" aria-hidden>
          <ChevronRight className="size-3.5" />
        </li>
        {meta.parent && (
          <>
            <li className="min-w-0">
              <Link to={meta.parent.to} className="truncate text-muted-foreground hover:text-foreground">
                {meta.parent.title}
              </Link>
            </li>
            <li className="text-muted-foreground/60" aria-hidden>
              <ChevronRight className="size-3.5" />
            </li>
          </>
        )}
        <li className="truncate font-medium text-foreground" aria-current="page">
          {meta.title}
        </li>
      </ol>
    </nav>
  )
}

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(readCollapsed)

  useEffect(() => {
    try {
      localStorage.setItem(COLLAPSED_KEY, collapsed ? '1' : '0')
    } catch {
      /* storage unavailable */
    }
  }, [collapsed])

  return (
    <div className="flex h-full">
      <aside
        className={cn(
          'hidden shrink-0 flex-col border-r border-border bg-surface transition-[width] duration-200 lg:flex',
          collapsed ? 'w-[68px]' : 'w-60',
        )}
      >
        <div className={cn('flex h-14 items-center', collapsed ? 'justify-center' : 'px-4')}>
          <Link to="/app" aria-label="Retrieva dashboard">
            {collapsed ? <LogoMark /> : <Logo />}
          </Link>
        </div>
        <div className="px-3">
          <OrganizationSwitcher collapsed={collapsed} />
        </div>
        <SidebarNav collapsed={collapsed} />
        <div className={cn('border-t border-border p-3', collapsed && 'flex justify-center')}>
          <Button
            variant="ghost"
            size={collapsed ? 'icon-sm' : 'sm'}
            className={cn(!collapsed && 'w-full justify-start text-muted-foreground')}
            onClick={() => setCollapsed((c) => !c)}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
            {!collapsed && 'Collapse'}
          </Button>
        </div>
      </aside>

      <AnimatePresence>
        {mobileOpen && (
          <>
            <motion.div
              className="fixed inset-0 z-40 bg-navy/40 lg:hidden"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setMobileOpen(false)}
            />
            <motion.aside
              className="fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] flex-col border-r border-border bg-surface lg:hidden"
              initial={{ x: -300 }}
              animate={{ x: 0 }}
              exit={{ x: -300 }}
              transition={{ type: 'spring', stiffness: 400, damping: 40 }}
              role="dialog"
              aria-label="Navigation"
            >
              <div className="flex h-14 items-center justify-between px-4">
                <Logo />
                <Button variant="ghost" size="icon-sm" onClick={() => setMobileOpen(false)} aria-label="Close menu">
                  <X />
                </Button>
              </div>
              <div className="px-3">
                <OrganizationSwitcher />
              </div>
              <SidebarNav onNavigate={() => setMobileOpen(false)} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-surface/80 px-4 backdrop-blur lg:px-6">
          <Button variant="ghost" size="icon-sm" className="lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open menu">
            <Menu />
          </Button>
          <div className="min-w-0 flex-1">
            <Breadcrumbs />
          </div>
          <Button variant="ghost" size="sm" asChild className="hidden text-muted-foreground sm:inline-flex">
            <Link to="/case-study">
              <BookOpen /> How it works
            </Link>
          </Button>
          <UserMenu />
        </header>
        {/* Not keyed by route: the chat page must survive its URL changing mid-stream. */}
        <main className="scroll-thin min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
