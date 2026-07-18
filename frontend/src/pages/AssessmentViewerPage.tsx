import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { evaluationsApi } from '../api/evaluations'
import { experimentsApi } from '../api/experiments'
import { runsApi } from '../api/runs'
import { AppHeader } from '../components/AppHeader'
import { MathContent, StandaloneEquations } from '../components/MathContent'
import { TokenUsage } from '../components/TokenUsage'
import { useSSE } from '../hooks/useSSE'
import { referencedEquationLabels } from '../math/equationReferences'
import { useRunStore } from '../store/runStore'
import type { CognitiveDemand } from '../types'
import { referencePdfValidationMessages } from '../validation/experimentValidation'

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
  const applyRunSnapshot = useRunStore((state) => state.applyRunSnapshot)
  const addRetriedRun = useRunStore((state) => state.addRetriedRun)
  const selectRun = useRunStore((state) => state.selectRun)
  const [retryDialogOpen, setRetryDialogOpen] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [retryingEvaluation, setRetryingEvaluation] = useState(false)
  const [retryPdfs, setRetryPdfs] = useState<File[]>([])

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
  const viewerReady = experimentRuns.filter(
    (item) => item.viewer_ready_at || item.status === 'complete',
  )
  const selectedId = routeRunId ?? selectedRunId ?? viewerReady[0]?.id
  const selected = selectedId ? runs[selectedId] : undefined

  useEffect(() => {
    if (selectedId && !selected?.assessment) runsApi.get(selectedId).then(mergeRun)
  }, [mergeRun, selected?.assessment, selectedId])
  const receive = useCallback((snapshot: Parameters<typeof applyRunSnapshot>[0]) => {
    applyRunSnapshot(snapshot)
  }, [applyRunSnapshot])
  useSSE(selectedId ?? null, receive)

  useEffect(() => {
    if (!selectedId || selected?.evaluation_status === 'complete') return
    const timer = window.setInterval(() => {
      void runsApi.get(selectedId).then(mergeRun).catch(() => undefined)
    }, 2000)
    return () => window.clearInterval(timer)
  }, [mergeRun, selected?.evaluation_status, selectedId])

  const questions = selected?.assessment?.parsed_json?.questions ?? selected?.generated_json?.questions ?? []
  const condition = selected?.condition ?? experiment?.conditions.find((item) => item.id === selected?.condition_id)
  const evaluationStatus = selected?.evaluation_status === 'failed'
    ? 'Evaluation unavailable'
    : selected?.evaluation_status === 'complete'
      ? 'Evaluation complete'
      : selected?.evaluation_status === 'not_started'
        ? 'Evaluation unavailable'
      : 'Evaluation in progress'

  const retry = async () => {
    if (!selectedId) return
    const pdfBacked = Boolean(selected?.reference_pdf_filenames?.length)
    if (pdfBacked && referencePdfValidationMessages(retryPdfs).length > 0) return
    setRetrying(true)
    try {
      const retried = await runsApi.retry(
        selectedId,
        pdfBacked ? retryPdfs : undefined,
      )
      addRetriedRun({ ...retried, experiment_id: retried.experiment_id ?? id })
      setRetryDialogOpen(false)
      setRetryPdfs([])
      navigate(`/runs/${retried.id}/progress`)
    } finally {
      setRetrying(false)
    }
  }

  const closeRetryDialog = () => {
    setRetryDialogOpen(false)
    setRetryPdfs([])
  }

  const retryEvaluation = async () => {
    if (!selected?.assessment?.id) return
    setRetryingEvaluation(true)
    try {
      const run = await evaluationsApi.retryLlm(selected.assessment.id)
      mergeRun({ ...run, evaluation_status: 'in_progress' })
    } finally {
      setRetryingEvaluation(false)
    }
  }

  return (
    <main className="experiment-page">
      <AppHeader subtitle="Run viewer" />
      <div className="viewer-shell">
        <aside>
          <h2>Runs</h2>
          {viewerReady.map((item) => (
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
              {selected && (
                <span
                  className={`evaluation-status ${selected.evaluation_status ?? 'in_progress'}`}
                  role="status"
                  aria-label="Evaluation status"
                >
                  {evaluationStatus}
                </span>
              )}
            </div>
            {selectedId && (
              <div className="viewer-action-group">
                {selected?.grading_available && selected.grading_question_id && selected.assessment?.id ? (
                  <Link
                    className="primary"
                    to={`/assessments/${selected.assessment.id}/questions/${selected.grading_question_id}/grade`}
                  >
                    Grade Assessment
                  </Link>
                ) : selected?.assessment?.id && (
                  selected.evaluation_status === 'failed'
                  || selected.evaluation_status === 'not_started'
                ) ? (
                  <button
                    className="primary"
                    disabled={retryingEvaluation}
                    onClick={retryEvaluation}
                  >
                    {retryingEvaluation ? 'Retrying LLM Evaluation…' : 'Retry LLM Evaluation'}
                  </button>
                ) : (
                  <button className="primary" disabled>{evaluationStatus}</button>
                )}
                <button
                  className="secondary"
                  disabled={!selected?.artifact_available}
                  onClick={() => selected?.artifact_available && runsApi.exportDocx(selectedId)}
                >
                  {selected?.artifact_available ? 'Export Word document' : 'Preparing document'}
                </button>
                <button className="retry-run-button" onClick={() => { setRetryPdfs([]); setRetryDialogOpen(true) }}>Retry run</button>
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
            {!questions.length && <p>Select a validated run to inspect its questions.</p>}
          </section>
        </article>
      </div>
      {selectedId && <Link className="viewer-back-button" to={`/runs/${selectedId}/progress`}>Back</Link>}
      {retryDialogOpen && <div className="modal-backdrop">
        <div className="incomplete-modal retry-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="retry-dialog-title">
          <h2 id="retry-dialog-title">Retry this run?</h2>
          <p>This creates a new run while preserving the current run and its results.</p>
          {Boolean(selected?.reference_pdf_filenames?.length) && <div className="retry-pdf-input">
            <p><strong>Previously attached:</strong> {selected?.reference_pdf_filenames?.join(', ')}</p>
            <label htmlFor="retry-reference-pdfs">Fresh Reference PDFs</label>
            <input
              id="retry-reference-pdfs"
              type="file"
              accept="application/pdf,.pdf"
              multiple
              aria-invalid={referencePdfValidationMessages(retryPdfs).length > 0 ? 'true' : undefined}
              onChange={(event) => setRetryPdfs(Array.from(event.currentTarget.files ?? []))}
            />
            <small>Maximum 3 PDFs; 20 MB per PDF.</small>
            <small>Please do not upload PDFs longer than 100 pages.</small>
            {retryPdfs.length > 0 && <ol aria-label="Fresh reference PDF selection">
              {retryPdfs.map((pdf, index) => <li key={`${pdf.name}-${pdf.size}-${index}`}>{pdf.name}</li>)}
            </ol>}
            {retryPdfs.length > 0 && referencePdfValidationMessages(retryPdfs)[0] && <span className="error">{referencePdfValidationMessages(retryPdfs)[0]}</span>}
          </div>}
          <div className="retry-dialog-actions">
            <button disabled={retrying} onClick={closeRetryDialog}>Cancel</button>
            <button className="primary" disabled={retrying || (Boolean(selected?.reference_pdf_filenames?.length) && referencePdfValidationMessages(retryPdfs).length > 0)} onClick={retry}>{retrying ? 'Starting retry…' : 'Confirm retry'}</button>
          </div>
        </div>
      </div>}
    </main>
  )
}
