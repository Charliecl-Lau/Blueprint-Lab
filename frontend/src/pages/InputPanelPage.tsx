import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { experimentsApi } from '../api/experiments'
import { AppHeader } from '../components/AppHeader'
import { PromptFactorFields } from '../components/PromptFactorFields'
import { RunProgressShortcut } from '../components/RunProgressShortcut'
import { useRunStore } from '../store/runStore'
import type { AssessmentType, CognitiveDemand, PromptStructure } from '../types'
import {
  PROMPT_FACTORS,
  factorContentId,
  validateExperimentForm,
  type ExperimentFormValues,
  type FactorKey,
  type ValidationError,
  type ValidationSection,
} from '../validation/experimentValidation'

type Section = 'details' | 'factors' | 'review'

const sections: { id: Section; label: string; subtitle: string }[] = [
  { id: 'details', label: 'Assessment Details', subtitle: 'Define the course and assessment requirements.' },
  { id: 'factors', label: 'Prompt Design Factors', subtitle: 'Select experimental factors and provide their content.' },
  { id: 'review', label: 'Review', subtitle: 'Check the condition before running the experiment.' },
]
const factorLabels = Object.fromEntries(PROMPT_FACTORS.map((factor) => [factor.key, factor.label.replace(' (chain-of-thought condition)', '')])) as Record<FactorKey, string>
const initialEnabled: Record<FactorKey, boolean> = { conceptBridge: false, fewShot: false, referenceContent: false, reasoningGuidance: false }
const initialContent: Record<FactorKey, string> = { conceptBridge: '', fewShot: '', referenceContent: '', reasoningGuidance: '' }
const validationSections: ValidationSection[] = ['Assessment Details', 'Prompt Design Factors']
const cognitiveDemandLabels: Record<CognitiveDemand, string> = {
  remember_understand: 'Remember/Understand',
  apply_analyze: 'Apply/Analyze',
  evaluate_create: 'Evaluate/Create',
}

