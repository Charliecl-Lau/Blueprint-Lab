import { useCallback, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { experimentsApi } from '../api/experiments'
import { useSSE } from '../hooks/useSSE'
import { useRunStore } from '../store/runStore'
import type { Stage } from '../types'

const labels: Record<Stage, string> = { pending: 'Queued', prompting: 'Generating prompt', generating: 'Generating questions', documenting: 'Building Word document', complete: 'Complete', error: 'Failed' }

export function ProgressPage() {
  const { experimentId } = useParams()
  const navigate = useNavigate()
  const id = Number(experimentId)
  const { experiment, runs, setExperiment, applySSEEvent } = useRunStore()
  useEffect(() => { if (id) experimentsApi.get(id).then(setExperiment) }, [id, setExperiment])
  const receive = useCallback(applySSEEvent, [applySSEEvent])
  useSSE(id || null, receive)
  const list = Object.values(runs)
  const complete = list.filter((item) => item.status === 'complete').length
  return <main className="experiment-page"><header><strong>Blueprint Lab</strong><span>Experiment progress</span></header><div className="experiment-shell">
    <h1>{experiment?.topic ?? 'Running experiment'}</h1><p>{complete} of {list.length} runs complete</p>
    <section><h2>Runs</h2>{list.map((run) => {
      const condition = run.condition ?? experiment?.conditions.find((item) => item.id === run.condition_id)
      return <article className="generation-card" key={run.id}><div><strong>{condition?.condition_code ?? `Condition ${run.condition_id}`} · Run {run.run_number}</strong><small>{condition?.prompt_structure ?? 'Prompt structure unavailable'}</small></div><span className={`status ${run.status}`}>{labels[run.status]}</span></article>
    })}{!list.length && <p>Loading run conditions…</p>}</section>
    {complete > 0 && <button className="primary" onClick={() => navigate(`/experiments/${id}/viewer`)}>Review runs</button>}
  </div></main>
}
