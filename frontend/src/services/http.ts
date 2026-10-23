/**
 * HTTP client for the Retrieva API.
 *
 * - The access token lives only in memory (never localStorage/sessionStorage).
 * - The refresh token is an httpOnly, SameSite=Strict cookie scoped to /api/v1/auth, so
 *   JavaScript can never read it; `refreshSession()` exchanges it for a new access token.
 * - A 401 triggers one single-flight refresh followed by one retry of the original request.
 */

export const API_BASE = `${import.meta.env.VITE_API_BASE_URL ?? ''}/api/v1`

export interface ApiErrorBody {
  code: string
  message: string
  details?: Record<string, unknown>
  correlation_id?: string | null
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>
  readonly correlationId: string | null

  constructor(status: number, body: ApiErrorBody) {
    super(body.message)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code
    this.details = body.details ?? {}
    this.correlationId = body.correlation_id ?? null
  }

  /** Field-level validation messages keyed by field name. */
  get fieldErrors(): Record<string, string> {
    const fields = (this.details.fields as { field: string; message: string }[] | undefined) ?? []
    return Object.fromEntries(fields.map((f) => [f.field, f.message]))
  }
}

type SessionListener = (token: string | null) => void

let accessToken: string | null = null
let refreshInFlight: Promise<unknown> | null = null
let refreshHandler: (() => Promise<string | null>) | null = null
const listeners = new Set<SessionListener>()

export function setAccessToken(token: string | null): void {
  accessToken = token
  listeners.forEach((listener) => listener(token))
}

export function getAccessToken(): string | null {
  return accessToken
}

export function onAccessTokenChange(listener: SessionListener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Registered by the auth context: performs the refresh and returns the new access token. */
export function setRefreshHandler(handler: () => Promise<string | null>): void {
  refreshHandler = handler
}

/** Single-flight refresh: concurrent callers share one network request. */
export async function refreshOnce(): Promise<string | null> {
  if (!refreshHandler) return null
  if (!refreshInFlight) {
    refreshInFlight = refreshHandler().finally(() => {
      refreshInFlight = null
    })
  }
  return (await refreshInFlight) as string | null
}

async function parseError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody = { code: 'http_error', message: `Request failed (${response.status})` }
  try {
    const json = await response.json()
    if (json?.error) body = json.error
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(response.status, body)
}

export interface RequestOptions {
  method?: string
  body?: unknown
  query?: Record<string, string | number | boolean | undefined | null | string[]>
  signal?: AbortSignal
  /** Skip the automatic refresh-and-retry on 401 (used by auth endpoints). */
  noRetry?: boolean
  headers?: Record<string, string>
}

export function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = `${API_BASE}${path}`
  if (!query) return url
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue
    if (Array.isArray(value)) value.forEach((v) => params.append(key, v))
    else params.set(key, String(value))
  }
  const qs = params.toString()
  return qs ? `${url}?${qs}` : url
}

export async function rawRequest(path: string, options: RequestOptions = {}): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json', ...options.headers }
  let body: BodyInit | undefined
  if (options.body instanceof FormData) {
    body = options.body
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }

  const send = () => {
    const authHeaders: Record<string, string> = accessToken ? { Authorization: `Bearer ${accessToken}` } : {}
    return fetch(buildUrl(path, options.query), {
      method: options.method ?? 'GET',
      headers: { ...headers, ...authHeaders },
      body,
      signal: options.signal,
      credentials: 'same-origin',
    })
  }

  let response = await send()
  if (response.status === 401 && !options.noRetry && accessToken !== null) {
    const refreshed = await refreshOnce()
    if (refreshed) response = await send()
  }
  if (!response.ok) throw await parseError(response)
  return response
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await rawRequest(path, options)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const http = {
  get: <T>(path: string, query?: RequestOptions['query'], signal?: AbortSignal) =>
    request<T>(path, { query, signal }),
  post: <T>(path: string, body?: unknown, options: Omit<RequestOptions, 'body' | 'method'> = {}) =>
    request<T>(path, { ...options, method: 'POST', body }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PATCH', body }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PUT', body }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}

/** Download an authenticated file and hand it to the browser as a named file. */
export async function downloadFile(path: string, filename: string, options: RequestOptions = {}): Promise<void> {
  const response = await rawRequest(path, options)
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1_000)
}

/**
 * Upload with progress reporting. `fetch` cannot report upload progress, so this uses XHR.
 */
export function uploadWithProgress<T>(
  path: string,
  form: FormData,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<T> {
  const attempt = () =>
    new Promise<T>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', buildUrl(path))
      if (accessToken) xhr.setRequestHeader('Authorization', `Bearer ${accessToken}`)
      xhr.setRequestHeader('Accept', 'application/json')
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress(event.loaded / event.total)
      }
      xhr.onload = () => {
        let json: unknown = null
        try {
          json = JSON.parse(xhr.responseText)
        } catch {
          /* ignore */
        }
        if (xhr.status >= 200 && xhr.status < 300) resolve(json as T)
        else {
          const body = (json as { error?: ApiErrorBody } | null)?.error ?? {
            code: 'upload_failed',
            message: `Upload failed (${xhr.status})`,
          }
          reject(new ApiError(xhr.status, body))
        }
      }
      xhr.onerror = () => reject(new ApiError(0, { code: 'network_error', message: 'Network error during upload' }))
      signal?.addEventListener('abort', () => xhr.abort())
      xhr.send(form)
    })

  return attempt().catch(async (error: unknown) => {
    if (error instanceof ApiError && error.status === 401 && (await refreshOnce())) return attempt()
    throw error
  })
}
