import { Building2, Check, ChevronsUpDown, LogOut, Menu, Monitor, Moon, Sun, User, X } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { Logo } from '@/components/brand/Logo'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/overlays'
import { useAuth } from '@/contexts/AuthContext'
import { useTheme, type ThemePreference } from '@/contexts/ThemeContext'
import { cn } from '@/utils/cn'
import { initials } from '@/utils/format'

import { NAVIGATION } from './navigation'

function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const { can } = useAuth()
  return (
    <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-4" aria-label="Main">
      {NAVIGATION.map((section) => {
        const items = section.items.filter((item) => !item.permission || can(item.permission))
        if (items.length === 0) return null
        return (
          <div key={section.label}>
            <p className="px-2 pb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground/80">
              {section.label}
            </p>
            <ul className="space-y-0.5">
              {items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.to === '/app'}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      cn(
                        'flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-[13.5px] font-medium transition-colors',
                        isActive
                          ? 'bg-primary-soft text-primary'
                          : 'text-muted-foreground hover:bg-surface-2 hover:text-foreground',
                      )
                    }
                  >
                    <item.icon className="size-4 shrink-0" aria-hidden />
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        )
      })}
    </nav>
  )
}

function OrganizationSwitcher() {
  const { session, switchOrganization } = useAuth()
  if (!session) return null
  const { organization, organizations } = session
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="flex w-full items-center gap-2 rounded-lg border border-border bg-surface px-2.5 py-2 text-left hover:bg-surface-2"
        >
          <span className="flex size-6 items-center justify-center rounded-md bg-surface-2 text-muted-foreground">
            <Building2 className="size-3.5" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[13px] font-medium">{organization.name}</span>
            <span className="block text-[11px] capitalize text-muted-foreground">{organization.role}</span>
          </span>
          <ChevronsUpDown className="size-3.5 text-muted-foreground" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-60">
        <DropdownMenuLabel>Organizations</DropdownMenuLabel>
        {organizations.map((org) => (
          <DropdownMenuItem
            key={org.id}
            onSelect={async () => {
              if (org.id === organization.id) return
              try {
                await switchOrganization(org.id)
                toast.success(`Switched to ${org.name}`)
              } catch (error) {
                toast.error(error instanceof Error ? error.message : 'Could not switch organization')
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
          className="flex size-8 items-center justify-center rounded-full bg-navy text-[12px] font-semibold text-white dark:bg-primary-soft dark:text-primary"
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
          <User /> Profile & security
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

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false)
  return (
    <div className="flex h-full">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-surface lg:flex">
        <div className="flex h-14 items-center px-4">
          <Logo />
        </div>
        <div className="px-3">
          <OrganizationSwitcher />
        </div>
        <SidebarNav />
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
              className="fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-border bg-surface lg:hidden"
              initial={{ x: -280 }}
              animate={{ x: 0 }}
              exit={{ x: -280 }}
              transition={{ type: 'spring', stiffness: 400, damping: 40 }}
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
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-surface/80 px-4 backdrop-blur lg:px-6">
          <Button
            variant="ghost"
            size="icon-sm"
            className="lg:hidden"
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
          >
            <Menu />
          </Button>
          <div className="lg:hidden">
            <Logo compact />
          </div>
          <div className="hidden lg:block" />
          <UserMenu />
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
