import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { runsApi } from '../api/runs'
import type { RecentRun } from '../types'

export function RunProgressShortcut() {
  const [run, setRun] = useState<RecentRun | null>(null)

  useEffect(() => {
    let active = true
    runsApi.recent(1)
      .then((items) => {
        if (active) setRun(Array.isArray(items) ? items[0] ?? null : null)
      })
      .catch(() => { if (active) setRun(null) })
    return () => { active = false }
  }, [])

  if (!run) return null
  return (
    <Link
      className="run-progress-shortcut"
      to={`/runs/${run.id}/progress`}
      aria-label={`Return to run progress: ${run.topic}`}
    >
      View run progress
    </Link>
  )
}
