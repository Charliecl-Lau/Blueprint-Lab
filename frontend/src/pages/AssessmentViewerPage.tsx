import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { experimentsApi } from '../api/experiments'
import { runsApi } from '../api/runs'
import { AppHeader } from '../components/AppHeader'
import { MathContent, StandaloneEquations } from '../components/MathContent'
import { TokenUsage } from '../components/TokenUsage'
import { referencedEquationLabels } from '../math/equationReferences'
import { useRunStore } from '../store/runStore'
import type { CognitiveDemand } from '../types'

const cognitiveDemandLabels: Record<CognitiveDemand, string> = {
  remember_understand: 'Remember/Understand',
  apply_analyze: 'Apply/Analyze',
  evaluate_create: 'Evaluate/Create',
}

export function AssessmentViewerPage() {
  const { experimentId, runId } = useParams()
  const navigate = useNavigate()
  const id = Number(experimentId)
  const routeRunId = Number(runId) || null
  const experiment = useRunStore((state) => state.experiments[id])
  const runs = useRunStore((state) => state.runs)
  const selectedRunId = useRunStore((state) => state.selectedRunId)
  const mergeExperiment = useRunStore((state) => state.mergeExperiment)
  const mergeRun = useRunStore((state) => state.mergeRun)
  const addRetriedRun = useRunStore((state) => state.addRetriedRun)
  const selectRun = useRunStore((state) => state.selectRun)
  const [retryDialogOpen, setRetryDialogOpen] = useState(false)
  const [retrying, setRetrying] = useState(false)

  useEffect(() => {
    if (id) experimentsApi.get(id).then(mergeExperiment)
  }, [id, mergeExperiment])
  useEffect(() => {
    if (routeRunId) runsApi.get(routeRunId).then(mergeRun)
  }, [mergeRun, routeRunId])

  const experimentRunIds = new Set(experiment?.runs.map((item) => item.id) ?? [])
  const experimentRuns = Object.values(runs).filter(
    (item) => item.experiment_id === id || experimentRunIds.has(item.id),
  )
  const complete = experimentRuns.filter((item) => item.status === 'complete')
  const selectedId = routeRunId ?? selectedRunId ?? complete[0]?.id
  const selected = selectedId ? runs[selectedId] : undefined
  useEffect(() => {
    if (selectedId && !selected?.assessment) runsApi.get(selectedId).then(mergeRun)
  }, [mergeRun, selected?.assessment, selectedId])

  const questions = selected?.assessment?.parsed_json?.questions ?? selected?.generated_json?.questions ?? []
  const condition = selected?.condition ?? experiment?.conditions.find((item) => item.id === selected?.condition_id)
  const retry = async () => {
    if (!selectedId) return
    setRetrying(true)
    try {
      const retried = await runsApi.retry(selectedId)
      addRetriedRun({ ...retried, experiment_id: retried.experiment_id ?? id })
      setRetryDialogOpen(false)
      navigate(`/runs/${retried.id}/progress`)
    } finally {
      setRetrying(false)
    }
  }

  return (
    <main className="experiment-page">
      <AppHeader subtitle="Run viewer" />
      <div className="viewer-shell">
        <aside>
          <h2>Runs</h2>
          {complete.map((item) => (
            <button
              className={item.id === selectedId ? 'selected' : ''}
              key={item.id}
              onClick={() => {
                selectRun(item.id)
                navigate(`/experiments/${id}/viewer/${item.id}`)
              }}
            >
              Run {item.run_number}
            </button>
          ))}
        </aside>
        <article>
          <div className="viewer-actions">
            <div>
              <h1>{experiment?.topic ?? 'Assessment'}</h1>
              <p>{condition?.condition_code ?? `Condition ${selected?.condition_id ?? '—'}`} · Run {selected?.run_number ?? '—'}</p>
            </div>
            {selectedId && (
              <div>
                <button className="retry-run-button" onClick={() => setRetryDialogOpen(true)}>Retry run</button>
                <button className="primary" onClick={() => runsApi.exportDocx(selectedId)}>Export Word document</button>
              </div>
            )}
          </div>
          <section>
            <h2>Experiment Condition</h2>
            <p><strong>Course:</strong> {experiment?.course}</p>
            <p><strong>Topic:</strong> {experiment?.topic}</p>
            <p><strong>Estimated student completion time:</strong> {experiment?.estimated_time_minutes} minutes</p>
            {experiment?.cognitive_demand && <p><strong>Cognitive demand:</strong> {cognitiveDemandLabels[experiment.cognitive_demand]}</p>}
            {experiment?.additional_instruction && <p><strong>Additional instruction:</strong> {experiment.additional_instruction}</p>}
            {condition && <div className="condition-factors" aria-label="Condition factors">
              <p className="condition-factor">Concept Bridge = {condition.concept_bridge_enabled ? 'ON' : 'OFF'}</p>
              <p className="condition-factor">Few-shot Examples = {condition.few_shot_enabled ? 'ON' : 'OFF'}</p>
              <p className="condition-factor">Reference Content = {condition.reference_content_enabled ? 'ON' : 'OFF'}</p>
              <p className="condition-factor">Reasoning Guidance = {condition.reasoning_guidance_enabled ? 'ON' : 'OFF'}</p>
            </div>}
            <TokenUsage usage={selected?.token_usage} />
          </section>
          <section>
            <h2>Generated Questions</h2>
            {questions.map((question, index) => {
              const equations = question.equations ?? []
              const referencedLabels = referencedEquationLabels(
                question.body,
                ...question.options?.map((option) => option.body) ?? [],
                question.model_answer,
              )
              return <div className="question" key={question.id ?? index}>
                <strong>{index + 1}. <MathContent text={question.body} segments={question.body_segments} equations={equations} location="question" /></strong>
                {question.options?.map((option, optionIndex) => (
                  <p key={option.id ?? optionIndex}><MathContent text={option.body} segments={option.segments} equations={equations} location="question" />{option.is_correct ? ' ✓' : ''}</p>
                ))}
                <StandaloneEquations equations={equations} location="question" referencedLabels={referencedLabels} />
                {question.model_answer && <p><strong>Solution:</strong> <MathContent text={question.model_answer} segments={question.model_answer_segments} equations={equations} location="solution" /></p>}
                <StandaloneEquations equations={equations} location="solution" referencedLabels={referencedLabels} />
              </div>
            })}
            {!questions.length && <p>Select a completed run to inspect its questions.</p>}
          </section>
        </article>
      </div>
      {selectedId && <Link className="viewer-back-button" to={`/runs/${selectedId}/progress`}>Back</Link>}
      {retryDialogOpen && <div className="modal-backdrop">
        <div className="incomplete-modal retry-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="retry-dialog-title">
          <h2 id="retry-dialog-title">Retry this run?</h2>
          <p>This creates a new run while preserving the current run and its results.</p>
          <div className="retry-dialog-actions">
            <button disabled={retrying} onClick={() => setRetryDialogOpen(false)}>Cancel</button>
            <button className="primary" disabled={retrying} onClick={retry}>{retrying ? 'Starting retry…' : 'Confirm retry'}</button>
          </div>
        </div>
      </div>}
    </main>
  )
}
