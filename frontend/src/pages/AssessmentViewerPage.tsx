import { useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { experimentsApi } from '../api/experiments'
import { runsApi } from '../api/runs'
import { useRunStore } from '../store/runStore'

export function AssessmentViewerPage() {
  const { experimentId } = useParams()
  const navigate = useNavigate()
  const id = Number(experimentId)
  const { experiment, runs, selectedRunId, setExperiment, setRun, addRetriedRun, selectRun } = useRunStore()
  useEffect(() => { if (id) experimentsApi.get(id).then(setExperiment) }, [id, setExperiment])
  const complete = Object.values(runs).filter((item) => item.status === 'complete')
  const selectedId = selectedRunId ?? complete[0]?.id
  const selected = selectedId ? runs[selectedId] : undefined
  useEffect(() => { if (selectedId && !selected?.assessment) runsApi.get(selectedId).then(setRun) }, [selectedId, selected?.assessment, setRun])
  const questions = selected?.assessment?.parsed_json?.questions ?? selected?.generated_json?.questions ?? []
  const condition = selected?.condition ?? experiment?.conditions.find((item) => item.id === selected?.condition_id)
  const retry = async () => {
    if (selectedId) addRetriedRun(await runsApi.retry(selectedId))
  }
  return <main className="experiment-page"><header><button onClick={() => navigate(`/experiments/${id}/progress`)}>Back</button><strong>Blueprint Lab</strong><span>Run viewer</span></header><div className="viewer-shell">
    <aside><h2>Runs</h2>{complete.map((item) => <button className={item.id === selectedId ? 'selected' : ''} key={item.id} onClick={() => selectRun(item.id)}>Run {item.run_number}</button>)}</aside>
    <article><div className="viewer-actions"><div><h1>{experiment?.topic ?? 'Assessment'}</h1><p>{condition?.condition_code ?? `Condition ${selected?.condition_id ?? '—'}`} · Run {selected?.run_number ?? '—'} · Prompt structure {condition?.prompt_structure ?? '—'}</p></div>{selectedId && <><button onClick={retry}>Retry run</button><button className="primary" onClick={() => runsApi.exportDocx(selectedId)}>Export Word document</button></>}</div>
      <section><h2>Experiment Condition</h2><p><strong>Course:</strong> {experiment?.course}</p><p><strong>Topic:</strong> {experiment?.topic}</p><p><strong>Estimated student completion time:</strong> {experiment?.estimated_time_minutes} minutes</p><p><strong>Condition:</strong> {condition?.condition_label}</p><details><summary>Prompt and factor metadata</summary><pre>{JSON.stringify(condition?.factor_inputs ?? {}, null, 2)}</pre><p>{selected?.prompt?.text ?? selected?.prompt_text}</p></details></section>
      <section><h2>Generated Questions</h2>{questions.map((question, index) => <div className="question" key={question.id ?? index}><strong>{index + 1}. {question.body}</strong>{question.options?.map((option, optionIndex) => <p key={option.id ?? optionIndex}>{option.body}{option.is_correct ? ' ✓' : ''}</p>)}{question.model_answer && <p><strong>Solution:</strong> {question.model_answer}</p>}</div>)}{!questions.length && <p>Select a completed run to inspect its questions.</p>}</section>
    </article>
  </div></main>
}
