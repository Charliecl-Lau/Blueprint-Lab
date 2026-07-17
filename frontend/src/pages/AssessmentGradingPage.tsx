import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { evaluationsApi } from '../api/evaluations'
import { AppHeader } from '../components/AppHeader'
import { Accordion } from '../components/evaluation/Accordion'
import { EvaluationComparisonPanel } from '../components/evaluation/EvaluationComparisonPanel'
import { HumanEvaluationSummary } from '../components/evaluation/HumanEvaluationSummary'
import { LLMEvaluationPanel } from '../components/evaluation/LLMEvaluationPanel'
import { RubricCriterionCard } from '../components/evaluation/RubricCriterionCard'
import { criterionKeys } from '../evaluation/rubric'
import { useHumanEvaluationDraft } from '../hooks/useHumanEvaluationDraft'
import type { EvaluationComparison, GradingContext } from '../types'

const llmBiasNotice = 'Complete the human assessment before reviewing the LLM evaluation to reduce scoring bias.'

export function AssessmentGradingPage() {
  const { assessmentId, questionId } = useParams()
  return <AssessmentGradingLoader key={questionId} assessmentId={assessmentId} questionId={questionId} />
}

function AssessmentGradingLoader({
  assessmentId,
  questionId,
}: {
  assessmentId?: string
  questionId?: string
}) {
  const assessmentNumber = Number(assessmentId)
  const questionNumber = Number(questionId)
  const [context, setContext] = useState<GradingContext | null>(null)
  const [loadError, setLoadError] = useState<string | null>(
    questionNumber ? null : 'The grading link does not contain a valid question.',
  )
  const [comparison, setComparison] = useState<EvaluationComparison | null>(null)
  const [comparisonLoading, setComparisonLoading] = useState(false)
  const openedLlmForEvaluation = useRef<Set<number>>(new Set())

  useEffect(() => {
    let active = true
    if (!questionNumber) return () => { active = false }
    evaluationsApi.gradingContext(questionNumber).then(
      (value) => { if (active) setContext(value) },
      (cause) => { if (active) setLoadError(cause instanceof Error ? cause.message : 'Unable to load this assessment.') },
    )
    return () => { active = false }
  }, [questionNumber])

  const human = useHumanEvaluationDraft(context?.human_evaluation ?? null)
  const draft = human.draft
  const finalized = draft?.status === 'finalized'
  const hasAllScores = criterionKeys.every((key) => (
    draft?.criteria.some((criterion) => criterion.criterion_key === key && criterion.score != null)
  ))

  const openLlm = (expanded: boolean) => {
    if (!expanded || !draft || !context) return
    if (openedLlmForEvaluation.current.has(draft.id)) return
    openedLlmForEvaluation.current.add(draft.id)
    void evaluationsApi.recordLlmAccess(draft.id, context.llm_evaluation.id).catch(() => {
      openedLlmForEvaluation.current.delete(draft.id)
    })
  }

  const openComparison = (expanded: boolean) => {
    if (!expanded || comparison || comparisonLoading || !finalized) return
    setComparisonLoading(true)
    evaluationsApi.comparison(questionNumber).then(setComparison).finally(() => setComparisonLoading(false))
  }

  if (loadError) {
    return (
      <main className="experiment-page">
        <AppHeader subtitle="Assessment grading" />
        <div className="grading-shell"><section className="grading-load-state" role="alert"><h1>Unable to load assessment grading</h1><p>{loadError}</p></section></div>
      </main>
    )
  }
  if (!context || !draft) {
    return (
      <main className="experiment-page">
        <AppHeader subtitle="Assessment grading" />
        <div className="grading-shell"><p className="grading-load-state" role="status">Loading assessment grading...</p></div>
      </main>
    )
  }

  const questionTitle = context.question.metadata?.question_title ?? `Assessment question ${questionNumber}`
  const gradePath = (targetQuestionId: number) => `/assessments/${assessmentNumber}/questions/${targetQuestionId}/grade`
  const statusLabel = draft.status === 'finalized'
    ? 'Finalized'
    : draft.status === 'reopened'
      ? 'Reopened'
      : 'Draft'
  const locked = draft.status === 'finalized'

  return (
    <main className="experiment-page grading-page">
      <AppHeader subtitle="Assessment grading" />
      <div className="grading-shell">
        <header className="grading-page-header">
          <div>
            <p className="evaluation-eyebrow">Human assessment</p>
            <h1>{questionTitle}</h1>
            <span className={`status ${draft.status}`}>{statusLabel}</span>
          </div>
          <nav className="grading-navigation" aria-label="Assessment grading navigation">
            <button className="secondary" type="button" onClick={() => human.navigateWithConfirmation(context.viewer_path)}>Return to Assessment Viewer</button>
            <button className="secondary" type="button" disabled={!context.previous_question_id} onClick={() => context.previous_question_id && human.navigateWithConfirmation(gradePath(context.previous_question_id))}>Previous Assessment</button>
            <button className="secondary" type="button" disabled={!context.next_question_id} onClick={() => context.next_question_id && human.navigateWithConfirmation(gradePath(context.next_question_id))}>Next Assessment</button>
          </nav>
        </header>

        <Accordion
          title="View LLM Assessment"
          notice={llmBiasNotice}
          onExpandedChange={openLlm}
        >
          <LLMEvaluationPanel evaluation={context.llm_evaluation} />
        </Accordion>

        <Accordion title="Human Assessment" defaultExpanded>
          <div className="human-evaluation-intro">
            <div>
              <h2>Grade with the Assessment Quality Rubric</h2>
              <p>Score every dimension from 1 to 5. Comments, suggested modifications, and issue flags are optional.</p>
            </div>
            <span className="rubric-version">Rubric {context.rubric.version}</span>
          </div>
          <div className="rubric-card-list">
            {context.rubric.criteria.map((rubric) => (
              <RubricCriterionCard
                key={rubric.key}
                rubric={rubric}
                value={draft.criteria.find((criterion) => criterion.criterion_key === rubric.key)}
                disabled={locked}
                onChange={human.updateCriterion}
                onBlur={() => { void human.saveNow().catch(() => undefined) }}
              />
            ))}
          </div>
          <HumanEvaluationSummary
            evaluation={draft}
            disabled={locked}
            onOverallChange={human.updateOverall}
            onBlur={() => { void human.saveNow().catch(() => undefined) }}
          />
          {human.error && <p className="grading-save-error" role="alert">{human.error}</p>}
          <div className="grading-actions">
            {locked ? (
              <button className="primary" type="button" onClick={() => { void human.reopen() }}>Reopen Evaluation</button>
            ) : (
              <>
                <button className="secondary" type="button" disabled={!human.dirty || human.saving} onClick={() => { void human.saveNow() }}>{human.saving ? 'Saving...' : 'Save Draft'}</button>
                <button className="primary" type="button" disabled={!hasAllScores || human.saving} onClick={() => { void human.finalize() }}>Finalize Human Assessment</button>
                <button className="secondary" type="button" disabled={!human.dirty} onClick={human.resetUnsaved}>Reset Unsaved Changes</button>
              </>
            )}
            <span className="save-state" role="status">{human.saving ? 'Saving draft...' : human.dirty ? 'Unsaved changes' : 'All changes saved'}</span>
          </div>
        </Accordion>

        <Accordion
          title="Compare Human and LLM Results"
          disabled={!finalized}
          notice={!finalized ? 'Finalize the human assessment to enable comparison.' : undefined}
          onExpandedChange={openComparison}
        >
          {comparisonLoading && <p role="status">Loading comparison...</p>}
          {comparison && <EvaluationComparisonPanel comparison={comparison} rubric={context.rubric} />}
        </Accordion>
      </div>
    </main>
  )
}
