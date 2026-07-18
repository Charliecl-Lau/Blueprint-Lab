import { act, renderHook } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { useSSE } from './useSSE'

class FakeEventSource {
  static instances: FakeEventSource[] = []

  url: string
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  close = vi.fn()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
  FakeEventSource.instances = []
})

test('keeps the event source open after a transient stream error', () => {
  vi.stubGlobal('EventSource', FakeEventSource)
  const { unmount } = renderHook(() => useSSE(8, vi.fn()))
  const source = FakeEventSource.instances[0]

  expect(source.url).toBe('/api/runs/8/progress')
  act(() => { source.onerror?.(new Event('error')) })
  expect(source.close).not.toHaveBeenCalled()

  unmount()
  expect(source.close).toHaveBeenCalledOnce()
})
