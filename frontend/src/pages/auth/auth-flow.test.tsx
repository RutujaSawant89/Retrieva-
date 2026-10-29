import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AppRoutes } from '@/App'
import { setAccessToken } from '@/services/http'
import { errorResponse, jsonResponse, makeSession, mockFetch, renderWithProviders } from '@/test/utils'

afterEach(() => {
  setAccessToken(null)
  vi.unstubAllGlobals()
})

describe('authentication flow', () => {
  it('redirects anonymous users from protected routes to login', async () => {
    mockFetch({ 'POST /api/v1/auth/refresh': () => errorResponse(401, 'unauthenticated', 'Missing refresh token') })
    renderWithProviders(<AppRoutes />, { route: '/app/settings' })
    expect(await screen.findByRole('heading', { name: 'Sign in to Retrieva' })).toBeInTheDocument()
  })

  it('signs in and lands on the dashboard', async () => {
    const session = makeSession()
    const fetchMock = mockFetch({
      'POST /api/v1/auth/refresh': () => errorResponse(401, 'unauthenticated', 'Missing refresh token'),
      'POST /api/v1/auth/login': () => jsonResponse(session),
    })
    renderWithProviders(<AppRoutes />, { route: '/login' })

    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Work email'), 'ada@acme.example.com')
    await user.type(screen.getByLabelText('Password'), 'Sup3r-Secret-Pass!')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('heading', { name: /^Good (morning|afternoon|evening), Ada$/ })).toBeInTheDocument()
    const loginCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/auth/login'))
    expect(JSON.parse(String(loginCall?.[1]?.body))).toMatchObject({ email: 'ada@acme.example.com' })
  })

  it('shows the server error message when credentials are rejected', async () => {
    mockFetch({
      'POST /api/v1/auth/refresh': () => errorResponse(401, 'unauthenticated', 'Missing refresh token'),
      'POST /api/v1/auth/login': () => errorResponse(401, 'unauthenticated', 'Invalid email or password'),
    })
    renderWithProviders(<AppRoutes />, { route: '/login' })
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Work email'), 'ada@acme.example.com')
    await user.type(screen.getByLabelText('Password'), 'wrong-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password')
  })

  it('restores a session from the refresh cookie on load', async () => {
    mockFetch({ 'POST /api/v1/auth/refresh': () => jsonResponse(makeSession()) })
    renderWithProviders(<AppRoutes />, { route: '/app' })
    await waitFor(() => expect(screen.getByRole('heading', { name: /^Good (morning|afternoon|evening), Ada$/ })).toBeInTheDocument())
  })

  it('keeps the register button disabled until the password policy is met', async () => {
    mockFetch({ 'POST /api/v1/auth/refresh': () => errorResponse(401, 'unauthenticated', 'none') })
    renderWithProviders(<AppRoutes />, { route: '/register' })
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Full name'), 'Ada Lovelace')
    await user.type(screen.getByLabelText('Work email'), 'ada@acme.example.com')
    await user.type(screen.getByLabelText('Organization name'), 'Acme')
    await user.type(screen.getByLabelText('Password'), 'weak')
    expect(screen.getByRole('button', { name: 'Create organization' })).toBeDisabled()
    await user.clear(screen.getByLabelText('Password'))
    await user.type(screen.getByLabelText('Password'), 'Sup3r-Secret-Pass!')
    expect(screen.getByRole('button', { name: 'Create organization' })).toBeEnabled()
  })
})
