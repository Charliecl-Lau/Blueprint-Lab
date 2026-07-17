import type { CriterionKey, EvaluationComparison, RubricSnapshot } from '../../types'

const indicatorLabels = {
  agreement: 'Agreement',
  minor_difference: 'Minor difference',
  significant_difference: 'Significant difference',
}

export function EvaluationComparisonPanel({
  comparison,
  rubric,
}: {
  comparison: EvaluationComparison
  rubric: RubricSnapshot
}) {
  const titles = Object.fromEntries(
    rubric.criteria.map((criterion) => [criterion.key, criterion.title]),
  ) as Record<CriterionKey, string>
  return (
    <div className="evaluation-comparison">
      <p className="comparison-caution">Agreement does not establish that either evaluator is correct.</p>
      <div className="comparison-table-wrap">
        <table>
          <caption>Human and LLM rubric score comparison</caption>
          <thead><tr><th scope="col">Rubric Dimension</th><th scope="col">Human Score</th><th scope="col">LLM Score</th><th scope="col">Difference</th><th scope="col">Indicator</th></tr></thead>
          <tbody>
            {comparison.criteria.map((criterion) => (
              <tr key={criterion.criterion_key}>
                <th scope="row">{titles[criterion.criterion_key]}</th>
                <td>{criterion.human_score}</td>
                <td>{criterion.llm_score}</td>
                <td>{criterion.difference > 0 ? '+' : ''}{criterion.difference}</td>
                <td><span className={`comparison-indicator ${criterion.indicator}`}>{indicatorLabels[criterion.indicator]}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <dl className="evaluation-metrics comparison-metrics">
        <div><dt>Mean absolute score difference</dt><dd>{comparison.mean_absolute_score_difference.toFixed(2)}</dd></div>
        <div><dt>Exact agreement rate</dt><dd>{formatRate(comparison.exact_agreement_rate)}</dd></div>
        <div><dt>Agreement within one point</dt><dd>{formatRate(comparison.agreement_within_one_point)}</dd></div>
        <div><dt>Largest disagreement</dt><dd>{titles[comparison.largest_disagreement.criterion_key]} ({comparison.largest_disagreement.absolute_difference})</dd></div>
        <div><dt>Human weighted score</dt><dd>{comparison.human_weighted_score.toFixed(1)}</dd></div>
        <div><dt>LLM weighted score</dt><dd>{comparison.llm_weighted_score.toFixed(1)}</dd></div>
        <div><dt>Overall decision difference</dt><dd>{comparison.decision_difference ? `${comparison.human_overall_decision} / ${comparison.llm_overall_decision}` : 'Same decision'}</dd></div>
      </dl>
    </div>
  )
}

function formatRate(value: number) {
  return `${Math.round(value * 100)}%`
}
