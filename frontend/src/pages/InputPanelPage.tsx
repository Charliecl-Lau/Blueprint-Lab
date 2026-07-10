import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { experimentsApi } from '../api/experiments'
import { PROMPT_FACTORS, PromptFactorFields, type FactorKey } from '../components/PromptFactorFields'
import { useRunStore } from '../store/runStore'
import type { AssessmentType, PromptStructure } from '../types'

const factorLabels: Record<FactorKey, string> = Object.fromEntries(PROMPT_FACTORS.map((factor) => [factor.key, factor.label.replace(' (chain-of-thought condition)', '')])) as Record<FactorKey, string>
const initialEnabled: Record<FactorKey, boolean> = { conceptBridge: false, fewShot: false, referenceContent: false, reasoningGuidance: false }
const initialContent: Record<FactorKey, string> = { conceptBridge: '', fewShot: '', referenceContent: '', reasoningGuidance: '' }

export function InputPanelPage() {
  const navigate = useNavigate()
  const reset = useRunStore((state) => state.reset)
  const [course, setCourse] = useState('')
  const [topic, setTopic] = useState('')
  const [objectives, setObjectives] = useState('')
  const [assessmentType, setAssessmentType] = useState<AssessmentType>('mixed')
  const [difficulty, setDifficulty] = useState('mixed')
  const [questionCount, setQuestionCount] = useState('4')
  const [estimatedTime, setEstimatedTime] = useState('30')
  const [promptStructure, setPromptStructure] = useState<PromptStructure>('openai')
  const [enabled, setEnabled] = useState(initialEnabled)
  const [content, setContent] = useState(initialContent)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)

  const submit = async () => {
    const next: Record<string, string> = {}
    if (!course.trim()) next.course = 'Course name is required.'
    if (!topic.trim()) next.topic = 'Topic is required.'
    if (!objectives.trim()) next.objectives = 'Learning objectives are required.'
    const questions = Number(questionCount)
    if (!Number.isInteger(questions) || questions < 1 || questions > 50) next.questionCount = 'Enter 1 to 50 questions.'
    const minutes = Number(estimatedTime)
    if (!Number.isInteger(minutes) || minutes < 1 || minutes > 480) next.estimatedTime = 'Enter 1 to 480 minutes.'
    for (const key of Object.keys(enabled) as FactorKey[]) if (enabled[key] && !content[key].trim()) next[key] = `Add content for ${factorLabels[key]}.`
    setErrors(next)
    if (Object.keys(next).length) return

    setLoading(true)
    try {
      reset()
      const experiment = await experimentsApi.create({
        course: course.trim(), topic: topic.trim(), learning_objectives: objectives.trim(), assessment_type: assessmentType,
        difficulty, number_of_questions: questions, estimated_time_minutes: minutes, prompt_structure: promptStructure,
        factors: { concept_bridge: enabled.conceptBridge, few_shot: enabled.fewShot, reference_content: enabled.referenceContent, reasoning_guidance: enabled.reasoningGuidance },
        factor_inputs: {
          ...(enabled.conceptBridge && { concept_bridge: content.conceptBridge.trim() }),
          ...(enabled.fewShot && { few_shot: content.fewShot.trim() }),
          ...(enabled.referenceContent && { reference_content: content.referenceContent.trim() }),
          ...(enabled.reasoningGuidance && { reasoning_guidance: content.reasoningGuidance.trim() }),
        },
      })
      navigate(`/experiments/${experiment.id}/progress`)
    } catch (error) {
      setErrors({ submit: error instanceof Error ? error.message : 'Unable to run experiment.' })
    } finally { setLoading(false) }
  }

  return <main className="experiment-page">
    <header><strong>Blueprint Lab</strong><span>Controlled assessment research</span></header>
    <div className="experiment-shell">
      <h1>New Experiment</h1><p>Configure an assessment and the prompt conditions to evaluate.</p>
      <section><h2>Assessment Details</h2>
        <div className="form-grid">
          <label>Course name<input value={course} onChange={(e) => setCourse(e.target.value)} />{errors.course && <em>{errors.course}</em>}</label>
          <label>Topic<input value={topic} onChange={(e) => setTopic(e.target.value)} />{errors.topic && <em>{errors.topic}</em>}</label>
          <label className="wide">Learning objectives<textarea rows={3} value={objectives} onChange={(e) => setObjectives(e.target.value)} />{errors.objectives && <em>{errors.objectives}</em>}</label>
          <label>Assessment format<select value={assessmentType} onChange={(e) => setAssessmentType(e.target.value as AssessmentType)}><option value="mcq">Multiple choice</option><option value="short_answer">Short answer</option><option value="mixed">Mixed</option></select></label>
          <label>Difficulty<select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option><option value="mixed">Mixed</option></select></label>
          <label>Number of questions<input type="number" min="1" max="50" value={questionCount} onChange={(e) => setQuestionCount(e.target.value)} />{errors.questionCount && <em>{errors.questionCount}</em>}</label>
          <label>Estimated student completion time<input aria-label="Estimated student completion time" type="number" min="1" max="480" value={estimatedTime} onChange={(e) => setEstimatedTime(e.target.value)} /><small>Minutes, distinct from generation time.</small>{errors.estimatedTime && <em>{errors.estimatedTime}</em>}</label>
          <label>Prompt structure<select value={promptStructure} onChange={(e) => setPromptStructure(e.target.value as PromptStructure)}><option value="openai">OpenAI</option><option value="anthropic">Anthropic</option></select></label>
        </div>
      </section>
      <section><h2>Prompt Design Factors</h2><PromptFactorFields enabled={enabled} content={content} errors={errors} onToggle={(key) => setEnabled((current) => ({ ...current, [key]: !current[key] }))} onContent={(key, value) => setContent((current) => ({ ...current, [key]: value }))} /></section>
      <section><h2>Review Experiment</h2><dl className="summary"><div><dt>Course</dt><dd>{course || 'Not set'}</dd></div><div><dt>Format</dt><dd>{assessmentType}</dd></div><div><dt>Difficulty</dt><dd>{difficulty}</dd></div><div><dt>Estimated student time</dt><dd>{estimatedTime} minutes</dd></div><div><dt>Factors</dt><dd>{(Object.keys(enabled) as FactorKey[]).filter((key) => enabled[key]).map((key) => factorLabels[key]).join(', ') || 'None'}</dd></div></dl></section>
      {errors.submit && <p className="error">{errors.submit}</p>}
      <button className="primary" disabled={loading} onClick={submit}>{loading ? 'Starting…' : 'Run Experiment'}</button>
    </div>
  </main>
}
