import { useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Badge } from '../components/ui/Badge'
import { useSSE } from '../hooks/useSSE'
import { useRunStore } from '../store/runStore'
import { runsApi } from '../api/runs'
import type { Assessment, Stage } from '../types'

const stageConfig: Record<Stage, { label: string; variant: 'default' | 'info' | 'success' | 'warning' | 'error'; dot: boolean }> = {
  pending:    { label: 'Queued',      variant: 'default',  dot: true },
  prompting:  { label: 'Generating',  variant: 'warning',  dot: true },
  planning:   { label: 'Generating',  variant: 'warning',  dot: true },
  validating: { label: 'Generating',  variant: 'warning',  dot: true },
  generating: { label: 'Generating',  variant: 'warning',  dot: true },
  complete:   { label: 'Complete',    variant: 'success',  dot: true },
  error:      { label: 'Failed',      variant: 'error',    dot: true },
}

const frameworkLabel: Record<string, string> = { forge: 'Forge', openai: 'OpenAI', risen: 'RISEN' }

// ── sub-components ─────────────────────────────────────────────────────────
function QualityDots({ score }: { score: number }) {
  return (
    <div style={{ display: 'flex', gap: 3 }}>
      {[1, 2, 3, 4, 5].map(i => (
        <div key={i} style={{ width: 6, height: 6, borderRadius: '50%', background: i <= score ? '#1A56DB' : '#EBEBED' }} />
      ))}
    </div>
  )
}

function SkeletonLine({ width = '100%', height = 11, style = {} }: { width?: string; height?: number; style?: React.CSSProperties }) {
  return (
    <div style={{
      height, width, borderRadius: 6,
      background: 'linear-gradient(90deg,#F5F5F7 25%,#EBEBED 50%,#F5F5F7 75%)',
      backgroundSize: '400px 100%',
      animation: 'progress-bar 1.4s linear infinite',
      ...style,
    }} />
  )
}

function AssessmentCard({ a }: { a: Assessment }) {
  const cfg = stageConfig[a.status]
  const isGenerating = ['prompting', 'planning', 'validating', 'generating'].includes(a.status)
  const isComplete = a.status === 'complete'
  const isQueued = a.status === 'pending'
  const letter = frameworkLabel[a.framework]?.slice(0, 1) ?? '?'

  return (
    <div style={{
      background: 'white', borderRadius: 14, border: '1px solid #EBEBED', padding: '18px 20px',
      boxShadow: isComplete ? '0 1px 3px rgba(0,0,0,0.06)' : 'none',
      animation: 'db-fade-in 0.25s ease', transition: 'box-shadow 0.2s',
      opacity: isQueued ? 0.7 : 1,
    }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 28, height: 28, borderRadius: 8, flexShrink: 0,
            background: isComplete ? '#1A56DB' : isGenerating ? '#FF9F0A' : '#EBEBED',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 12, fontWeight: 700, color: isQueued ? '#86868B' : 'white',
          }}>
            {letter}
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 500, color: '#1D1D1F', letterSpacing: '-0.01em' }}>{frameworkLabel[a.framework]}</div>
            <div style={{ fontSize: 11, color: '#86868B' }}>Set {a.control_set_id}</div>
          </div>
        </div>
        <Badge variant={cfg.variant} dot={cfg.dot} size="sm">{cfg.label}</Badge>
      </div>

      {/* Body — complete */}
      {isComplete && (
        <div style={{ animation: 'db-fade-in 0.3s ease' }}>
          <p style={{ fontSize: 12, color: '#515154', lineHeight: 1.55, marginBottom: 12, letterSpacing: '-0.01em' }}>
            Ready to review
          </p>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <QualityDots score={0} />
            <span style={{ fontSize: 11, color: '#86868B' }}>—</span>
          </div>
        </div>
      )}

      {/* Body — generating */}
      {isGenerating && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <span style={{ fontSize: 11, color: '#86868B', display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ display: 'inline-block', width: 10, height: 10, border: '1.5px solid #FF9F0A', borderTopColor: 'transparent', borderRadius: '50%', animation: 'db-spin 0.6s linear infinite' }} />
              {cfg.label}…
            </span>
          </div>
          <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 5 }}>
            <SkeletonLine height={10} width="90%" />
            <SkeletonLine height={10} width="70%" />
            <SkeletonLine height={10} width="80%" />
          </div>
        </div>
      )}

      {/* Body — queued */}
      {isQueued && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <SkeletonLine height={9} width="85%" style={{ opacity: 0.5 }} />
          <SkeletonLine height={9} width="60%" style={{ opacity: 0.4 }} />
          <SkeletonLine height={9} width="75%" style={{ opacity: 0.3 }} />
          <div style={{ marginTop: 4, fontSize: 11, color: '#B8B8BE' }}>Waiting in queue</div>
        </div>
      )}
    </div>
  )
}

