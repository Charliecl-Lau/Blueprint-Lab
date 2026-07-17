import { useCallback, useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { experimentsApi } from '../api/experiments'
import { runsApi } from '../api/runs'
import { AppHeader } from '../components/AppHeader'
import { useSSE } from '../hooks/useSSE'
import { useRunStore } from '../store/runStore'
import type { Stage } from '../types'

const labels: Record<Stage, string> = {
  preparing_prompt: 'Preparing Prompt',
  generating_assessment: 'Generating Assessment',
  validating_assessment: 'Validating Assessment',
  evaluating_quality: 'Evaluating Assessment Quality',
  saving_results: 'Saving Results',
  complete: 'Complete',
  generation_failed: 'Generation Failed',
  evaluation_failed: 'Evaluation Failed',
}

export function ProgressPage() {
  const { runId } = useParams()
  const id = Number(runId)
  const run = useRunStore((state) => state.runs[id])
  const experiment = useRunStore((state) => (
    run?.experiment_id ? state.experiments[run.experiment_id] : undefined
  ))
  const mergeRun = useRunStore((state) => state.mergeRun)
  const mergeExperiment = useRunStore((state) => state.mergeExperiment)
  const applyRunSnapshot = useRunStore((state) => state.applyRunSnapshot)

  useEffect(() => {
    if (!id) return
    let active = true
    runsApi.get(id).then((snapshot) => {
      if (!active) return
      mergeRun(snapshot)
      if (snapshot.experiment_id) {
        experimentsApi.get(snapshot.experiment_id).then((value) => {
          if (active) mergeExperiment(value)
        })
      }
    })
    return () => { active = false }
  }, [id, mergeExperiment, mergeRun])

  const receive = useCallback((snapshot: Parameters<typeof applyRunSnapshot>[0]) => {
    applyRunSnapshot(snapshot)
  }, [applyRunSnapshot])
  useSSE(id || null, receive)

  const condition = experiment?.conditions.find((item) => item.id === run?.condition_id)
  return (
    <main className="experiment-page">
      <AppHeader subtitle="Run progress" />
      <div className="experiment-shell">
        <h1>{experiment?.topic ?? `Run ${id || ''}`}</h1>
        <p>This page reflects the latest persisted state for this run.</p>
        <section>
          <h2>Run status</h2>
          {run ? (
            <article className="generation-card">
              <div>
                <strong>{condition?.condition_code ?? `Condition ${run.condition_id}`} · Run {run.run_number}</strong>
                <small>{condition?.prompt_structure ?? 'Prompt structure unavailable'}</small>
              </div>
              <span className={`status ${run.status}`}>{labels[run.status]}</span>
            </article>
          ) : <p>Loading persisted run state…</p>}
          {run?.error?.message && <p className="error">{run.error.message}</p>}
        </section>
        {run?.status === 'complete' && run.experiment_id && (
          <Link className="primary inline-action" to={`/experiments/${run.experiment_id}/viewer/${run.id}`}>
            Review run
          </Link>
        )}
        <div className="progress-exit">
          <p>This experiment will continue running in the background.</p>
          <Link className="primary" to="/">Back to Control Assessment</Link>
        </div>
      </div>
    </main>
  )
}
