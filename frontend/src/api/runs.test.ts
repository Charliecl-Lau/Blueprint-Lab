import { afterEach, expect, test, vi } from 'vitest'
import { runsApi } from './runs'

afterEach(() => vi.unstubAllGlobals())

test('rewrite retry sends its idempotency key to the narrow endpoint', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: vi.fn().mockResolvedValue({ id: 7 }),
  })
  vi.stubGlobal('fetch', fetchMock)

  await runsApi.retryDocxRewrite(7, 'retry-key')

  expect(fetchMock).toHaveBeenCalledWith('/api/runs/7/docx-rewrite/retry', {
    method: 'POST',
    body: JSON.stringify({}),
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': 'retry-key' },
  })
})
