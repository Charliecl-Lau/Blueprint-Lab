import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useRunStore } from '../store/runStore'
import { runsApi } from '../api/runs'
import { assessmentsApi } from '../api/assessments'
import type { Assessment, Question } from '../types'

const frameworkLabel: Record<string, string> = { forge: 'Forge', openai: 'OpenAI', risen: 'RISEN' }

// ── sub-components ─────────────────────────────────────────────────────────
function QualityDots({ score, size = 7 }: { score: number; size?: number }) {
  return (
    <div style={{ display: 'flex', gap: 2 }}>
      {[1, 2, 3, 4, 5].map(i => (
        <div key={i} style={{ width: size, height: size, borderRadius: '50%', background: i <= score ? '#1A56DB' : '#EBEBED', transition: 'background 0.2s' }} />
      ))}
    </div>
  )
}

function VariantCard({ a, letter, selected, onClick }: { a: Assessment; letter: string; selected: boolean; onClick: () => void }) {
  const [hov, setHov] = useState(false)
  const typeColors: Record<string, string> = { forge: '#EBF2FF', openai: '#F3EEFF', risen: '#FFF8EC' }
  const typeText:   Record<string, string> = { forge: '#1444B0', openai: '#6B3FC0', risen: '#8C5100' }
  const label = frameworkLabel[a.framework] ?? a.framework
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        padding: '12px 14px', borderRadius: 10, cursor: 'pointer', transition: 'all 0.12s', userSelect: 'none',
        background: selected ? 'white' : hov ? 'rgba(255,255,255,0.7)' : 'transparent',
        boxShadow: selected ? '0 1px 4px rgba(0,0,0,0.08)' : 'none',
        border: selected ? '1px solid #EBEBED' : '1px solid transparent',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 7 }}>
        <div style={{
          width: 26, height: 26, borderRadius: 7, flexShrink: 0,
          background: selected ? '#1A56DB' : (typeColors[a.framework] ?? '#F5F5F7'),
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 11, fontWeight: 700,
          color: selected ? 'white' : (typeText[a.framework] ?? '#515154'),
        }}>
          {letter}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#1D1D1F', letterSpacing: '-0.01em' }}>Variant {letter}</div>
          <div style={{ fontSize: 11, color: '#86868B' }}>{label} · Set {a.control_set_id}</div>
        </div>
        <QualityDots score={4} size={6} />
      </div>
    </div>
  )
}

