import { useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { experimentsApi } from '../api/experiments'
import { generationsApi } from '../api/generations'
import { useRunStore } from '../store/runStore'

export function AssessmentViewerPage() {
  const { experimentId } = useParams()
  const navigate = useNavigate()
  const id = Number(experimentId)
  const { experiment, generations, selectedGenerationId, setExperiment, setGeneration, selectGeneration } = useRunStore()
  useEffect(() => { if (id) experimentsApi.get(id).then(setExperiment) }, [id, setExperiment])
  const complete = Object.values(generations).filter((item) => item.status === 'complete')
  const selectedId = selectedGenerationId ?? complete[0]?.id
  const selected = selectedId ? generations[selectedId] : undefined
  useEffect(() => { if (selectedId && !selected?.generated_json) generationsApi.get(selectedId).then(setGeneration) }, [selectedId, selected?.generated_json, setGeneration])
  const questions = selected?.generated_json?.questions ?? []
  const condition = selected?.condition ?? experiment?.conditions.find((item) => item.id === selected?.condition_id)
  return <main className="experiment-page"><header><button onClick={() => navigate(`/experiments/${id}/progress`)}>Back</button><strong>Blueprint Lab</strong><span>Generation viewer</span></header><div className="viewer-shell">
    <aside><h2>Generations</h2>{complete.map((item) => <button className={item.id === selectedId ? 'selected' : ''} key={item.id} onClick={() => selectGeneration(item.id)}>Generation {item.id}</button>)}</aside>
    <article><div className="viewer-actions"><div><h1>{experiment?.topic ?? 'Assessment'}</h1><p>Assessment ID {selected?.id ?? '—'} · Prompt structure {condition?.prompt_structure ?? '—'}</p></div>{selectedId && <><button onClick={() => generationsApi.regenerate(selectedId)}>Regenerate</button><button className="primary" onClick={() => generationsApi.exportDocx(selectedId)}>Export Word document</button></>}</div>
      <section><h2>Experiment Condition</h2><p><strong>Course:</strong> {experiment?.course}</p><p><strong>Topic:</strong> {experiment?.topic}</p><p><strong>Estimated student completion time:</strong> {experiment?.estimated_time_minutes} minutes</p><p><strong>Condition:</strong> {condition?.condition_label}</p><details><summary>Prompt and factor metadata</summary><pre>{JSON.stringify(condition?.factor_inputs ?? {}, null, 2)}</pre><p>{selected?.prompt_text}</p></details></section>
      <section><h2>Generated Questions</h2>{questions.map((question, index) => <div className="question" key={question.id ?? index}><strong>{index + 1}. {question.body}</strong>{question.options?.map((option, optionIndex) => <p key={option.id ?? optionIndex}>{option.body}{option.is_correct ? ' ✓' : ''}</p>)}{question.model_answer && <p><strong>Solution:</strong> {question.model_answer}</p>}</div>)}{!questions.length && <p>Select a completed generation to inspect its questions.</p>}</section>
    </article>
  </div></main>
}
