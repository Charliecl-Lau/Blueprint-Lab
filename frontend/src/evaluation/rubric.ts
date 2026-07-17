import type { CriterionKey } from '../types'


export const criterionKeys = [
  'technical_correctness',
  'course_alignment',
  'blooms_alignment',
  'clarity_solution',
  'materials_context',
] as const satisfies readonly CriterionKey[]

const weights: Record<CriterionKey, number> = {
  technical_correctness: 30,
  course_alignment: 25,
  blooms_alignment: 10,
  clarity_solution: 25,
  materials_context: 10,
}

export function calculateDraftScores(
  scores: Partial<Record<CriterionKey, number>>,
) {
  const complete = criterionKeys.every((key) => (
    Number.isInteger(scores[key]) && scores[key]! >= 1 && scores[key]! <= 5
  ))
  if (!complete) return null

  const weighted_score = criterionKeys.reduce(
    (total, key) => total + scores[key]! * weights[key] / 5,
    0,
  )
  const critical_gate = scores.technical_correctness! < 3 ? 'FAIL' : 'PASS'
  const overall_decision = critical_gate === 'FAIL'
    ? 'Not ready – critical issue'
    : weighted_score >= 90
      ? 'Instructor-ready'
      : weighted_score >= 80
        ? 'Strong – minor revision'
        : weighted_score >= 70
          ? 'Usable – moderate revision'
          : weighted_score >= 60
            ? 'Substantial revision'
            : 'Not ready'

  return {
    weighted_score,
    critical_gate,
    overall_decision,
    instructor_readiness: overall_decision === 'Instructor-ready'
      ? 'Instructor-ready'
      : 'Revision required',
  }
}
