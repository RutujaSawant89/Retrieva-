import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router'
import { vi } from 'vitest'

import { TooltipProvider } from '@/components/ui/overlays'
import { AuthProvider } from '@/contexts/AuthContext'
import { ThemeProvider } from '@/contexts/ThemeContext'
import type { SessionOut } from '@/types/api'

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

export function errorResponse(status: number, code: string, message: string): Response {
  return jsonResponse({ error: { code, message, details: {}, correlation_id: 'test' } }, status)
}

export function makeSession(overrides: Partial<SessionOut> = {}): SessionOut {
  const org = { id: 'org-1', name: 'Acme Research', slug: 'acme', role: 'admin' as const }
  return {
    access_token: 'access-1',
    token_type: 'bearer',
    expires_at: new Date(Date.now() + 15 * 60_000).toISOString(),
    user: {
      id: 'user-1',
      email: 'ada@acme.example.com',
      full_name: 'Ada Lovelace',
      created_at: new Date().toISOString(),
      last_login_at: null,
    },
    organization: org,
    organizations: [org],
    permissions: ['documents:read', 'members:manage'],
    ...overrides,
  }
}

type Handler = (url: string, init: RequestInit) => Response | Promise<Response>

/** Route-based fetch mock: the first matching `METHOD path` prefix handles the request. */
export function mockFetch(routes: Record<string, Handler>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = typeof input === 'string' ? input : input.toString()
    const method = (init.method ?? 'GET').toUpperCase()
    const path = url.replace(/^https?:\/\/[^/]+/, '')
    for (const [key, handler] of Object.entries(routes)) {
      const [m, prefix] = key.split(' ')
      if (m === method && path.startsWith(prefix)) return handler(url, init)
    }
    return errorResponse(404, 'not_found', `No mock for ${method} ${path}`)
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

export function renderWithProviders(ui: ReactElement, { route = '/' }: { route?: string } = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <TooltipProvider>
            <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
          </TooltipProvider>
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>,
  )
}
