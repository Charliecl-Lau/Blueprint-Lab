import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { Select } from '../components/ui/Select'
import { Checkbox } from '../components/ui/Checkbox'
import { Switch } from '../components/ui/Switch'
import { runsApi } from '../api/runs'
import { useRunStore } from '../store/runStore'
import type { ControlSet } from '../types'

// ── hidden defaults (API still requires control_sets) ──────────────────────
const defaultControlSet = (): Omit<ControlSet, 'id'> => ({
  personality: 'formal',
  prompt_length: 'medium',
  result_length: 'medium',
  action_word_count: 3,
})

// ── section definitions ────────────────────────────────────────────────────
const SECTIONS = [
  {
    id: 'topic',
    label: 'Topic & Context',
    icon: (
      <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
        <path d="M3 4h10M3 7h10M3 10h8M3 13h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: 'config',
    label: 'Assessment Config',
    icon: (
      <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
        <circle cx="3" cy="4" r="1.5" fill="currentColor" />
        <path d="M6 4h7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="3" cy="9" r="1.5" fill="currentColor" />
        <path d="M6 9h7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="3" cy="14" r="1.5" fill="currentColor" />
        <path d="M6 14h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: 'framework',
    label: 'Prompt Framework',
    icon: (
      <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
        <path d="M2 3h12v2H2zM2 7h9v2H2zM2 11h11v2H2z" fill="currentColor" opacity="0.2" />
        <path d="M2 3.5h12M2 7.5h9M2 11.5h11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: 'variables',
    label: 'Output Variables',
    icon: (
      <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
        <path d="M2 5h4v6H2zM6 5h4v6H6zM10 5h4v6h-4z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      </svg>
    ),
  },
] as const

type SectionId = (typeof SECTIONS)[number]['id']

// ── select options ─────────────────────────────────────────────────────────
const SUBJECT_OPTIONS = [
  { value: '', label: 'Select subject area…' },
  { value: 'sciences', label: 'Sciences & Engineering' },
  { value: 'humanities', label: 'Humanities & Social Sciences' },
  { value: 'medicine', label: 'Medicine & Health Sciences' },
  { value: 'law', label: 'Law & Legal Studies' },
  { value: 'business', label: 'Business & Economics' },
  { value: 'education', label: 'Education & Pedagogy' },
]

const LEVEL_OPTIONS = [
  { value: 'first', label: 'First Year' },
  { value: 'second', label: 'Second Year' },
  { value: 'third', label: 'Third Year' },
  { value: 'postgrad', label: 'Postgraduate' },
]

const DIFFICULTY_OPTIONS = [
  { value: 'easy', label: 'Easy' },
  { value: 'medium', label: 'Medium' },
  { value: 'hard', label: 'Hard' },
  { value: 'mixed', label: 'Mixed Difficulty' },
]

const BLOOM_OPTIONS = [
  { value: 'remember', label: 'Remember — Recall facts' },
  { value: 'understand', label: 'Understand — Explain ideas' },
  { value: 'apply', label: 'Apply — Use in new situations' },
  { value: 'analyze', label: 'Analyze — Draw connections' },
  { value: 'evaluate', label: 'Evaluate — Justify a decision' },
  { value: 'create', label: 'Create — Produce new work' },
]

const FRAMEWORK_OPTIONS = [
  { value: '', label: 'Select a framework…' },
  { value: 'direct', label: 'Direct — Clear, unambiguous questions' },
  { value: 'socratic', label: 'Socratic — Question-led inquiry' },
  { value: 'case', label: 'Case-based — Scenario and application' },
  { value: 'scenario', label: 'Scenario-based — Real-world context' },
]

const REGISTER_OPTIONS = [
  { value: 'formal', label: 'Formal academic' },
  { value: 'semiformal', label: 'Semi-formal' },
]

// ── sub-components ─────────────────────────────────────────────────────────
function SectionCard({ title, children, style }: { title: string; children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      background: 'white', borderRadius: 14, padding: '24px',
      border: '1px solid #EBEBED', boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
      animation: 'db-fade-in 0.22s ease',
      ...style,
    }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#1D1D1F', letterSpacing: '-0.01em', marginBottom: 16 }}>{title}</div>
      {children}
    </div>
  )
}

function FieldLabel({ children, optional }: { children: React.ReactNode; optional?: boolean }) {
  return (
    <div style={{ fontSize: 12, fontWeight: 500, color: '#6E6E73', letterSpacing: '-0.01em', marginBottom: 6, display: 'flex', justifyContent: 'space-between' }}>
      <span>{children}</span>
      {optional && <span style={{ fontWeight: 400, color: '#B8B8BE' }}>Optional</span>}
    </div>
  )
}

const ASSESSMENT_TYPES = [
  { id: 'mcq',   label: 'Multiple Choice', desc: 'Single or multiple correct answers', icon: '☰' },
  { id: 'short', label: 'Short Answer',    desc: 'Written responses under 100 words',  icon: '✎' },
  { id: 'essay', label: 'Essay Questions', desc: 'Extended analytical writing',         icon: '≡' },
  { id: 'mixed', label: 'Mixed Format',    desc: 'Combination of question types',       icon: '⊞' },
]

function AssessmentTypeCard({ id, label, desc, icon, selected, onClick }: {
  id: string; label: string; desc: string; icon: string; selected: boolean; onClick: () => void
}) {
  const [hov, setHov] = useState(false)
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        padding: '14px 16px', borderRadius: 10, cursor: 'pointer', transition: 'all 0.15s',
        border: selected ? '1.5px solid #1A56DB' : `1px solid ${hov ? '#B8B8BE' : '#D2D2D7'}`,
        background: selected ? '#EBF2FF' : hov ? '#FAFAFA' : 'white',
        display: 'flex', alignItems: 'flex-start', gap: 12,
      }}
    >
      <div style={{
        width: 32, height: 32, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        background: selected ? 'rgba(26,86,219,0.12)' : '#F5F5F7',
        color: selected ? '#1A56DB' : '#6E6E73', fontSize: 16,
      }}>
        {icon}
      </div>
      <div>
        <div style={{ fontSize: 13, fontWeight: 500, color: selected ? '#1444B0' : '#1D1D1F', letterSpacing: '-0.01em' }}>{label}</div>
        <div style={{ fontSize: 12, color: '#86868B', marginTop: 2, lineHeight: 1.4 }}>{desc}</div>
      </div>
    </div>
  )
}