function MCQQuestion({ q, showAnswers }: { q: Question; showAnswers: boolean }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div style={{ marginBottom: 20, paddingBottom: 20, borderBottom: '1px solid #F5F5F7', animation: 'db-fade-in 0.2s ease' }}>
      <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
        <div style={{ width: 22, height: 22, borderRadius: 6, background: '#F5F5F7', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 600, color: '#6E6E73', flexShrink: 0, marginTop: 1 }}>
          Q{q.order}
        </div>
        <p style={{ fontSize: 15, color: '#1D1D1F', lineHeight: 1.6, letterSpacing: '-0.01em', flex: 1 }}>{q.body}</p>
      </div>
      <div style={{ marginLeft: 34, display: 'flex', flexDirection: 'column', gap: 7 }}>
        {q.options?.map((opt, i) => {
          const isCorrect = opt.is_correct
          const show = showAnswers
          return (
            <div key={opt.id} style={{
              display: 'flex', alignItems: 'flex-start', gap: 9, padding: '8px 12px', borderRadius: 8, fontSize: 13, lineHeight: 1.5, letterSpacing: '-0.01em',
              background: show && isCorrect ? '#EDFAF2' : show && !isCorrect ? 'transparent' : '#FAFAFA',
              border: show && isCorrect ? '1px solid #8CE0B5' : '1px solid transparent',
              color: show && isCorrect ? '#1EA347' : show && !isCorrect ? '#86868B' : '#1D1D1F',
            }}>
              <div style={{
                width: 18, height: 18, borderRadius: '50%', flexShrink: 0, marginTop: 1,
                border: `1.5px solid ${show && isCorrect ? '#30C559' : '#D2D2D7'}`,
                background: show && isCorrect ? '#30C559' : 'transparent',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                {show && isCorrect && (
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                    <path d="M1.5 5l3 3 4-4.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </div>
              {opt.body}
            </div>
          )
        })}
      </div>
      {showAnswers && q.model_answer && (
        <div style={{ marginLeft: 34, marginTop: 10 }}>
          <button
            onClick={() => setExpanded(e => !e)}
            style={{ fontSize: 12, color: '#1A56DB', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 4, padding: 0 }}
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" style={{ transform: expanded ? 'rotate(90deg)' : 'rotate(0)', transition: 'transform 0.15s' }}>
              <path d="M4.5 3l3 3-3 3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
            </svg>
            {expanded ? 'Hide explanation' : 'Show explanation'}
          </button>
          {expanded && <p style={{ marginTop: 8, fontSize: 13, color: '#515154', lineHeight: 1.6, padding: '10px 12px', background: '#F5F5F7', borderRadius: 8 }}>{q.model_answer}</p>}
        </div>
      )}
    </div>
  )
}

function ShortAnswerQuestion({ q }: { q: Question }) {
  const [showAnswer, setShowAnswer] = useState(false)
  return (
    <div style={{ marginBottom: 20, paddingBottom: 20, borderBottom: '1px solid #F5F5F7' }}>
      <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
        <div style={{ width: 22, height: 22, borderRadius: 6, background: '#F3EEFF', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 600, color: '#9B5DE5', flexShrink: 0, marginTop: 1 }}>
          Q{q.order}
        </div>
        <p style={{ fontSize: 15, color: '#1D1D1F', lineHeight: 1.6, letterSpacing: '-0.01em', flex: 1 }}>{q.body}</p>
      </div>
      <div style={{ marginLeft: 34 }}>
        <button
          onClick={() => setShowAnswer(s => !s)}
          style={{ fontSize: 12, color: '#9B5DE5', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 4, marginBottom: showAnswer ? 8 : 0 }}
        >
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" style={{ transform: showAnswer ? 'rotate(90deg)' : 'rotate(0)', transition: 'transform 0.15s' }}>
            <path d="M4.5 3l3 3-3 3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
          </svg>
          {showAnswer ? 'Hide model answer' : 'Show model answer'}
        </button>
        {showAnswer && q.model_answer && (
          <div style={{ padding: '12px 14px', background: '#F3EEFF', borderRadius: 9, fontSize: 13, color: '#1D1D1F', lineHeight: 1.65 }}>
            {q.model_answer}
          </div>
        )}
      </div>
    </div>
  )
}

// ── main component ─────────────────────────────────────────────────────────
export function AssessmentViewerPage() {
  const { runId } = useParams<{ runId: string }>()
  const navigate = useNavigate()
  const { run, assessments, selectedAssessmentId, setRun, selectAssessment, setAssessment } = useRunStore()
  const [activeTab, setActiveTab] = useState('questions')
  const [exportOpen, setExportOpen] = useState(false)
  const [exporting, setExporting] = useState(false)

  const numericRunId = runId ? Number(runId) : null

  useEffect(() => {
    if (!numericRunId) return
    runsApi.get(numericRunId).then(setRun)
  }, [numericRunId])

  const completeList = Object.values(assessments)
    .filter(a => a.status === 'complete')
    .sort((a, b) => a.id - b.id)

  const selectedId = selectedAssessmentId ?? completeList[0]?.id
  const selected: Assessment | undefined = selectedId ? assessments[selectedId] : undefined

  useEffect(() => {
    if (!selected || selected.questions) return
    assessmentsApi.get(selected.id).then(setAssessment)
  }, [selected?.id])

  const handleExport = async (variant: 'student' | 'answer_key') => {
    if (!selectedId) return
    setExporting(true)
    setExportOpen(false)
    try {
      await assessmentsApi.exportPdf(selectedId, variant)
    } finally {
      setExporting(false)
    }
  }

  const handleRegenerate = async () => {
    if (!selectedId) return
    await assessmentsApi.regenerate(selectedId)
  }

  const getLetter = (a: Assessment) => {
    const idx = completeList.findIndex(x => x.id === a.id)
    return idx >= 0 ? String.fromCharCode(65 + idx) : '?'
  }

  const selectedLetter = selected ? getLetter(selected) : '?'
  const showAnswers = activeTab === 'answer-key'

  const tabs = [
    { id: 'questions',  label: 'Questions' },
    { id: 'answer-key', label: 'Answer Key' },
    { id: 'student',    label: 'Student View' },
  ]

  const exportItems = [
    { label: 'Export as PDF', action: () => handleExport('student') },
    { label: 'Export as DOCX', action: () => setExportOpen(false) },
    { label: 'Copy to clipboard', action: () => setExportOpen(false) },
    { label: 'Share link', action: () => setExportOpen(false) },
  ]

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', fontFamily: 'var(--font-sans)' }}>

      {/* Topbar */}
      <div style={{ height: 52, background: 'white', borderBottom: '1px solid #EBEBED', display: 'flex', alignItems: 'center', padding: '0 24px', gap: 12, flexShrink: 0, zIndex: 10 }}>
        <button
          onClick={() => navigate(`/runs/${runId}/progress`)}
          style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 13, color: '#6E6E73', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', padding: '5px 8px', borderRadius: 7 }}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M10 4L6 8l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
          Assessments
        </button>
        <div style={{ width: 1, height: 20, background: '#EBEBED' }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: '#1D1D1F', letterSpacing: '-0.02em' }}>
            {run?.topic ?? 'Assessment'}{selected ? ` — Variant ${selectedLetter}` : ''}
          </div>
          {selected && (
            <div style={{ fontSize: 11, color: '#86868B' }}>
              {frameworkLabel[selected.framework]} · {selected.questions?.length ?? '—'} questions · {(selected.questions?.length ?? 0) >= 1 ? 'High quality' : 'Loading…'}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            onClick={handleRegenerate}
            style={{ display: 'flex', alignItems: 'center', gap: 5, height: 32, padding: '0 12px', border: '1px solid #D2D2D7', borderRadius: 8, fontSize: 12, fontWeight: 500, color: '#1D1D1F', background: 'white', cursor: 'pointer', fontFamily: 'inherit' }}
          >
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" />
              <path d="M5 8h6M8 5l3 3-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            Regenerate
          </button>
          <div style={{ position: 'relative' }}>
            <button
              onClick={() => setExportOpen(o => !o)}
              style={{ display: 'flex', alignItems: 'center', gap: 5, height: 32, padding: '0 12px', border: 'none', borderRadius: 8, fontSize: 12, fontWeight: 500, color: 'white', background: exporting ? '#4A76E8' : '#1A56DB', cursor: 'pointer', fontFamily: 'inherit' }}
            >
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                <path d="M3 11v2h10v-2M8 3v8M5 8l3 3 3-3" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              Export
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                <path d="M2.5 4l2.5 2.5L7.5 4" stroke="white" strokeWidth="1.3" strokeLinecap="round" />
              </svg>
            </button>
            {exportOpen && (
              <div style={{ position: 'absolute', top: 36, right: 0, background: 'white', borderRadius: 10, boxShadow: '0 8px 24px rgba(0,0,0,0.12)', border: '1px solid #EBEBED', padding: 6, minWidth: 150, zIndex: 100 }}>
                {exportItems.map(item => (
                  <div
                    key={item.label}
                    onClick={item.action}
                    style={{ padding: '7px 10px', borderRadius: 7, fontSize: 13, color: '#1D1D1F', cursor: 'pointer', letterSpacing: '-0.01em' }}
                    onMouseEnter={e => (e.currentTarget.style.background = '#F5F5F7')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                  >
                    {item.label}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Body */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* Variant sidebar */}
        <div style={{ width: 264, background: '#F5F5F7', borderRight: '1px solid #EBEBED', display: 'flex', flexDirection: 'column', flexShrink: 0, overflowY: 'auto' }}>
          <div style={{ padding: '14px 12px 8px', fontSize: 10, fontWeight: 500, color: '#B8B8BE', letterSpacing: '0.08em', textTransform: 'uppercase', flexShrink: 0 }}>
            {completeList.length} Variants
          </div>
          <div style={{ padding: '0 8px 12px', display: 'flex', flexDirection: 'column', gap: 2 }}>
            {completeList.map((a, i) => (
              <VariantCard
                key={a.id}
                a={a}
                letter={String.fromCharCode(65 + i)}
                selected={a.id === selectedId}
                onClick={() => { selectAssessment(a.id); setActiveTab('questions') }}
              />
            ))}
          </div>
        </div>

        {/* Main content */}
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>

          {/* Tab bar */}
          <div style={{ padding: '0 32px', borderBottom: '1px solid #EBEBED', background: 'white', flexShrink: 0, display: 'flex', alignItems: 'flex-end', gap: 0 }}>
            {tabs.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                style={{
                  padding: '14px 16px', fontSize: 13, fontWeight: activeTab === tab.id ? 500 : 400,
                  color: activeTab === tab.id ? '#1D1D1F' : '#86868B',
                  background: 'none', border: 'none', borderBottom: `2px solid ${activeTab === tab.id ? '#1A56DB' : 'transparent'}`,
                  marginBottom: -1, cursor: 'pointer', fontFamily: 'inherit', letterSpacing: '-0.01em', transition: 'all 0.12s',
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Document content */}
          {selected ? (
            <div style={{ flex: 1, padding: '36px 48px', maxWidth: 780, animation: 'db-fade-in 0.2s ease' }} key={`${selectedId}-${activeTab}`}>

              {activeTab === 'student' ? (
                <div>
                  <div style={{ padding: '16px 20px', background: '#FFF8EC', border: '1px solid #FFE8B8', borderRadius: 10, marginBottom: 24, fontSize: 13, color: '#8C5100' }}>
                    Student View — answer key and explanations are hidden
                  </div>
                  <div style={{ marginBottom: 24 }}>
                    <h1 style={{ fontSize: 22, fontWeight: 600, color: '#1D1D1F', letterSpacing: '-0.025em', marginBottom: 6 }}>{run?.topic ?? 'Assessment'}</h1>
                    <div style={{ fontSize: 13, color: '#86868B' }}>
                      Assessment Variant {selectedLetter} · {frameworkLabel[selected.framework]} · {selected.questions?.length ?? '—'} questions · Time allowed: 60 minutes
                    </div>
                    <div style={{ height: 1, background: '#EBEBED', margin: '20px 0' }} />
                    <p style={{ fontSize: 13, color: '#515154', lineHeight: 1.6 }}>Answer all questions. Write your student ID at the top of each page. Show all working where required.</p>
                  </div>
                  {selected.questions ? (
                    selected.questions.map(q =>
                      q.type === 'mcq' ? (
                        <div key={q.id} style={{ marginBottom: 20, paddingBottom: 20, borderBottom: '1px solid #F5F5F7' }}>
                          <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
                            <div style={{ width: 22, height: 22, borderRadius: 6, background: '#F5F5F7', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 600, color: '#6E6E73', flexShrink: 0, marginTop: 1 }}>Q{q.order}</div>
                            <p style={{ fontSize: 15, color: '#1D1D1F', lineHeight: 1.6 }}>{q.body}</p>
                          </div>
                          <div style={{ marginLeft: 34, display: 'flex', flexDirection: 'column', gap: 7 }}>
                            {q.options?.map((opt, j) => (
                              <div key={j} style={{ display: 'flex', alignItems: 'flex-start', gap: 9, padding: '8px 12px', borderRadius: 8, fontSize: 13, lineHeight: 1.5, background: '#FAFAFA', border: '1px solid transparent' }}>
                                <div style={{ width: 18, height: 18, borderRadius: '50%', border: '1.5px solid #D2D2D7', flexShrink: 0, marginTop: 1 }} />
                                {opt.body}
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : (
                        <div key={q.id} style={{ marginBottom: 20, paddingBottom: 20, borderBottom: '1px solid #F5F5F7' }}>
                          <div style={{ display: 'flex', gap: 12 }}>
                            <div style={{ width: 22, height: 22, borderRadius: 6, background: '#F3EEFF', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 600, color: '#9B5DE5', flexShrink: 0, marginTop: 1 }}>Q{q.order}</div>
                            <p style={{ fontSize: 15, color: '#1D1D1F', lineHeight: 1.6, letterSpacing: '-0.01em' }}>{q.body}</p>
                          </div>
                        </div>
                      )
                    )
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                      {[100, 80, 90, 70].map((w, i) => (
                        <div key={i} className="db-skeleton" style={{ height: 60, width: `${w}%` }} />
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <div>
                  <div style={{ marginBottom: 28 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                      <h1 style={{ fontSize: 22, fontWeight: 600, color: '#1D1D1F', letterSpacing: '-0.025em', flex: 1 }}>
                        Variant {selectedLetter} — {frameworkLabel[selected.framework]}
                      </h1>
                      <QualityDots score={4} size={8} />
                    </div>
                    <p style={{ fontSize: 13, color: '#86868B', lineHeight: 1.5 }}>
                      Set {selected.control_set_id} · {selected.questions?.length ?? '—'} questions
                    </p>
                    <div style={{ height: 1, background: '#EBEBED', margin: '20px 0' }} />
                  </div>
                  {selected.questions ? (
                    selected.questions.map(q =>
                      q.type === 'mcq'
                        ? <MCQQuestion key={q.id} q={q} showAnswers={showAnswers} />
                        : <ShortAnswerQuestion key={q.id} q={q} />
                    )
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                      {[100, 80, 90, 70].map((w, i) => (
                        <div key={i} className="db-skeleton" style={{ height: 60, width: `${w}%` }} />
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1, color: '#86868B', fontSize: 14 }}>
              Waiting for first assessment to complete…
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