// ── main component ─────────────────────────────────────────────────────────
export function ProgressPage() {
  const { runId } = useParams<{ runId: string }>()
  const navigate = useNavigate()
  const { run, assessments, setRun, applySSEEvent } = useRunStore()

  const numericRunId = runId ? Number(runId) : null

  useEffect(() => {
    if (!numericRunId) return
    runsApi.get(numericRunId).then(setRun)
  }, [numericRunId])

  useSSE(numericRunId, applySSEEvent)

  const assessmentList = Object.values(assessments)
  const complete   = assessmentList.filter(a => a.status === 'complete').length
  const generating = assessmentList.filter(a => ['prompting', 'planning', 'validating', 'generating'].includes(a.status)).length
  const queued     = assessmentList.filter(a => a.status === 'pending').length
  const total      = assessmentList.length || 12
  const allDone    = complete === total && total > 0
  const totalProgress = Math.round((complete / total) * 100)

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', fontFamily: 'var(--font-sans)' }}>

      {/* Top bar */}
      <div style={{ height: 52, background: 'white', borderBottom: '1px solid #EBEBED', display: 'flex', alignItems: 'center', padding: '0 28px', gap: 12, flexShrink: 0 }}>
        <button
          onClick={() => navigate('/')}
          style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 13, color: '#6E6E73', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', padding: '5px 8px', borderRadius: 7 }}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M10 4L6 8l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
          Back
        </button>
        <div style={{ width: 1, height: 20, background: '#EBEBED' }} />
        <svg width="22" height="22" viewBox="0 0 40 40" fill="none">
          <rect width="40" height="40" rx="10" fill="#1A56DB" />
          <path d="M9 11h8.5C21.09 11 24 13.91 24 17.5v5C24 26.09 21.09 29 17.5 29H9V11z" stroke="white" strokeWidth="2" fill="none" strokeLinejoin="round" />
        </svg>
        <span style={{ fontSize: 14, fontWeight: 600, color: '#1D1D1F', letterSpacing: '-0.02em' }}>Generating Assessments</span>
        {run && <span style={{ fontSize: 13, color: '#86868B' }}>{run.topic}</span>}
        <div style={{ flex: 1 }} />
        {!allDone && (
          <button
            onClick={() => navigate('/')}
            style={{ fontSize: 13, color: '#FF3B30', background: 'none', border: '1px solid #FFD1CC', borderRadius: 8, padding: '5px 12px', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 500 }}
          >
            Stop generation
          </button>
        )}
        {allDone && (
          <button
            onClick={() => navigate(`/runs/${runId}/viewer`)}
            style={{ fontSize: 13, color: 'white', background: '#1A56DB', border: 'none', borderRadius: 8, padding: '6px 14px', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 500 }}
          >
            View all assessments →
          </button>
        )}
      </div>

      {/* Overall progress bar */}
      <div style={{ height: 3, background: '#F5F5F7', flexShrink: 0 }}>
        <div style={{ height: '100%', width: `${totalProgress}%`, background: '#1A56DB', transition: 'width 0.6s ease', borderRadius: '0 99px 99px 0' }} />
      </div>

      {/* Status summary */}
      <div style={{ background: 'white', borderBottom: '1px solid #EBEBED', padding: '10px 28px', display: 'flex', alignItems: 'center', gap: 20, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#30C559' }} />
          <span style={{ fontSize: 13, color: '#1D1D1F' }}><strong>{complete}</strong> complete</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#FF9F0A', animation: 'db-pulse 1.2s ease infinite' }} />
          <span style={{ fontSize: 13, color: '#1D1D1F' }}><strong>{generating}</strong> generating</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#D2D2D7' }} />
          <span style={{ fontSize: 13, color: '#1D1D1F' }}><strong>{queued}</strong> queued</span>
        </div>
        <div style={{ marginLeft: 'auto', fontSize: 12, color: '#86868B' }}>
          {allDone
            ? 'All variants complete — ready to review'
            : `~${Math.max(1, Math.round((total - complete) * 0.5))} min remaining`}
        </div>
      </div>

      {/* Grid */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px 28px', background: '#F5F5F7' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 14, maxWidth: 1200 }}>
          {assessmentList.map(a => <AssessmentCard key={a.id} a={a} />)}
        </div>
      </div>
    </div>
  )
}
