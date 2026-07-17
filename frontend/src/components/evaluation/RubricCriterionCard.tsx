import type { EvaluationCriterion, HumanCriterionPatch, RubricCriterion } from '../../types'

const issueFlags = [
  'Technical error',
  'Missing information',
  'Ambiguous wording',
  'Incorrect model answer',
  'Course misalignment',
  "Bloom's level mismatch",
  'Weak materials science context',
  'Incomplete solution',
  'Prompt instruction not followed',
  'Other',
]

function scoreGuidance(criterion: RubricCriterion, score: number) {
  if (score === 1 || score === 3 || score === 5) return criterion.anchors[String(score) as '1' | '3' | '5']
  return score === 2
    ? 'Performance between the score 1 and score 3 anchors.'
    : 'Performance between the score 3 and score 5 anchors.'
}

export function RubricCriterionCard({
  rubric,
  value,
  disabled,
  onChange,
  onBlur,
}: {
  rubric: RubricCriterion
  value?: EvaluationCriterion
  disabled: boolean
  onChange: (patch: HumanCriterionPatch) => void
  onBlur: () => void
}) {
  const selectedFlags = value?.issue_flags ?? []
  const titleId = `criterion-${rubric.key}-title`
  return (
    <article className="rubric-card">
      <header>
        <div>
          <h3 id={titleId}>{rubric.title}</h3>
          <p>{rubric.description}</p>
        </div>
        <span className="weight-badge">{rubric.weight}%</span>
      </header>
      <fieldset role="radiogroup" aria-labelledby={titleId} disabled={disabled}>
        <legend>Score</legend>
        <div className="score-selector">
          {[1, 2, 3, 4, 5].map((score) => (
            <label key={score} title={scoreGuidance(rubric, score)}>
              <input
                type="radio"
                name={`score-${rubric.key}`}
                value={score}
                checked={value?.score === score}
                disabled={disabled}
                aria-label={`${score} - ${scoreGuidance(rubric, score)}`}
                onChange={() => onChange({ criterion_key: rubric.key, score })}
                onBlur={onBlur}
              />
              <span>{score}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <details className="score-guidance">
        <summary>Score-level guidance</summary>
        <ol>
          {[1, 2, 3, 4, 5].map((score) => <li key={score}><strong>{score}</strong> {scoreGuidance(rubric, score)}</li>)}
        </ol>
      </details>
      <label className="grading-field">
        Reviewer Comment
        <textarea
          rows={4}
          disabled={disabled}
          value={value?.comment ?? ''}
          placeholder="Explain the strengths, weaknesses, errors, or concerns that influenced this score."
          onChange={(event) => onChange({ criterion_key: rubric.key, comment: event.target.value })}
          onBlur={onBlur}
        />
      </label>
      <label className="grading-field">
        Suggested Modification (optional)
        <textarea
          rows={3}
          disabled={disabled}
          value={value?.suggested_modification ?? ''}
          placeholder="Describe a specific change that would improve this assessment."
          onChange={(event) => onChange({ criterion_key: rubric.key, suggested_modification: event.target.value })}
          onBlur={onBlur}
        />
      </label>
      <fieldset className="issue-flags" disabled={disabled}>
        <legend>Issue Flags (optional)</legend>
        <div>
          {issueFlags.map((flag) => (
            <label key={flag}>
              <input
                type="checkbox"
                disabled={disabled}
                checked={selectedFlags.includes(flag)}
                onChange={(event) => onChange({
                  criterion_key: rubric.key,
                  issue_flags: event.target.checked
                    ? [...selectedFlags, flag]
                    : selectedFlags.filter((item) => item !== flag),
                })}
                onBlur={onBlur}
              />
              {flag}
            </label>
          ))}
        </div>
      </fieldset>
    </article>
  )
}