// ── section renderers ──────────────────────────────────────────────────────
function TopicSection({ form, update }: { form: FormState; update: UpdateFn }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <SectionCard title="Course Context">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Input label="Course name" placeholder="e.g. Introduction to Statistics" value={form.courseName} onChange={e => update('courseName', e.target.value)} />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Select label="Subject area" value={form.subject} onChange={e => update('subject', e.target.value)} options={SUBJECT_OPTIONS} />
            <Select label="Academic level" value={form.level} onChange={e => update('level', e.target.value)} placeholder="Select level…" options={LEVEL_OPTIONS} />
          </div>
        </div>
      </SectionCard>
      <SectionCard title="Learning Objectives">
        <FieldLabel optional>What should students demonstrate after this assessment?</FieldLabel>
        <textarea
          value={form.objectives}
          onChange={e => update('objectives', e.target.value)}
          placeholder="e.g. Apply the central limit theorem to estimate population parameters using sample data"
          rows={4}
          style={{ width: '100%', padding: '10px 12px', border: '1px solid #D2D2D7', borderRadius: 10, fontSize: 13, fontFamily: 'inherit', color: '#1D1D1F', lineHeight: 1.55, outline: 'none', transition: 'border-color 0.15s', background: 'white', resize: 'vertical' }}
          onFocus={e => (e.target.style.borderColor = '#1A56DB')}
          onBlur={e => (e.target.style.borderColor = '#D2D2D7')}
        />
      </SectionCard>
    </div>
  )
}

