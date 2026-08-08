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

const activityMessages: Partial<Record<Stage, string[]>> = {
  pending: ['Waiting for generation to begin…'],
  prompting: [
    'Preparing the assessment instructions…',
    'Organizing the provided requirements…',
  ],
  generating: [
    'Structuring the assessment…',
    'Preparing questions and solutions…',
  ],
  documenting: [
    'Formatting the assessment content…',
    'Building the document structure…',
  ],
  docx_authoring: [
    'Formatting the assessment content…',
    'Building the document structure…',
  ],
  docx_executing: [
    'Applying document formatting…',
    'Assembling the Word document…',
  ],
  docx_validating: [
    'Checking document structure…',
    'Confirming the document is ready…',
  ],
  docx_repairing: [
    'Correcting document issues…',
    'Preparing the revised document…',
  ],
}

function formatElapsed(totalSeconds: number) {
  const seconds = Math.max(0, Math.floor(totalSeconds))
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
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
  const [activityState, setActivityState] = useState<{ stage?: Stage, index: number }>({ index: 0 })
  const [now, setNow] = useState(() => Date.now())

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
  const terminal = runStatus ? isTerminalRunStatus(runStatus) : false
  useEffect(() => {
    if (!id || !runStatus || isTerminalRunStatus(runStatus)) return
    const timer = window.setInterval(() => {
      void runsApi.get(id).then(mergeRun).catch(() => undefined)
    }, 2000)
    return () => window.clearInterval(timer)
  }, [id, mergeRun, runStatus])

  const messages = runStatus ? activityMessages[runStatus] : undefined
  useEffect(() => {
    if (terminal || !messages || messages.length < 2) return
    let timer: number
    const rotate = () => {
      setActivityState((current) => ({
        stage: runStatus,
        index: current.stage === runStatus ? (current.index + 1) % messages.length : 1,
      }))
      timer = window.setTimeout(rotate, 10000)
    }
    timer = window.setTimeout(rotate, 10000)
    return () => window.clearTimeout(timer)
  }, [messages, runStatus, terminal])

  useEffect(() => {
    if (terminal || !run?.started_at) return
    let timer: number
    const tick = () => {
      setNow(Date.now())
      timer = window.setTimeout(tick, 1000)
    }
    timer = window.setTimeout(tick, 1000)
    return () => window.clearTimeout(timer)
  }, [run?.started_at, terminal])

  const condition = experiment?.conditions.find((item) => item.id === run?.condition_id)
  const statusLabel = run
    ? (run.rewrite?.backend === 'agentic_tools' ? agenticLabels[run.status] : undefined) ?? labels[run.status]
    : undefined
  const activityIndex = activityState.stage === runStatus ? activityState.index : 0
  const activityMessage = messages?.[activityIndex % messages.length]
  const elapsedSeconds = run?.started_at
    ? Math.max(0, (now - new Date(run.started_at).getTime()) / 1000)
    : null
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
          {run && !terminal && activityMessage && (
            <div className="active-progress">
              <p className="activity-message" aria-live="polite" aria-atomic="true">
                {activityMessage}
              </p>
              <p className="elapsed-time">
                {elapsedSeconds === null ? 'Working' : `Working · ${formatElapsed(elapsedSeconds)} elapsed`}
              </p>
              <p className="progress-reassurance">
                {elapsedSeconds !== null && elapsedSeconds >= 120
                  ? 'Still working. Complex assessments may take several minutes.'
                  : 'This can take several minutes. You may leave this page; work will continue in the background.'}
              </p>
            </div>
          )}
          {run?.progress_message
            && run.progress_message !== statusLabel
            && run.progress_message !== activityMessage && (
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
