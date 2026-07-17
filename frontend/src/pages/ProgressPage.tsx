import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { evaluationsApi } from '../api/evaluations'
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

const pipelineStages = [
  'preparing_prompt',
  'generating_assessment',
  'validating_assessment',
  'evaluating_quality',
  'saving_results',
  'complete',
] as const

type PipelineStage = typeof pipelineStages[number]

function currentPipelineStage(status: Stage, errorType?: string | null): PipelineStage {
  if (status === 'generation_failed') {
    if (errorType === 'assessment_parse_error') return 'validating_assessment'
    if (errorType?.startsWith('actual_prompt')) return 'preparing_prompt'
    return 'generating_assessment'
  }
  if (status === 'evaluation_failed') return 'evaluating_quality'
  return status
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
  const [retryingEvaluation, setRetryingEvaluation] = useState(false)
  const [streamRevision, setStreamRevision] = useState(0)

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
  useSSE(id || null, receive, streamRevision)

  const retryEvaluation = async () => {
    const assessmentId = run?.assessment?.id
    if (!assessmentId) return
    setRetryingEvaluation(true)
    try {
      mergeRun(await evaluationsApi.retryLlm(assessmentId))
      setStreamRevision((value) => value + 1)
    } finally {
      setRetryingEvaluation(false)
    }
  }

  const condition = experiment?.conditions.find((item) => item.id === run?.condition_id)
  const activeStage = run
    ? currentPipelineStage(run.status, run.error?.type)
    : 'preparing_prompt'
  const activeIndex = pipelineStages.indexOf(activeStage)
  const failed = run?.status === 'generation_failed' || run?.status === 'evaluation_failed'

  return (
    <main className="experiment-page">
      <AppHeader subtitle="Run progress" />
      <div className="experiment-shell">
        <h1>{experiment?.topic ?? `Run ${id || ''}`}</h1>
        <p>This page reflects the latest persisted state for this run.</p>
        <section>
          <h2>Run status</h2>
          {run ? <>
            <div className="generation-card">
              <div>
                <strong>{condition?.condition_code ?? `Condition ${run.condition_id}`} · Run {run.run_number}</strong>
                <small>{condition?.prompt_structure ?? 'Prompt structure unavailable'}</small>
              </div>
              <span className={`status ${run.status}`}>{labels[run.status]}</span>
            </div>
            <ol className="pipeline-timeline" aria-label="Assessment generation progress">
              {pipelineStages.map((stage, index) => {
                const state = failed && index === activeIndex
                  ? 'failed'
                  : index < activeIndex
                    ? 'completed'
                    : index === activeIndex
                      ? 'current'
                      : 'pending'
                const stateLabel = state === 'completed'
                  ? 'Completed'
                  : state === 'current'
                    ? 'In progress'
                    : state === 'failed'
                      ? 'Failed'
                      : 'Pending'
                return (
                  <li className={state} key={stage}>
                    <span className="pipeline-marker" aria-hidden="true" />
                    <div>
                      <strong>{labels[stage]}</strong>
                      <small>{stateLabel}</small>
                      {index === activeIndex && run.progress_message && (
                        <p>{run.progress_message}</p>
                      )}
                    </div>
                  </li>
                )
              })}
            </ol>
          </> : <p>Loading persisted run state…</p>}
          {run?.error?.message && <p className="error">{run.error.message}</p>}
        </section>
        <div className="progress-actions">
          {run?.viewer_ready_at && run.experiment_id && (
            <Link className="primary inline-action" to={`/experiments/${run.experiment_id}/viewer/${run.id}`}>
              View Assessment
            </Link>
          )}
          {run?.status === 'evaluation_failed' && run.assessment?.id && (
            <button
              className="secondary inline-action"
              disabled={retryingEvaluation}
              onClick={retryEvaluation}
            >
              {retryingEvaluation ? 'Retrying LLM Evaluation…' : 'Retry LLM Evaluation'}
            </button>
          )}
        </div>
        <div className="progress-exit">
          <p>This experiment will continue running in the background.</p>
          <Link className="primary" to="/">Back to Control Assessment</Link>
        </div>
      </div>
    </main>
  )
}
