import type { Evaluation, RubricSnapshot } from '../../types'

export function ReadOnlyHumanEvaluationPanel({
  evaluation,
  rubric,
}: {
  evaluation: Evaluation | null
  rubric: RubricSnapshot
}) {
  if (!evaluation) return <p>Human evaluation not completed</p>

  return <section aria-labelledby="finalized-human-evaluation-title">
    <div className="evaluation-panel-heading">
      <div>
        <p className="evaluation-eyebrow">Read-only saved review</p>
        <h2 id="finalized-human-evaluation-title">Finalized Human Evaluation</h2>
      </div>
      <span className="status finalized">Finalized</span>
    </div>
    <dl className="evaluation-metrics">
      <div><dt>Weighted score</dt><dd>{evaluation.weighted_score?.toFixed(1) ?? 'Not available'}</dd></div>
      <div><dt>Critical gate</dt><dd>{evaluation.critical_gate ?? 'Not available'}</dd></div>
      <div><dt>Overall quality decision</dt><dd>{evaluation.overall_decision ?? 'Not available'}</dd></div>
      <div><dt>Instructor readiness</dt><dd>{evaluation.instructor_readiness ?? 'Not available'}</dd></div>
    </dl>

    <div className="read-only-human-criteria">
      {rubric.criteria.map((definition) => {
        const result = evaluation.criteria.find(
          (item) => item.criterion_key === definition.key,
        )
        return <article className="read-only-human-criterion" key={definition.key}>
          <header>
            <h3>{definition.title}</h3>
            <strong>{result?.score ?? '-'} / 5</strong>
          </header>
          <p>{result?.comment || 'No reviewer comment'}</p>
          {result?.suggested_modification && <p>
            <strong>Suggested modification:</strong> {result.suggested_modification}
          </p>}
          {Boolean(result?.issue_flags.length) && <ul>
            {result?.issue_flags.map((flag) => <li key={flag}>{flag}</li>)}
          </ul>}
        </article>
      })}
    </div>

    <div className="read-only-human-overall">
      {evaluation.overall_comments && <p><strong>Overall comments:</strong> {evaluation.overall_comments}</p>}
      {evaluation.recommended_action && <p><strong>Recommended action:</strong> {evaluation.recommended_action}</p>}
    </div>
  </section>
}
