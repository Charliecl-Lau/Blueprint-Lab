import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { evaluationsApi } from '../api/evaluations'
import { AppHeader } from '../components/AppHeader'
import { Accordion } from '../components/evaluation/Accordion'
import { EvaluationComparisonPanel } from '../components/evaluation/EvaluationComparisonPanel'
import { LLMEvaluationPanel } from '../components/evaluation/LLMEvaluationPanel'
import { ReadOnlyHumanEvaluationPanel } from '../components/history/ReadOnlyHumanEvaluationPanel'
import type { HistoryEvaluationContext } from '../types'

export function RunHistoryEvaluationPage() {
  const { runId, questionId } = useParams()
  const navigate = useNavigate()
  const runNumber = Number(runId)
  const questionNumber = Number(questionId)
  const [context, setContext] = useState<HistoryEvaluationContext | null>(null)
  const [error, setError] = useState<string | null>(
    questionNumber ? null : 'Evaluation history was not found.',
  )

  const requestHistory = useCallback(() => {
    if (!questionNumber) return
    evaluationsApi.historyContext(questionNumber).then(
      setContext,
      (cause: Error & { status?: number }) => {
        if (cause.status === 409 && runNumber) {
          navigate(`/runs/${runNumber}/history`, { replace: true })
        } else {
          setError(cause.message || 'Evaluation history could not be loaded.')
        }
      },
    )
  }, [navigate, questionNumber, runNumber])

  useEffect(requestHistory, [requestHistory])

  const retry = () => {
    setError(null)
    setContext(null)
    requestHistory()
  }

  const historyPath = context?.history_path ?? (runNumber ? `/runs/${runNumber}/history` : '/')

  if (error) return <main className="experiment-page grading-page history-evaluation-page">
    <AppHeader subtitle="Run history evaluation" />
    <div className="grading-shell"><section className="grading-load-state" role="alert">
      <h1>Evaluation history could not be loaded.</h1>
      <p>{error}</p>
      <div className="history-load-actions"><button type="button" onClick={retry}>Retry</button><Link to={historyPath}>Return to Run History</Link></div>
    </section></div>
  </main>

  if (!context) return <main className="experiment-page grading-page history-evaluation-page">
    <AppHeader subtitle="Run history evaluation" />
    <div className="grading-shell"><p className="grading-load-state" role="status">Loading evaluation history...</p></div>
  </main>

  const questionTitle = context.question.metadata?.question_title ?? `Assessment question ${questionNumber}`
  const evaluationPath = (targetQuestionId: number) => (
    `/runs/${context.run_id}/history/questions/${targetQuestionId}/evaluation`
  )

  return <main className="experiment-page grading-page history-evaluation-page">
    <AppHeader subtitle="Run history evaluation" />
    <div className="grading-shell">
      <header className="grading-page-header">
        <div>
          <p className="evaluation-eyebrow">Saved evaluation evidence</p>
          <h1>{questionTitle}</h1>
          <span className="status finalized">Finalized history</span>
        </div>
        <nav className="grading-navigation" aria-label="Run history evaluation navigation">
          <Link className="secondary" to={context.history_path}>Return to Run History</Link>
          {context.previous_question_id
            ? <Link className="secondary" to={evaluationPath(context.previous_question_id)}>Previous Assessment</Link>
            : <span className="secondary disabled" aria-disabled="true">Previous Assessment</span>}
          {context.next_question_id
            ? <Link className="secondary" to={evaluationPath(context.next_question_id)}>Next Assessment</Link>
            : <span className="secondary disabled" aria-disabled="true">Next Assessment</span>}
        </nav>
      </header>

      <Accordion title="View LLM Assessment">
        <LLMEvaluationPanel evaluation={context.llm_evaluation} />
      </Accordion>

      <Accordion title="Human Assessment" defaultExpanded>
        <ReadOnlyHumanEvaluationPanel evaluation={context.human_evaluation} rubric={context.rubric} />
      </Accordion>

      <Accordion
        title="Compare Human and LLM Results"
        disabled={!context.comparison}
        notice={!context.comparison ? 'Human evaluation not completed' : undefined}
      >
        {context.comparison && <EvaluationComparisonPanel comparison={context.comparison} rubric={context.rubric} />}
      </Accordion>
    </div>
  </main>
}
