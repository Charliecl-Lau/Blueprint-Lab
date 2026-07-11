import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { experimentsApi } from '../api/experiments'
import { PROMPT_FACTORS, PromptFactorFields, type FactorKey } from '../components/PromptFactorFields'
import { useRunStore } from '../store/runStore'
import type { AssessmentType, PromptStructure } from '../types'

type Section = 'details' | 'factors' | 'review'
const sections: { id: Section; label: string; subtitle: string }[] = [
  { id: 'details', label: 'Assessment Details', subtitle: 'Define the course and assessment requirements.' },
  { id: 'factors', label: 'Prompt Design Factors', subtitle: 'Select experimental factors and provide their content.' },
  { id: 'review', label: 'Review', subtitle: 'Check the condition before running the experiment.' },
]
const factorLabels = Object.fromEntries(PROMPT_FACTORS.map((factor) => [factor.key, factor.label.replace(' (chain-of-thought condition)', '')])) as Record<FactorKey, string>
const initialEnabled: Record<FactorKey, boolean> = { conceptBridge: false, fewShot: false, referenceContent: false, reasoningGuidance: false }
const initialContent: Record<FactorKey, string> = { conceptBridge: '', fewShot: '', referenceContent: '', reasoningGuidance: '' }

export function InputPanelPage() {
  const navigate = useNavigate(), reset = useRunStore((state) => state.reset)
  const [section, setSection] = useState<Section>('details')
  const [course, setCourse] = useState(''), [topic, setTopic] = useState(''), [objectives, setObjectives] = useState('')
  const [assessmentType, setAssessmentType] = useState<AssessmentType>('mixed'), [difficulty, setDifficulty] = useState('mixed')
  const [questionCount, setQuestionCount] = useState('4'), [estimatedTime, setEstimatedTime] = useState('30')
  const [promptStructure, setPromptStructure] = useState<PromptStructure>('openai')
  const [enabled, setEnabled] = useState(initialEnabled), [content, setContent] = useState(initialContent)
  const [errors, setErrors] = useState<Record<string, string>>({}), [missing, setMissing] = useState<{ section: Section; label: string }[]>([])
  const [loading, setLoading] = useState(false)

  const validate = () => {
    const next: Record<string, string> = {}, absent: { section: Section; label: string }[] = []
    const required = (key: string, value: string, label: string) => { if (!value.trim()) { next[key] = `${label} is required.`; absent.push({ section: 'details', label }) } }
    required('course', course, 'Course name'); required('topic', topic, 'Topic'); required('objectives', objectives, 'Learning objectives')
    const questions = Number(questionCount), minutes = Number(estimatedTime)
    if (!Number.isInteger(questions) || questions < 1 || questions > 50) { next.questionCount = 'Enter 1 to 50 questions.'; absent.push({ section: 'details', label: 'Number of questions' }) }
    if (!Number.isInteger(minutes) || minutes < 1 || minutes > 480) { next.estimatedTime = 'Enter 1 to 480 minutes.'; absent.push({ section: 'details', label: 'Estimated student completion time' }) }
    for (const key of Object.keys(enabled) as FactorKey[]) if (enabled[key] && !content[key].trim()) { next[key] = `Add content for ${factorLabels[key]}.`; absent.push({ section: 'factors', label: `${factorLabels[key]} content` }) }
    setErrors(next); setMissing(absent)
    return { valid: absent.length === 0, questions, minutes }
  }

  const submit = async () => {
    const result = validate(); if (!result.valid) return
    setLoading(true)
    try {
      reset()
      const experiment = await experimentsApi.create({
        course: course.trim(), topic: topic.trim(), learning_objectives: objectives.trim(), assessment_type: assessmentType, difficulty,
        number_of_questions: result.questions, estimated_time_minutes: result.minutes, prompt_structure: promptStructure,
        factors: { concept_bridge: enabled.conceptBridge, few_shot: enabled.fewShot, reference_content: enabled.referenceContent, reasoning_guidance: enabled.reasoningGuidance },
        factor_inputs: { ...(enabled.conceptBridge && { concept_bridge: content.conceptBridge.trim() }), ...(enabled.fewShot && { few_shot: content.fewShot.trim() }), ...(enabled.referenceContent && { reference_content: content.referenceContent.trim() }), ...(enabled.reasoningGuidance && { reasoning_guidance: content.reasoningGuidance.trim() }) },
      })
      navigate(`/experiments/${experiment.id}/progress`)
    } catch (error) { setErrors({ submit: error instanceof Error ? error.message : 'Unable to run experiment.' }) }
    finally { setLoading(false) }
  }

  const index = sections.findIndex((item) => item.id === section), current = sections[index]
  const goToMissing = (item: { section: Section }) => { setSection(item.section); setMissing([]) }
  return <main className="experiment-page wizard-page">
    <header><strong>Blueprint Lab</strong><span>Controlled assessment research</span></header>
    <div className="wizard-layout">
      <nav aria-label="Experiment sections" className="wizard-nav"><h1 className="nav-eyebrow">New Experiment</h1>{sections.map((item, itemIndex) => <button aria-label={item.label} key={item.id} className={section === item.id ? 'active' : ''} onClick={() => setSection(item.id)}><span>{itemIndex + 1}</span><div><strong>{item.label}</strong><small>{item.subtitle}</small></div></button>)}</nav>
      <div className="wizard-content"><div className="section-heading"><h2>{section === 'review' ? 'Review Experiment' : current.label}</h2><p>{current.subtitle}</p></div>
        {section === 'details' && <section className="section-card"><div className="form-grid">
          <label>Course name<input value={course} onChange={(e) => setCourse(e.target.value)} />{errors.course && <em>{errors.course}</em>}</label><label>Topic<input value={topic} onChange={(e) => setTopic(e.target.value)} />{errors.topic && <em>{errors.topic}</em>}</label>
          <label className="wide">Learning objectives<textarea rows={3} value={objectives} onChange={(e) => setObjectives(e.target.value)} />{errors.objectives && <em>{errors.objectives}</em>}</label>
          <label>Assessment format<select value={assessmentType} onChange={(e) => setAssessmentType(e.target.value as AssessmentType)}><option value="mcq">Multiple choice</option><option value="short_answer">Short answer</option><option value="mixed">Mixed</option></select></label>
          <label>Difficulty<select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option><option value="mixed">Mixed</option></select></label>
          <label>Number of questions<input type="number" min="1" max="50" value={questionCount} onChange={(e) => setQuestionCount(e.target.value)} />{errors.questionCount && <em>{errors.questionCount}</em>}</label>
          <label>Estimated student completion time<input aria-label="Estimated student completion time" type="number" min="1" max="480" value={estimatedTime} onChange={(e) => setEstimatedTime(e.target.value)} /><small>Minutes, distinct from generation time.</small>{errors.estimatedTime && <em>{errors.estimatedTime}</em>}</label>
          <label>Prompt structure<select value={promptStructure} onChange={(e) => setPromptStructure(e.target.value as PromptStructure)}><option value="openai">OpenAI</option><option value="anthropic">Anthropic</option></select></label>
        </div></section>}
        {section === 'factors' && <section className="section-card"><PromptFactorFields enabled={enabled} content={content} errors={errors} onToggle={(key) => setEnabled((value) => ({ ...value, [key]: !value[key] }))} onContent={(key, value) => setContent((currentContent) => ({ ...currentContent, [key]: value }))} /></section>}
        {section === 'review' && <section className="section-card"><dl className="summary"><div><dt>Course</dt><dd>{course || 'Not set'}</dd></div><div><dt>Topic</dt><dd>{topic || 'Not set'}</dd></div><div><dt>Format</dt><dd>{assessmentType}</dd></div><div><dt>Difficulty</dt><dd>{difficulty}</dd></div><div><dt>Estimated student time</dt><dd>{estimatedTime} minutes</dd></div><div><dt>Factors</dt><dd>{(Object.keys(enabled) as FactorKey[]).filter((key) => enabled[key]).map((key) => factorLabels[key]).join(', ') || 'None'}</dd></div></dl></section>}
        <div className="section-navigation">{index > 0 && <button onClick={() => setSection(sections[index - 1].id)}>Previous</button>}{index < sections.length - 1 && <button className="next" onClick={() => setSection(sections[index + 1].id)}>Next: {sections[index + 1].label}</button>}</div>
      </div>
    </div>
    <div className="fixed-run-action" data-testid="fixed-run-action"><span>Section {index + 1} of 3</span><button className="primary" disabled={loading} onClick={submit}>{loading ? 'Starting…' : 'Run Experiment'}</button></div>
    {missing.length > 0 && <div className="modal-backdrop"><div role="dialog" aria-modal="true" aria-labelledby="incomplete-title" className="incomplete-modal"><h2 id="incomplete-title">Your experiment isn’t ready yet</h2><p>Complete the following items before running the experiment.</p><div>{missing.map((item, itemIndex) => <button key={`${item.label}-${itemIndex}`} onClick={() => goToMissing(item)}><strong>{sections.find((entry) => entry.id === item.section)?.label}:</strong> {item.label}</button>)}</div><button className="modal-close" onClick={() => setMissing([])}>Close</button></div></div>}
  </main>
}
