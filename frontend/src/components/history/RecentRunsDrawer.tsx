import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { runsApi } from '../../api/runs'
import type { TerminalRunSummary } from '../../types'

type Props = { open: boolean; onClose(): void }

const focusableSelector = 'button:not(:disabled), a[href]'

export function RecentRunsDrawer({ open, onClose }: Props) {
  const [runs, setRuns] = useState<TerminalRunSummary[]>([])
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')
  const drawerRef = useRef<HTMLElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)

  const load = useCallback(() => {
    setState('loading')
    runsApi.historyRecent(10).then(
      (items) => {
        setRuns(items.filter((item) => (
          item.status === 'complete'
          || item.status === 'complete_with_warnings'
          || item.status === 'error'
        )))
        setState('ready')
      },
      () => setState('error'),
    )
  }, [])

  useEffect(() => {
    if (!open) return
    load()
    requestAnimationFrame(() => closeRef.current?.focus())
  }, [load, open])

  useEffect(() => {
    if (!open) return
    const listener = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', listener)
    return () => document.removeEventListener('keydown', listener)
  }, [onClose, open])

  const trapFocus = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key !== 'Tab') return
    const focusable = Array.from(
      drawerRef.current?.querySelectorAll<HTMLElement>(focusableSelector) ?? [],
    )
    if (focusable.length === 0) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  if (!open) return null

  return <div className="history-drawer-backdrop" onMouseDown={onClose}>
    <aside
      ref={drawerRef}
      aria-label="Recent Runs"
      aria-modal="true"
      role="dialog"
      className="history-drawer"
      onKeyDown={trapFocus}
      onMouseDown={(event) => event.stopPropagation()}
    >
      <header>
        <h2>Recent Runs</h2>
        <button ref={closeRef} aria-label="Close Recent Runs" onClick={onClose}>Close</button>
      </header>
      {state === 'loading' && <p role="status">Loading recent runs...</p>}
      {state === 'error' && <div role="alert">
        <p>Recent runs could not be loaded.</p>
        <button onClick={load}>Retry</button>
      </div>}
      {state === 'ready' && runs.length === 0 && <p>No completed or failed runs yet.</p>}
      {state === 'ready' && runs.map((run) => <Link
        key={run.id}
        className={`history-run-card ${run.display_status}`}
        to={`/runs/${run.id}/history`}
      >
        <strong>{run.topic}</strong>
        <span>Run {run.run_number}</span>
        <span>{run.display_status === 'failed' ? 'Failed' : 'Completed'}</span>
        <time dateTime={run.display_at}>{new Date(run.display_at).toLocaleString()}</time>
      </Link>)}
    </aside>
  </div>
}
