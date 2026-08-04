import { useEffect } from 'react'
import type { RunSnapshot } from '../types'
import { isTerminalRunStatus } from '../store/runStore'

export function useSSE(
  runId: number | null,
  onSnapshot: (snapshot: RunSnapshot) => void,
) {
  useEffect(() => {
    if (!runId || typeof EventSource === 'undefined') return
    const es = new EventSource(`/api/runs/${runId}/progress`)

    es.onmessage = (e) => {
      const snapshot: RunSnapshot = JSON.parse(e.data)
      onSnapshot(snapshot)
      if (isTerminalRunStatus(snapshot.status)) es.close()
    }

    es.onerror = () => {
      // EventSource reconnects automatically after transient disconnects.
    }

    return () => es.close()
  }, [runId, onSnapshot])
}
