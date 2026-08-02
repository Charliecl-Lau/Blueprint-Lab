import { afterEach, expect, test, vi } from 'vitest'
import { runsApi } from './runs'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

test('loads terminal history from the dedicated endpoint', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [] })
  vi.stubGlobal('fetch', fetchMock)
  await runsApi.historyRecent(12)
  expect(fetchMock).toHaveBeenCalledWith(
    '/api/runs/history/recent?limit=12',
    { headers: { 'Content-Type': 'application/json' } },
  )
})

test('loads immutable run detail with GET', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
  vi.stubGlobal('fetch', fetchMock)
  await runsApi.historyDetail(8)
  expect(fetchMock).toHaveBeenCalledWith(
    '/api/runs/8/history',
    { headers: { 'Content-Type': 'application/json' } },
  )
})

test('uses the stored filename when downloading DOCX', async () => {
  const anchor = { href: '', download: '', click: vi.fn() } as unknown as HTMLAnchorElement
  vi.spyOn(document, 'createElement').mockReturnValue(anchor)
  vi.stubGlobal('URL', {
    createObjectURL: vi.fn().mockReturnValue('blob:docx'),
    revokeObjectURL: vi.fn(),
  })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    blob: async () => new Blob(['PK-saved']),
    headers: new Headers({
      'Content-Disposition': 'attachment; filename="phase-stability.docx"',
    }),
  }))

  await runsApi.exportDocx(8)

  expect(anchor.download).toBe('phase-stability.docx')
  expect(anchor.click).toHaveBeenCalledOnce()
})
