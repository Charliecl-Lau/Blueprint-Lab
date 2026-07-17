import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { runsApi } from '../api/runs'
import { useRunStore } from '../store/runStore'
import type { RecentRun } from '../types'

const ACTIVE = new Set([
  'preparing_prompt',
  'generating_assessment',
  'validating_assessment',
  'evaluating_quality',
  'saving_results',
])

export function RunProgressShortcut() {
  const runs = useRunStore((state) => state.runs)
  const experiments = useRunStore((state) => state.experiments)
  const storedRun = Object.values(runs)
    .filter((item) => ACTIVE.has(item.status))
    .sort((left, right) => right.id - left.id)[0]
  const storedShortcut = storedRun
    ? {
        id: storedRun.id,
        topic: experiments[storedRun.experiment_id ?? -1]?.topic ?? `Run ${storedRun.id}`,
      }
    : null
  const storedRunId = storedShortcut?.id
  const [recentRun, setRecentRun] = useState<RecentRun | null>(null)

  useEffect(() => {
    if (storedRunId) return
    let active = true
    runsApi.recent(10)
      .then((items) => {
        if (!active || !Array.isArray(items)) return
        setRecentRun(items.find((item) => ACTIVE.has(item.status)) ?? items[0] ?? null)
      })
      .catch(() => { if (active) setRecentRun(null) })
    return () => { active = false }
  }, [storedRunId])

  const run = storedShortcut ?? recentRun
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