function createIdempotencyKey() {
  const cryptoSource = globalThis.crypto
  if (typeof cryptoSource?.randomUUID === 'function') return cryptoSource.randomUUID()

  if (typeof cryptoSource?.getRandomValues === 'function') {
    const bytes = cryptoSource.getRandomValues(new Uint8Array(16))
    bytes[6] = (bytes[6] & 0x0f) | 0x40
    bytes[8] = (bytes[8] & 0x3f) | 0x80
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
  }

  return `experiment-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function StepIcon({ section }: { section: Section }) {
  if (section === 'details') return <svg aria-hidden="true" viewBox="0 0 18 18"><path d="M4 4h10M4 9h10M4 14h7" /></svg>
  if (section === 'factors') return <svg aria-hidden="true" viewBox="0 0 18 18"><path d="M3 5h12M3 9h9M3 13h11" /></svg>
  return <svg aria-hidden="true" viewBox="0 0 18 18"><path d="M4 2.5h7l3 3v10H4zM7 10l1.5 1.5L12 8" /></svg>
}

function Chevron({ direction }: { direction: 'left' | 'right' }) {
  return <svg aria-hidden="true" viewBox="0 0 16 16"><path d={direction === 'left' ? 'M10 3 5 8l5 5' : 'm6 3 5 5-5 5'} /></svg>
}

export function InputPanelPage() {
  const navigate = useNavigate()
  const mergeExperiment = useRunStore((state) => state.mergeExperiment)
  const submissionKey = useRef<string | null>(null)
  const [section, setSection] = useState<Section>('details')
  const [course, setCourse] = useState('')
  const [topic, setTopic] = useState('')
  const [objectives, setObjectives] = useState('')
  const [assessmentType, setAssessmentType] = useState<AssessmentType>('mixed')
  const [difficulty, setDifficulty] = useState('mixed')
  const [questionCount, setQuestionCount] = useState('4')
  const [estimatedTime, setEstimatedTime] = useState('30')
  const [cognitiveDemand, setCognitiveDemand] = useState<CognitiveDemand>('remember_understand')
  const [additionalInstruction, setAdditionalInstruction] = useState('')
  const [promptStructure, setPromptStructure] = useState<PromptStructure>('openai')
  const [enabled, setEnabled] = useState(initialEnabled)
  const [content, setContent] = useState(initialContent)
  const [validationErrors, setValidationErrors] = useState<ValidationError[]>([])
  const [dialogOpen, setDialogOpen] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const values = (overrides: Partial<ExperimentFormValues> = {}): ExperimentFormValues => ({
    course,
    topic,
    learningObjectives: objectives,
    assessmentType,
    difficulty,
    questionCount,
    estimatedTime,
    cognitiveDemand,
    additionalInstruction,
    promptStructure,
    enabled,
    content,
    ...overrides,
  })
  const errors = Object.fromEntries(validationErrors.map((error) => [error.field, error.message]))

  const clearFieldWhenValid = (field: string, nextValues: ExperimentFormValues) => {
    if (!validateExperimentForm(nextValues).some((error) => error.field === field)) {
      setValidationErrors((current) => current.filter((error) => error.field !== field))
    }
  }

  const focusError = (error: ValidationError) => {
    setSection(error.section === 'Assessment Details' ? 'details' : 'factors')
    setDialogOpen(false)
    requestAnimationFrame(() => document.getElementById(error.field)?.focus())
  }

  const submit = async () => {
    const nextErrors = validateExperimentForm(values())
    setValidationErrors(nextErrors)
    if (nextErrors.length > 0) {
      setDialogOpen(true)
      return
    }

    setSubmitError(null)
    setLoading(true)
    try {
      submissionKey.current ??= createIdempotencyKey()
      const experiment = await experimentsApi.create({
        course: course.trim(), topic: topic.trim(), learning_objectives: objectives.trim(), assessment_type: assessmentType, difficulty,
        number_of_questions: Number(questionCount), estimated_time_minutes: Number(estimatedTime), prompt_structure: promptStructure,
        cognitive_demand: cognitiveDemand, additional_instruction: additionalInstruction.trim() || null,
        factors: { concept_bridge: enabled.conceptBridge, few_shot: enabled.fewShot, reference_content: enabled.referenceContent, reasoning_guidance: enabled.reasoningGuidance },
        factor_inputs: { ...(enabled.conceptBridge && { concept_bridge: content.conceptBridge.trim() }), ...(enabled.fewShot && { few_shot: content.fewShot.trim() }), ...(enabled.referenceContent && { reference_content: content.referenceContent.trim() }), ...(enabled.reasoningGuidance && { reasoning_guidance: content.reasoningGuidance.trim() }) },
      }, submissionKey.current)
      mergeExperiment(experiment)
      const run = experiment.runs[0]
      if (!run) throw new Error('The experiment response did not include an initial run.')
      submissionKey.current = null
      navigate(`/runs/${run.id}/progress`)
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : 'Unable to run experiment.')
    } finally {
      setLoading(false)
    }
  }

  const updateFactorEnabled = (key: FactorKey) => {
    const nextEnabled = { ...enabled, [key]: !enabled[key] }
    setEnabled(nextEnabled)
    clearFieldWhenValid(factorContentId(key), values({ enabled: nextEnabled }))
  }
  const updateFactorContent = (key: FactorKey, nextValue: string) => {
    const nextContent = { ...content, [key]: nextValue }
    setContent(nextContent)
    clearFieldWhenValid(factorContentId(key), values({ content: nextContent }))
  }
  const index = sections.findIndex((item) => item.id === section)
  const current = sections[index]
  const isSectionComplete = (id: Section) => {
    if (id === 'details') return course.trim() !== '' && topic.trim() !== '' && objectives.trim() !== ''
    if (id === 'factors') {
      const keys = Object.keys(enabled) as FactorKey[]
      return keys.some((key) => enabled[key]) && keys.every((key) => !enabled[key] || content[key].trim() !== '')
    }
    return false
  }

  return <main className="experiment-page wizard-page">
    <AppHeader subtitle="Controlled assessment research" action={<RunProgressShortcut />} />
    <div className="wizard-layout">
      <nav aria-label="Experiment sections" className="wizard-nav">
        <h1 className="nav-eyebrow">New Experiment</h1>
        {sections.map((item) => <button aria-label={item.label} aria-current={section === item.id ? 'step' : undefined} key={item.id} className={section === item.id ? 'active' : ''} onClick={() => setSection(item.id)}><span className="step-icon"><StepIcon section={item.id} /></span><strong>{item.label}</strong>{isSectionComplete(item.id) && <span className="step-dot" aria-hidden="true" />}</button>)}
      </nav>
      <div className="wizard-content">
        <div className="section-heading"><h2>{section === 'review' ? 'Review Experiment' : current.label}</h2><p>{current.subtitle}</p></div>
        {section === 'details' && <section className="section-card"><div className="form-grid">
          <div className="field-stack"><label htmlFor="course">Course name</label><input id="course" value={course} aria-invalid={errors.course ? 'true' : undefined} aria-describedby={errors.course ? 'course-error' : undefined} onChange={(event) => { const next = event.target.value; setCourse(next); clearFieldWhenValid('course', values({ course: next })) }} />{errors.course && <em id="course-error">{errors.course}</em>}</div>
          <div className="field-stack"><label htmlFor="topic">Topic</label><input id="topic" value={topic} aria-invalid={errors.topic ? 'true' : undefined} aria-describedby={errors.topic ? 'topic-error' : undefined} onChange={(event) => { const next = event.target.value; setTopic(next); clearFieldWhenValid('topic', values({ topic: next })) }} />{errors.topic && <em id="topic-error">{errors.topic}</em>}</div>
          <div className="wide field-stack"><label htmlFor="learning-objectives">Learning objectives</label><textarea id="learning-objectives" rows={3} value={objectives} aria-invalid={errors['learning-objectives'] ? 'true' : undefined} aria-describedby={errors['learning-objectives'] ? 'learning-objectives-error' : undefined} onChange={(event) => { const next = event.target.value; setObjectives(next); clearFieldWhenValid('learning-objectives', values({ learningObjectives: next })) }} />{errors['learning-objectives'] && <em id="learning-objectives-error">{errors['learning-objectives']}</em>}</div>
          <label>Assessment format<select value={assessmentType} onChange={(event) => setAssessmentType(event.target.value as AssessmentType)}><option value="mcq">Multiple choice</option><option value="short_answer">Short answer</option><option value="mixed">Mixed</option></select></label>
          <label>Difficulty<select value={difficulty} onChange={(event) => setDifficulty(event.target.value)}><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option><option value="mixed">Mixed</option></select></label>
          <div className="field-stack"><label htmlFor="number-of-questions">Number of questions</label><input id="number-of-questions" type="number" min="1" max="50" value={questionCount} aria-invalid={errors['number-of-questions'] ? 'true' : undefined} aria-describedby={errors['number-of-questions'] ? 'number-of-questions-error' : undefined} onChange={(event) => { const next = event.target.value; setQuestionCount(next); clearFieldWhenValid('number-of-questions', values({ questionCount: next })) }} />{errors['number-of-questions'] && <em id="number-of-questions-error">{errors['number-of-questions']}</em>}</div>
          <div className="field-stack"><label htmlFor="estimated-time">Estimated student completion time</label><input id="estimated-time" type="number" min="1" max="480" value={estimatedTime} aria-invalid={errors['estimated-time'] ? 'true' : undefined} aria-describedby={errors['estimated-time'] ? 'estimated-time-error' : undefined} onChange={(event) => { const next = event.target.value; setEstimatedTime(next); clearFieldWhenValid('estimated-time', values({ estimatedTime: next })) }} /><small>Minutes, distinct from generation time.</small>{errors['estimated-time'] && <em id="estimated-time-error">{errors['estimated-time']}</em>}</div>
          <label>Prompt structure<select value={promptStructure} onChange={(event) => setPromptStructure(event.target.value as PromptStructure)}><option value="openai">OpenAI</option><option value="anthropic">Anthropic</option></select></label>
          <div className="field-stack"><label htmlFor="cognitive-demand">Cognitive demand</label><select id="cognitive-demand" required value={cognitiveDemand} aria-invalid={errors['cognitive-demand'] ? 'true' : undefined} aria-describedby={errors['cognitive-demand'] ? 'cognitive-demand-error' : undefined} onChange={(event) => { const next = event.target.value as CognitiveDemand; setCognitiveDemand(next); clearFieldWhenValid('cognitive-demand', values({ cognitiveDemand: next })) }}><option value="remember_understand">Remember/Understand</option><option value="apply_analyze">Apply/Analyze</option><option value="evaluate_create">Evaluate/Create</option></select>{errors['cognitive-demand'] && <em id="cognitive-demand-error">{errors['cognitive-demand']}</em>}</div>
          <div className="wide field-stack"><label htmlFor="additional-instruction">Additional instruction (optional)</label><textarea id="additional-instruction" rows={3} maxLength={20000} value={additionalInstruction} onChange={(event) => setAdditionalInstruction(event.target.value)} /></div>
        </div></section>}
        {section === 'factors' && <section className="section-card"><PromptFactorFields enabled={enabled} content={content} errors={errors} onToggle={updateFactorEnabled} onContent={updateFactorContent} /></section>}
        {section === 'review' && <section className="section-card"><dl className="summary"><div><dt>Course</dt><dd>{course || 'Not set'}</dd></div><div><dt>Topic</dt><dd>{topic || 'Not set'}</dd></div><div><dt>Format</dt><dd>{assessmentType}</dd></div><div><dt>Difficulty</dt><dd>{difficulty}</dd></div><div><dt>Estimated student time</dt><dd>{estimatedTime} minutes</dd></div><div><dt>Cognitive demand</dt><dd>{cognitiveDemandLabels[cognitiveDemand]}</dd></div><div><dt>Additional instruction</dt><dd>{additionalInstruction.trim() || 'None'}</dd></div><div><dt>Factors</dt><dd>{(Object.keys(enabled) as FactorKey[]).filter((key) => enabled[key]).map((key) => factorLabels[key]).join(', ') || 'None'}</dd></div></dl></section>}
        <div className="section-navigation">{index > 0 && <button aria-label="Previous" onClick={() => setSection(sections[index - 1].id)}><Chevron direction="left" />Previous</button>}{index < sections.length - 1 && <button aria-label={`Next: ${sections[index + 1].label}`} className="next" onClick={() => setSection(sections[index + 1].id)}>Next: {sections[index + 1].label}<Chevron direction="right" /></button>}</div>
      </div>
    </div>
    <div className="fixed-run-action" data-testid="fixed-run-action">
      {submitError && <p className="submit-error" role="alert">{submitError}</p>}
      <button className="primary run-button" disabled={loading} onClick={submit}>{loading ? 'Starting…' : 'Run Experiment'}</button>
    </div>
    {dialogOpen && <div className="modal-backdrop"><div role="dialog" aria-modal="true" aria-labelledby="validation-title" className="incomplete-modal validation-dialog">
      <h2 id="validation-title">Complete the required fields before running the experiment.</h2>
      <p>Select an item to return to its field.</p>
      {validationSections.map((group) => {
        const groupErrors = validationErrors.filter((error) => error.section === group)
        return groupErrors.length > 0 && <section className="validation-group" key={group}><h3>{group}</h3>{groupErrors.map((error) => <button key={error.field} onClick={() => focusError(error)}>{error.label}</button>)}</section>
      })}
      <button className="modal-close" onClick={() => validationErrors[0] && focusError(validationErrors[0])}>Close</button>
    </div></div>}
  </main>
}
