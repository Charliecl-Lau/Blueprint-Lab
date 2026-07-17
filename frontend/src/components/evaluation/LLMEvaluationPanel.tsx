import type { Evaluation } from '../../types'

export function LLMEvaluationPanel({ evaluation }: { evaluation: Evaluation }) {
  const rubricByKey = Object.fromEntries(
    evaluation.rubric_snapshot.criteria.map((criterion) => [criterion.key, criterion]),
  )

  return (
    <div className="llm-evaluation" aria-labelledby="llm-evaluation-title">
      <div className="evaluation-panel-heading">
        <div>
          <p className="evaluation-eyebrow">Read-only supporting information</p>
          <h2 id="llm-evaluation-title">LLM-Generated Evaluation</h2>
        </div>
        <span className="status finalized">Finalized</span>
      </div>
      <dl className="evaluation-metrics">
        <div><dt>Weighted LLM score</dt><dd>{evaluation.weighted_score?.toFixed(1) ?? 'Not available'}</dd></div>
        <div><dt>Critical gate</dt><dd>{evaluation.critical_gate ?? 'Not available'}</dd></div>
        <div><dt>Overall quality decision</dt><dd>{evaluation.overall_decision ?? 'Not available'}</dd></div>
        <div><dt>Instructor readiness</dt><dd>{evaluation.instructor_readiness ?? 'Not available'}</dd></div>
        <div><dt>Evaluation model</dt><dd>{evaluation.evaluation_model ?? 'Not recorded'}</dd></div>
        <div><dt>Model version</dt><dd>{evaluation.evaluation_model_version ?? 'Not recorded'}</dd></div>
        <div><dt>Evaluated</dt><dd>{evaluation.evaluation_timestamp ? new Date(evaluation.evaluation_timestamp).toLocaleString() : 'Not recorded'}</dd></div>
      </dl>

      <div className="llm-criterion-list">
        {evaluation.criteria.map((criterion) => {
          const rubric = rubricByKey[criterion.criterion_key]
          return (
            <article className="llm-criterion-card" key={criterion.criterion_key}>
              <header>
                <h3>{rubric?.title ?? criterion.criterion_key}</h3>
                <span className="weight-badge">{rubric?.weight ?? 0}%</span>
                <strong className="llm-score">{criterion.score ?? '-'} / 5</strong>
              </header>
              <div className="llm-feedback-grid">
                <div><h4>Score justification</h4><p>{criterion.justification ?? 'No justification recorded.'}</p></div>
                <FeedbackList title="Identified strengths" values={criterion.strengths} />
                <FeedbackList title="Identified weaknesses" values={criterion.weaknesses} />
                <FeedbackList title="Suggested improvements" values={criterion.suggested_improvements} />
                <FeedbackList title="Suggested modifications" values={criterion.suggested_modifications} />
              </div>
            </article>
          )
        })}
      </div>

      <section className="llm-overall-feedback" aria-labelledby="llm-overall-title">
        <h3 id="llm-overall-title">Overall LLM Feedback</h3>
        <FeedbackList title="Major strengths" values={evaluation.major_strengths} />
        <FeedbackList title="Major weaknesses" values={evaluation.major_weaknesses} />
        <div><h4>Highest-priority revision</h4><p>{evaluation.highest_priority_revision ?? 'None recorded.'}</p></div>
        <div><h4>Recommended instructor action</h4><p>{evaluation.recommended_action ?? 'None recorded.'}</p></div>
      </section>
    </div>
  )
}

function FeedbackList({ title, values }: { title: string; values: string[] }) {
  return (
    <div>
      <h4>{title}</h4>
      {values.length ? <ul>{values.map((value) => <li key={value}>{value}</li>)}</ul> : <p>None recorded.</p>}
    </div>
  )
}
