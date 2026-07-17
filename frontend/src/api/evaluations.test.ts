import { afterEach, expect, test, vi } from 'vitest'
import { evaluationsApi } from './evaluations'


afterEach(() => {
  vi.unstubAllGlobals()
})


function successfulFetch() {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: vi.fn().mockResolvedValue({}),
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}


test('patch sends revision and only supplied human draft fields', async () => {
  const fetchMock = successfulFetch()

  await evaluationsApi.update(17, {
    revision: 3,
    overall_comments: 'Only this field changed.',
  })

  expect(fetchMock).toHaveBeenCalledWith('/api/evaluations/17', {
    method: 'PATCH',
    body: JSON.stringify({
      revision: 3,
      overall_comments: 'Only this field changed.',
    }),
    headers: { 'Content-Type': 'application/json' },
  })
})


test('LLM disclosure logging uses POST with the selected evaluation', async () => {
  const fetchMock = successfulFetch()

  await evaluationsApi.recordLlmAccess(12, 44)

  expect(fetchMock).toHaveBeenCalledWith('/api/evaluations/12/llm-access', {
    method: 'POST',
    body: JSON.stringify({ llm_evaluation_id: 44 }),
    headers: { 'Content-Type': 'application/json' },
  })
})


test('evaluation retry targets the saved assessment without regeneration', async () => {
  const fetchMock = successfulFetch()

  await evaluationsApi.retryLlm(9)

  expect(fetchMock).toHaveBeenCalledWith('/api/assessments/9/evaluations/llm/retry', {
    method: 'POST',
    body: JSON.stringify({}),
    headers: { 'Content-Type': 'application/json' },
  })
})
