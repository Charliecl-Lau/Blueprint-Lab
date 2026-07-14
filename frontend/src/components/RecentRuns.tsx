import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { runsApi } from '../api/runs'
import type { RecentRun } from '../types'

const ACTIVE = new Set(['pending', 'prompting', 'generating', 'documenting'])

export function RecentRuns() {
  const [runs, setRuns] = useState<RecentRun[]>([])

  useEffect(() => {
    let active = true
    runsApi.recent(10)
      .then((items) => { if (active && Array.isArray(items)) setRuns(items) })
      .catch(() => { if (active) setRuns([]) })
    return () => { active = false }
  }, [])

  if (runs.length === 0) return null
  return (
    <section className="recent-runs" aria-labelledby="recent-runs-title">
      <h2 id="recent-runs-title">Recent runs</h2>
      <div>
        {runs.map((run) => {
          const target = ACTIVE.has(run.status)
            ? `/runs/${run.id}/progress`
            : `/experiments/${run.experiment_id}/viewer/${run.id}`
          return (
            <article key={run.id}>
              <div>
                <strong>{run.topic}</strong>
                <span>{run.condition_label} · Run {run.run_number}</span>
              </div>
              <Link to={target} aria-label={`Reopen run ${run.run_number}: ${run.topic}`}>
                Reopen
              </Link>
            </article>
          )
        })}
      </div>
    </section>
  )
}
