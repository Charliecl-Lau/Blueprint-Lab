import { expect, test } from 'vitest'
import { calculateDraftScores, criterionKeys } from './rubric'


test('mirrors backend rubric weights and critical gate', () => {
  const scores = Object.fromEntries(criterionKeys.map((key) => [key, 5]))
  scores.technical_correctness = 2

  expect(calculateDraftScores(scores)).toEqual({
    weighted_score: 82,
    critical_gate: 'FAIL',
    overall_decision: 'Not ready – critical issue',
    instructor_readiness: 'Revision required',
  })
})


test('returns null calculations until all five valid scores exist', () => {
  expect(calculateDraftScores({ technical_correctness: 3 })).toBeNull()
  expect(calculateDraftScores(Object.fromEntries(
    criterionKeys.map((key) => [key, key === 'technical_correctness' ? 6 : 4]),
  ))).toBeNull()
})


test('uses the same decision thresholds as the authoritative backend rubric', () => {
  expect(calculateDraftScores(Object.fromEntries(
    criterionKeys.map((key) => [key, 4]),
  ))?.overall_decision).toBe('Strong – minor revision')
})
