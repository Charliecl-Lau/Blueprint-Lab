import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { runsApi } from '../api/runs'
import { AppHeader } from '../components/AppHeader'
import { Accordion } from '../components/evaluation/Accordion'
import { ActualPromptPanel } from '../components/history/ActualPromptPanel'
import { AssessmentDetailsPanel } from '../components/history/AssessmentDetailsPanel'
import { QuestionsSolutionsPanel } from '../components/history/QuestionsSolutionsPanel'
import type { RunHistoryDetail } from '../types'

export function RunHistoryPage() {
  const { runId } = useParams()
  const id = Number(runId)
  const validId = Number.isInteger(id) && id > 0
  const [history, setHistory] = useState<RunHistoryDetail | null>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'error'>(validId ? 'loading' : 'error')
  const [downloadError, setDownloadError] = useState(false)

  const load = useCallback(() => {
    if (!validId) return
    setState('loading')
    runsApi.historyDetail(id).then(
      (detail) => {
        setHistory(detail)
        setState('ready')
      },
      () => setState('error'),
    )
  }, [id, validId])

  useEffect(() => { load() }, [load])

  if (!validId) return <main className="experiment-page history-page">
    <AppHeader subtitle="Run history" />
    <div className="history-load-state" role="alert">
      <h1>Invalid run history link</h1>
      <Link to="/">Return home</Link>
    </div>
  </main>

  if (state === 'loading') return <main className="experiment-page history-page">
    <AppHeader subtitle="Run history" />
    <div className="history-load-state" role="status">Loading run history...</div>
  </main>

  if (state === 'error' || !history) return <main className="experiment-page history-page">
    <AppHeader subtitle="Run history" />
    <div className="history-load-state" role="alert">
      <h1>Run history could not be loaded.</h1>
      <div className="history-load-actions"><button onClick={load}>Retry</button><Link to="/">Return home</Link></div>
    </div>
  </main>

  const failed = history.display_status === 'failed'
  const firstQuestionId = history.question_ids?.[0]
  const download = async () => {
    setDownloadError(false)
    try {
      await runsApi.exportDocx(history.id)
    } catch {
      setDownloadError(true)
    }
  }

  return <main className={`experiment-page history-page ${history.display_status}`}>
    <AppHeader subtitle="Run history" action={<Link className="secondary" to="/">Return home</Link>} />
    <article className="history-shell">
      <header className="history-page-heading">
        <div>
          <p className="history-eyebrow">Saved run evidence</p>
          <h1>{history.assessment_details.topic}</h1>
          <p>Run {history.run_number}</p>
        </div>
        <span className={`history-status ${history.display_status}`}>
          {failed ? 'Failed' : 'Completed'}
        </span>
      </header>

      {!failed && <div className="history-document-action">
        {history.artifact
          ? <button className="secondary" onClick={download}>Download Word DOCX</button>
          : <button className="secondary" disabled>Word document unavailable</button>}
        {downloadError && <p role="alert">The Word document could not be downloaded.</p>}
      </div>}

      <Accordion title="Assessment Details" defaultExpanded={failed}>
        <AssessmentDetailsPanel details={history.assessment_details} />
      </Accordion>
      <Accordion title="Actual Prompt" defaultExpanded={failed}>
        <ActualPromptPanel prompt={history.actual_prompt} />
      </Accordion>
      {!failed && <>
        <Accordion title="Questions and Solutions" defaultExpanded>
          {history.questions?.length
            ? <QuestionsSolutionsPanel questions={history.questions} />
            : <p>No saved questions are available.</p>}
        </Accordion>
        {firstQuestionId && <Link
          className="primary history-next"
          to={`/runs/${history.id}/history/questions/${firstQuestionId}/evaluation`}
        >Next</Link>}
      </>}
    </article>
  </main>
}
