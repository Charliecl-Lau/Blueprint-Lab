const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = init?.body instanceof FormData
  const headers = isFormData
    ? init?.headers
    : { 'Content-Type': 'application/json', ...init?.headers }
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const error = new Error(`${res.status}: Request failed`) as Error & { status: number; body: unknown }
    error.status = res.status
    error.body = body
    throw error
  }
  return res.json()
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown, headers?: HeadersInit) => request<T>(path, {
    method: 'POST',
    body: body instanceof FormData ? body : JSON.stringify(body),
    headers,
  }),
  patch: <T>(path: string, body: unknown) => request<T>(path, {
    method: 'PATCH',
    body: JSON.stringify(body),
  }),
}