function ConfigSection({ form, update }: { form: FormState; update: UpdateFn }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <SectionCard title="Assessment Format">
        <FieldLabel>Select the primary question format</FieldLabel>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 4 }}>
          {ASSESSMENT_TYPES.map(t => (
            <AssessmentTypeCard key={t.id} {...t} selected={form.assessmentType === t.id} onClick={() => update('assessmentType', t.id)} />
          ))}
        </div>
      </SectionCard>
      <SectionCard title="Question Parameters">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
          <Input label="Questions per variant" type="number" value={form.questionCount} onChange={e => update('questionCount', e.target.value)} suffix="Qs" size="md" />
          <Select label="Difficulty" value={form.difficulty} onChange={e => update('difficulty', e.target.value)} options={DIFFICULTY_OPTIONS} />
          <Select label="Bloom's taxonomy" value={form.bloom} onChange={e => update('bloom', e.target.value)} placeholder="Select level…" options={BLOOM_OPTIONS} />
        </div>
      </SectionCard>
    </div>
  )
}

function FrameworkSection({ form, update }: { form: FormState; update: UpdateFn }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <SectionCard title="Pedagogical Approach">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <Select label="Question framework" value={form.framework} onChange={e => update('framework', e.target.value)} options={FRAMEWORK_OPTIONS} />
          <Select label="Language register" value={form.register} onChange={e => update('register', e.target.value)} options={REGISTER_OPTIONS} />
        </div>
      </SectionCard>
      <SectionCard title="Additional Instructions">
        <FieldLabel optional>Any specific requirements, constraints, or examples to follow</FieldLabel>
        <textarea
          value={form.instructions}
          onChange={e => update('instructions', e.target.value)}
          placeholder="e.g. Avoid questions on Chapter 4 (not yet covered). Use Australian English spelling."
          rows={5}
          style={{ width: '100%', padding: '10px 12px', border: '1px solid #D2D2D7', borderRadius: 10, fontSize: 13, fontFamily: 'inherit', color: '#1D1D1F', lineHeight: 1.55, outline: 'none', transition: 'border-color 0.15s', background: 'white', resize: 'vertical' }}
          onFocus={e => (e.target.style.borderColor = '#1A56DB')}
          onBlur={e => (e.target.style.borderColor = '#D2D2D7')}
        />
      </SectionCard>
    </div>
  )
}

function VariablesSection({ form, update }: { form: FormState; update: UpdateFn }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <SectionCard title="Generation Settings">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 20 }}>
          <Input label="Variants to generate" type="number" value={form.variants} onChange={e => update('variants', e.target.value)} hint="Max 12 parallel variants" />
          <Input label="Target word count" type="number" value={form.wordLimitValue} onChange={e => update('wordLimitValue', e.target.value)} suffix="words" disabled={!form.wordLimit} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Switch checked={form.includeAnswerKey} onChange={v => update('includeAnswerKey', v)} label="Include answer key in export" size="md" />
          <Switch checked={form.shuffleQuestions} onChange={v => update('shuffleQuestions', v)} label="Shuffle question order across variants" size="md" />
          <Switch checked={form.wordLimit} onChange={v => update('wordLimit', v)} label="Enforce word count limit" size="md" />
        </div>
      </SectionCard>
      <SectionCard title="Export Defaults">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Checkbox checked={true} onChange={() => {}} label="PDF export" description="High-quality formatted PDF per variant" />
          <Checkbox checked={false} onChange={() => {}} label="DOCX export" description="Editable Word document format" />
          <Checkbox checked={true} onChange={() => {}} label="Student version" description="Separate copy without answers highlighted" />
        </div>
      </SectionCard>
    </div>
  )
}

// ── types ──────────────────────────────────────────────────────────────────
interface FormState {
  courseName: string; subject: string; level: string; objectives: string
  assessmentType: string; questionCount: string; difficulty: string; bloom: string
  framework: string; register: string; instructions: string
  variants: string; wordLimitValue: string
  includeAnswerKey: boolean; shuffleQuestions: boolean; wordLimit: boolean
}

type UpdateFn = <K extends keyof FormState>(key: K, value: FormState[K]) => void

