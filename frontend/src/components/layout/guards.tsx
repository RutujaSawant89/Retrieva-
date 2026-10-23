import type { ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router'

import { LogoMark } from '@/components/brand/Logo'
import { EmptyState } from '@/components/ui/primitives'
import { useAuth } from '@/contexts/AuthContext'

function FullScreenLoader() {
  return (
    <div className="flex h-full items-center justify-center" role="status" aria-label="Loading">
      <LogoMark className="size-9 animate-pulse" />
    </div>
  )
}

/** Renders child routes only for authenticated users; otherwise redirects to /login. */
export function RequireAuth() {
  const { status } = useAuth()
  const location = useLocation()
  if (status === 'loading') return <FullScreenLoader />
  if (status === 'anonymous') return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <Outlet />
}

/** Sends signed-in users away from the login/register pages. */
export function RedirectIfAuthenticated({ children }: { children: ReactNode }) {
  const { status } = useAuth()
  if (status === 'loading') return <FullScreenLoader />
  if (status === 'authenticated') return <Navigate to="/app" replace />
  return <>{children}</>
}

export function RequirePermission({ permission, children }: { permission: string; children: ReactNode }) {
  const { can } = useAuth()
  if (!can(permission)) {
    return (
      <EmptyState
        className="py-24"
        title="You don't have access to this page"
        description="Ask an organization admin for a role that includes this permission."
      />
    )
  }
  return <>{children}</>
}
