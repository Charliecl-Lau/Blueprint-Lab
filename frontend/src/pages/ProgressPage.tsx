import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { experimentsApi } from '../api/experiments'
import { runsApi } from '../api/runs'
import { AppHeader } from '../components/AppHeader'
import { useSSE } from '../hooks/useSSE'
import { isTerminalRunStatus, useRunStore } from '../store/runStore'
import type { Stage } from '../types'

const labels: Record<Stage, string> = {
  pending: 'Queued',
  prompting: 'Generating prompt',
  generating: 'Generating questions',
  docx_authoring: 'Authoring Word document',
  docx_executing: 'Building Word document in sandbox',
  docx_validating: 'Verifying Word document',
  docx_repairing: 'Repairing Word document',
  rewrite_failed: 'Word rewrite failed',
  documenting: 'Building Word document',
  complete: 'Complete',
  complete_with_warnings: 'Completed with warnings',
  error: 'Failed',
}

const agenticLabels: Partial<Record<Stage, string>> = {
  docx_authoring: 'Gemini is designing the Word document',
  docx_executing: 'Applying document operations',
  docx_validating: 'Rendering and verifying the Word document',
  docx_repairing: 'Gemini is revising the rendered document',
  complete: 'Verified canonical document available',
  rewrite_failed: 'Original document remains available',
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
  const [recovering, setRecovering] = useState(false)
  const [retryingRewrite, setRetryingRewrite] = useState(false)

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

  const runStatus = run?.status
  useEffect(() => {
    if (!id || !runStatus || isTerminalRunStatus(runStatus)) return
    const timer = window.setInterval(() => {
      void runsApi.get(id).then(mergeRun).catch(() => undefined)
    }, 2000)
    return () => window.clearInterval(timer)
  }, [id, mergeRun, runStatus])

  const condition = experiment?.conditions.find((item) => item.id === run?.condition_id)
  const statusLabel = run
    ? (run.rewrite?.backend === 'agentic_tools' ? agenticLabels[run.status] : undefined) ?? labels[run.status]
    : undefined
  const recoverAssessment = async () => {
    if (!run || !id) return
    setRecovering(true)
    try {
      mergeRun(await runsApi.recoverAssessment(id))
    } finally {
      setRecovering(false)
    }
  }
  const retryDocxRewrite = async () => {
    if (!run || !id || !run.rewrite?.repair_available) return
    setRetryingRewrite(true)
    try {
      mergeRun(await runsApi.retryDocxRewrite(id, crypto.randomUUID()))
    } finally {
      setRetryingRewrite(false)
    }
  }
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
              <span className={`status ${run.status}`}>{statusLabel}</span>
            </article>
          ) : <p>Loading persisted run state…</p>}
          {run?.error?.message && <p className="error">{run.error.message}</p>}
          {run?.progress_message && run.progress_message !== statusLabel && (
            <p className="progress-message">{run.progress_message}</p>
          )}
        </section>
        {(run?.status === 'complete' || run?.status === 'complete_with_warnings') && run.experiment_id && (
          <Link className="primary inline-action" to={`/experiments/${run.experiment_id}/viewer/${run.id}`}>
            View Assessment
          </Link>
        )}
        {run?.status === 'rewrite_failed' && run.experiment_id && (
          <section className="assessment-warning" role="alert">
            <h2>Original assessment remains available</h2>
            <p>The Word rewrite failed. Review the preserved original assessment and safe failure summary.</p>
            <Link className="primary inline-action" to={`/experiments/${run.experiment_id}/viewer/${run.id}`}>
              View original assessment
            </Link>
            {run.rewrite?.repair_available && (
              <button className="secondary inline-action" disabled={retryingRewrite} onClick={retryDocxRewrite}>
                {retryingRewrite ? 'Retrying Word rewrite...' : 'Retry Word rewrite'}
              </button>
            )}
          </section>
        )}
        {run?.status === 'error' && run.error?.type === 'assessment_parse_error' && (
          <button className="primary inline-action" disabled={recovering} onClick={recoverAssessment}>
            {recovering ? 'Recovering assessment...' : 'Recover saved assessment'}
          </button>
        )}
        <div className="progress-exit">
          <p>This experiment will continue running in the background.</p>
          <Link className="primary" to="/">Back to Control Assessment</Link>
        </div>
      </div>
    </main>
  )
}
