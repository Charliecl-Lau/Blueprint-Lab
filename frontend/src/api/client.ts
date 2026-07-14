const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
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
    body: JSON.stringify(body),
    headers,
  }),
}
