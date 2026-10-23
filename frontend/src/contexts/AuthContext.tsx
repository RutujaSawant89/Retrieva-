import { useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import { authApi, type RegisterInput } from '@/services/auth'
import { ApiError, refreshOnce, setAccessToken, setRefreshHandler } from '@/services/http'
import type { SessionOut } from '@/types/api'

type Status = 'loading' | 'authenticated' | 'anonymous'

interface AuthContextValue {
  status: Status
  session: SessionOut | null
  login: (email: string, password: string) => Promise<SessionOut>
  register: (input: RegisterInput) => Promise<SessionOut>
  logout: () => Promise<void>
  switchOrganization: (orgId: string) => Promise<void>
  updateSession: (patch: Partial<SessionOut>) => void
  can: (permission: string) => boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

/** Refresh the access token this long before it expires. */
const REFRESH_LEAD_MS = 60_000

/** Exchange the refresh cookie, retrying once if another tab rotated it at the same moment. */
async function exchangeRefreshCookie(): Promise<SessionOut> {
  try {
    return await authApi.refresh()
  } catch (error) {
    if (error instanceof ApiError && error.code === 'refresh_race') {
      await new Promise((resolve) => setTimeout(resolve, 250))
      return authApi.refresh()
    }
    throw error
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [session, setSession] = useState<SessionOut | null>(null)
  const [status, setStatus] = useState<Status>('loading')
  const timer = useRef<number | undefined>(undefined)

  const apply = useCallback((next: SessionOut | null) => {
    setAccessToken(next?.access_token ?? null)
    setSession(next)
    setStatus(next ? 'authenticated' : 'anonymous')
    window.clearTimeout(timer.current)
    if (next) {
      const delay = Math.max(5_000, new Date(next.expires_at).getTime() - Date.now() - REFRESH_LEAD_MS)
      timer.current = window.setTimeout(() => void refreshOnce(), delay)
    }
  }, [])

  useEffect(() => {
    setRefreshHandler(async () => {
      try {
        const next = await exchangeRefreshCookie()
        apply(next)
        return next.access_token
      } catch {
        apply(null)
        queryClient.clear()
        return null
      }
    })
    // Restore the session from the httpOnly refresh cookie (single-flight, StrictMode-safe).
    void refreshOnce()
    return () => window.clearTimeout(timer.current)
  }, [apply, queryClient])

  const login = useCallback(
    async (email: string, password: string) => {
      const next = await authApi.login(email, password)
      queryClient.clear()
      apply(next)
      return next
    },
    [apply, queryClient],
  )

  const register = useCallback(
    async (input: RegisterInput) => {
      const next = await authApi.register(input)
      queryClient.clear()
      apply(next)
      return next
    },
    [apply, queryClient],
  )

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } finally {
      apply(null)
      queryClient.clear()
    }
  }, [apply, queryClient])

  const switchOrganization = useCallback(
    async (orgId: string) => {
      const next = await authApi.switchOrganization(orgId)
      queryClient.clear()
      apply(next)
    },
    [apply, queryClient],
  )

  const updateSession = useCallback((patch: Partial<SessionOut>) => {
    setSession((current) => (current ? { ...current, ...patch } : current))
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      session,
      login,
      register,
      logout,
      switchOrganization,
      updateSession,
      can: (permission: string) => session?.permissions.includes(permission) ?? false,
    }),
    [status, session, login, register, logout, switchOrganization, updateSession],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
