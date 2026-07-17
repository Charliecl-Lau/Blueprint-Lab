import { useEffect } from 'react'
import type { RunSnapshot } from '../types'

export function useSSE(
  runId: number | null,
  onSnapshot: (snapshot: RunSnapshot) => void,
  reconnectKey = 0,
) {
  useEffect(() => {
    if (!runId || typeof EventSource === 'undefined') return
    const es = new EventSource(`/api/runs/${runId}/progress`)

    es.onmessage = (e) => {
      const snapshot: RunSnapshot = JSON.parse(e.data)
      onSnapshot(snapshot)
      if (
        snapshot.status === 'complete'
        || snapshot.status === 'generation_failed'
        || snapshot.status === 'evaluation_failed'
      ) es.close()
    }

    es.onerror = () => es.close()

    return () => es.close()
  }, [runId, onSnapshot, reconnectKey])
}
