import { useEffect } from 'react'
import type { SSEEvent } from '../types'

export function normalizeSSEEvent(event: SSEEvent): SSEEvent {
  return { ...event, run_id: event.run_id ?? event.generation_id }
}

export function useSSE(
  experimentId: number | null,
  onEvent: (event: SSEEvent) => void,
  onDone?: () => void,
) {
  useEffect(() => {
    if (!experimentId) return
    const es = new EventSource(`/api/experiments/${experimentId}/progress`)

    es.onmessage = (e) => {
      const data: SSEEvent = JSON.parse(e.data)
      onEvent(normalizeSSEEvent(data))
    }

    es.addEventListener('done', () => {
      es.close()
      onDone?.()
    })

    es.onerror = () => es.close()

    return () => es.close()
  }, [experimentId, onEvent, onDone])
}
