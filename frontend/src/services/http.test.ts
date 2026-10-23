import { afterEach, describe, expect, it, vi } from 'vitest'

import { errorResponse, jsonResponse, mockFetch } from '@/test/utils'

import { ApiError, buildUrl, http, setAccessToken, setRefreshHandler } from './http'

afterEach(() => {
  setAccessToken(null)
  vi.unstubAllGlobals()
})

describe('http client', () => {
  it('sends the in-memory access token as a bearer header', async () => {
    setAccessToken('token-123')
    const fetchMock = mockFetch({ 'GET /api/v1/things': () => jsonResponse({ ok: true }) })
    await http.get('/things')
    const headers = fetchMock.mock.calls[0][1]?.headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer token-123')
  })

  it('raises ApiError with field errors from the standard error body', async () => {
    mockFetch({
      'POST /api/v1/things': () =>
        jsonResponse(
          {
            error: {
              code: 'validation_error',
              message: 'Request validation failed',
              details: { fields: [{ field: 'name', message: 'Field required' }] },
              correlation_id: 'cid-1',
            },
          },
          422,
        ),
    })
    const error = await http.post('/things', {}).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).fieldErrors).toEqual({ name: 'Field required' })
    expect((error as ApiError).correlationId).toBe('cid-1')
  })

  it('refreshes once on 401 and retries, sharing one refresh across concurrent requests', async () => {
    setAccessToken('expired')
    let calls = 0
    mockFetch({
      'GET /api/v1/things': (_url, init) => {
        const auth = (init.headers as Record<string, string>).Authorization
        return auth === 'Bearer fresh' ? jsonResponse({ ok: true }) : errorResponse(401, 'unauthenticated', 'expired')
      },
    })
    const refresh = vi.fn(async () => {
      calls += 1
      await new Promise((resolve) => setTimeout(resolve, 10))
      setAccessToken('fresh')
      return 'fresh'
    })
    setRefreshHandler(refresh)

    const results = await Promise.all([http.get('/things'), http.get('/things'), http.get('/things')])
    expect(results).toEqual([{ ok: true }, { ok: true }, { ok: true }])
    expect(calls).toBe(1)
  })

  it('does not retry when the request opted out', async () => {
    setAccessToken('expired')
    const refresh = vi.fn(async () => 'fresh')
    setRefreshHandler(refresh)
    mockFetch({ 'POST /api/v1/auth/login': () => errorResponse(401, 'unauthenticated', 'bad credentials') })
    await expect(
      import('./http').then(({ request }) => request('/auth/login', { method: 'POST', noRetry: true })),
    ).rejects.toThrow('bad credentials')
    expect(refresh).not.toHaveBeenCalled()
  })

  it('builds query strings and skips empty values', () => {
    expect(buildUrl('/docs', { page: 2, q: '', tags: ['a', 'b'], missing: undefined })).toBe(
      '/api/v1/docs?page=2&tags=a&tags=b',
    )
  })
})
