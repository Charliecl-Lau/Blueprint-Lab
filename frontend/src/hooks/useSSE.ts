import { useEffect } from 'react'
import type { SSEEvent } from '../types'

export function useSSE(
  runId: number | null,
  onEvent: (event: SSEEvent) => void,
  onDone?: () => void,
) {
  useEffect(() => {
    if (!runId) return
    const es = new EventSource(`/api/runs/${runId}/events`)

    es.onmessage = (e) => {
      const data: SSEEvent = JSON.parse(e.data)
      onEvent(data)
    }

    es.addEventListener('done', () => {
      es.close()
      onDone?.()
    })

    es.onerror = () => es.close()

    return () => es.close()
  }, [runId])
}