// ── main component ─────────────────────────────────────────────────────────
export function InputPanelPage() {
  const navigate = useNavigate()
  const reset = useRunStore(s => s.reset)

  const [section, setSection] = useState<SectionId>('topic')
  const [form, setForm] = useState<FormState>({
    courseName: '', subject: '', level: '', objectives: '',
    assessmentType: 'mcq', questionCount: '12', difficulty: 'mixed', bloom: '',
    framework: 'direct', register: 'formal', instructions: '',
    variants: '12', wordLimitValue: '300',
    includeAnswerKey: true, shuffleQuestions: false, wordLimit: false,
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const update: UpdateFn = (key, value) => setForm(f => ({ ...f, [key]: value }))

  const sectionIndex = SECTIONS.findIndex(s => s.id === section)
  const activeSection = SECTIONS[sectionIndex]

  const handleSubmit = async () => {
    if (!form.courseName.trim()) { setError('Course name is required'); return }
    if (!form.objectives.trim()) { setError('Learning objectives are required'); return }

    setLoading(true)
    setError('')
    reset()

    const qCount = parseInt(form.questionCount) || 12
    try {
      const { id } = await runsApi.create({
        topic: form.courseName.trim(),
        expectations: form.objectives.trim(),
        mcq_count: form.assessmentType === 'mcq' ? qCount : 0,
        long_answer_count: form.assessmentType !== 'mcq' ? qCount : 0,
        frameworks: ['forge'],
        control_sets: [defaultControlSet(), defaultControlSet(), defaultControlSet(), defaultControlSet()],
      })
      navigate(`/runs/${id}/progress`)
    } catch (e: any) {
      setError(e.message || 'Failed to create run')
      setLoading(false)
    }
  }

  const goTo = (id: SectionId) => setSection(id)
  const goPrev = () => sectionIndex > 0 && goTo(SECTIONS[sectionIndex - 1].id)
  const goNext = () => sectionIndex < SECTIONS.length - 1 && goTo(SECTIONS[sectionIndex + 1].id)

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', fontFamily: 'var(--font-sans)', background: '#F5F5F7' }}>

      {/* Top bar */}
      <div style={{ height: 52, background: 'white', borderBottom: '1px solid #EBEBED', display: 'flex', alignItems: 'center', padding: '0 28px', gap: 12, flexShrink: 0, zIndex: 10 }}>
        <svg width="28" height="28" viewBox="0 0 40 40" fill="none">
          <rect width="40" height="40" rx="10" fill="#1A56DB" />
          <path d="M9 11h8.5C21.09 11 24 13.91 24 17.5v5C24 26.09 21.09 29 17.5 29H9V11z" stroke="white" strokeWidth="2" fill="none" strokeLinejoin="round" />
          <circle cx="29" cy="13" r="1.2" fill="white" opacity="0.6" />
          <circle cx="33" cy="13" r="1.2" fill="white" opacity="0.6" />
          <circle cx="29" cy="17" r="1.2" fill="white" opacity="0.6" />
          <circle cx="33" cy="17" r="1.2" fill="white" opacity="0.9" />
          <circle cx="29" cy="21" r="1.2" fill="white" opacity="0.6" />
          <circle cx="33" cy="21" r="1.2" fill="white" opacity="0.6" />
        </svg>
        <span style={{ fontSize: 14, fontWeight: 600, color: '#1D1D1F', letterSpacing: '-0.02em' }}>Design Blueprint</span>
        <span style={{ color: '#D2D2D7', fontSize: 16, marginLeft: 4 }}>/</span>
        <span style={{ fontSize: 13, color: '#6E6E73' }}>New Assessment Run</span>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 10px', borderRadius: 8, cursor: 'pointer', background: '#F5F5F7' }}>
          <div style={{ width: 24, height: 24, borderRadius: '50%', background: '#1A56DB', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 600, color: 'white' }}>SC</div>
          <span style={{ fontSize: 13, color: '#1D1D1F', fontWeight: 500 }}>Dr. Sarah Chen</span>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M3 4.5l3 3 3-3" stroke="#86868B" strokeWidth="1.3" strokeLinecap="round" />
          </svg>
        </div>
      </div>

      {/* Body */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* Side nav */}
        <div style={{ width: 220, background: 'white', borderRight: '1px solid #EBEBED', padding: '20px 12px', display: 'flex', flexDirection: 'column', gap: 2, flexShrink: 0 }}>
          <div style={{ fontSize: 10, fontWeight: 500, color: '#B8B8BE', letterSpacing: '0.08em', textTransform: 'uppercase', padding: '4px 8px 10px', marginBottom: 2 }}>Configuration</div>
          {SECTIONS.map((s, i) => {
            const isActive = section === s.id
            return (
              <div
                key={s.id}
                onClick={() => goTo(s.id)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 9, padding: '8px 10px', borderRadius: 8, cursor: 'pointer', transition: 'all 0.12s',
                  background: isActive ? '#EBF2FF' : 'transparent',
                  color: isActive ? '#1444B0' : '#515154',
                }}
              >
                <span style={{ opacity: isActive ? 1 : 0.6 }}>{s.icon}</span>
                <span style={{ fontSize: 13, fontWeight: isActive ? 500 : 400, letterSpacing: '-0.01em' }}>{s.label}</span>
                {i < 2 && <div style={{ marginLeft: 'auto', width: 6, height: 6, borderRadius: '50%', background: '#30C559', opacity: 0.8 }} />}
              </div>
            )
          })}
          <div style={{ flex: 1 }} />
          <div style={{ padding: '12px 10px', borderTop: '1px solid #F5F5F7', fontSize: 12, color: '#86868B' }}>
            <div style={{ fontWeight: 500, color: '#1D1D1F', marginBottom: 3 }}>12 variants queued</div>
            Ready to generate when you click Generate below.
          </div>
        </div>

        {/* Form area */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '28px' }}>
          <div style={{ maxWidth: 740, margin: '0 auto' }}>
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 20, fontWeight: 600, color: '#1D1D1F', letterSpacing: '-0.02em' }}>{activeSection.label}</div>
            </div>

            {section === 'topic'     && <TopicSection     form={form} update={update} />}
            {section === 'config'    && <ConfigSection    form={form} update={update} />}
            {section === 'framework' && <FrameworkSection form={form} update={update} />}
            {section === 'variables' && <VariablesSection form={form} update={update} />}

            {error && (
              <div style={{ marginTop: 16, padding: '10px 14px', background: '#FFF1F0', border: '1px solid #FFCCC7', borderRadius: 10, fontSize: 13, color: '#CF1322' }}>
                {error}
              </div>
            )}

            <div style={{ height: 24 }} />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              {sectionIndex > 0 && (
                <button
                  onClick={goPrev}
                  style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#6E6E73', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}
                >
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M10 4L6 8l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
                  Previous
                </button>
              )}
              {sectionIndex < SECTIONS.length - 1 && (
                <button
                  onClick={goNext}
                  style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#1A56DB', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 500, marginLeft: 'auto' }}
                >
                  Next: {SECTIONS[sectionIndex + 1].label}
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M6 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Bottom bar */}
      <div style={{ height: 68, background: 'rgba(255,255,255,0.95)', backdropFilter: 'blur(12px)', borderTop: '1px solid #EBEBED', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 28px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <Button variant="ghost" size="sm">Save Draft</Button>
          <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
            {SECTIONS.map((s, i) => (
              <div key={s.id} style={{ width: 6, height: 6, borderRadius: '50%', background: i <= sectionIndex ? '#1A56DB' : '#D2D2D7', transition: 'background 0.2s' }} />
            ))}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ fontSize: 12, color: '#86868B' }}>
            <span style={{ color: '#1D1D1F', fontWeight: 500 }}>12</span> variants · <span style={{ color: '#1D1D1F', fontWeight: 500 }}>~3 min</span> estimated
          </div>
          <Button variant="primary" size="lg" loading={loading} onClick={handleSubmit} disabled={loading}>
            Generate 12 Assessments
          </Button>
        </div>
      </div>
    </div>
  )
}
