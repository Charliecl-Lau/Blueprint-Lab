import type { Evaluation, RecommendedAction } from '../../types'
import { calculateDraftScores } from '../../evaluation/rubric'

const actions: RecommendedAction[] = [
  'Accept without revision',
  'Accept with minor revision',
  'Revise before use',
  'Major revision required',
  'Reject assessment',
]

export function HumanEvaluationSummary({
  evaluation,
  disabled,
  onOverallChange,
  onBlur,
}: {
  evaluation: Evaluation
  disabled: boolean
  onOverallChange: (field: 'highest_priority_issue' | 'overall_comments' | 'recommended_action', value: string | null) => void
  onBlur: () => void
}) {
  const scores = Object.fromEntries(evaluation.criteria.map((item) => [item.criterion_key, item.score ?? undefined]))
  const preview = calculateDraftScores(scores)
  return (
    <section className="human-evaluation-summary" aria-labelledby="human-summary-title">
      <h3 id="human-summary-title">Human Assessment Summary</h3>
      <dl className="evaluation-metrics">
        <div><dt>Weighted score</dt><dd>{preview ? `${preview.weighted_score.toFixed(1)} / 100` : 'Pending all five scores'}</dd></div>
        <div><dt>Critical gate</dt><dd>{preview?.critical_gate ?? 'Pending'}</dd></div>
        <div><dt>Overall quality decision</dt><dd>{preview?.overall_decision ?? 'Pending'}</dd></div>
        <div><dt>Instructor readiness</dt><dd>{preview?.instructor_readiness ?? 'Pending'}</dd></div>
      </dl>
      <label className="grading-field">
        Highest-priority issue
        <input
          disabled={disabled}
          value={evaluation.highest_priority_issue ?? ''}
          onChange={(event) => onOverallChange('highest_priority_issue', event.target.value)}
          onBlur={onBlur}
        />
      </label>
      <label className="grading-field">
        Overall reviewer comments
        <textarea
          rows={5}
          disabled={disabled}
          value={evaluation.overall_comments ?? ''}
          onChange={(event) => onOverallChange('overall_comments', event.target.value)}
          onBlur={onBlur}
        />
      </label>
      <label className="grading-field">
        Recommended action
        <select
          disabled={disabled}
          value={evaluation.recommended_action ?? ''}
          onChange={(event) => onOverallChange('recommended_action', event.target.value || null)}
          onBlur={onBlur}
        >
          <option value="">Select an action</option>
          {actions.map((action) => <option key={action} value={action}>{action}</option>)}
        </select>
      </label>
    </section>
  )
}
