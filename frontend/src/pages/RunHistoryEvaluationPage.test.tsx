import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe, toHaveNoViolations } from 'jest-axe'
import { beforeEach, expect, test, vi } from 'vitest'
import App from '../App'
import type { Evaluation, HistoryEvaluationContext, RubricSnapshot } from '../types'

expect.extend(toHaveNoViolations)

const criterionKeys = [
  'technical_correctness',
  'course_alignment',
  'blooms_alignment',
  'clarity_solution',
  'materials_context',
] as const

const rubric: RubricSnapshot = {
  version: '2026-07-16',
  criteria: criterionKeys.map((key, index) => ({
    key,
    title: [
      'Technical Correctness & Solvability',
      'Course Alignment & Concept Bridge',
      'Bloom Taxonomy Alignment & Assessment Design',
      'Clarity, Prompt Alignment & Solution Quality',
      'Materials Science Context & Relevance',
    ][index],
    weight: [30, 25, 10, 25, 10][index],
    covers: 'Quality',
    description: 'Authoritative criterion description.',
    comment_prompt: 'Explain the score.',
    anchors: { '1': 'Poor', '3': 'Acceptable', '5': 'Excellent' },
  })),
}

function evaluation(type: 'human' | 'llm'): Evaluation {
  return {
    id: type === 'human' ? 21 : 22,
    assessment_id: 5,
    question_id: 11,
    evaluation_type: type,
    evaluator_identity: type === 'human' ? 'local-reviewer' : 'gemini-evaluator',
    evaluation_model: type === 'llm' ? 'gemini-evaluator' : null,
    evaluation_model_version: type === 'llm' ? 'evaluation-v1' : null,
    rubric_version: rubric.version,
    rubric_snapshot: rubric,
    weighted_score: type === 'human' ? 80 : 100,
    critical_gate: 'PASS',
    overall_decision: type === 'human' ? 'Strong - minor revision' : 'Instructor-ready',
    instructor_readiness: type === 'human' ? 'Revision required' : 'Instructor-ready',
    highest_priority_issue: null,
    highest_priority_revision: type === 'llm' ? 'No revision required.' : null,
    overall_comments: type === 'human' ? 'Saved human review.' : null,
    major_strengths: type === 'llm' ? ['Technically sound.'] : [],
    major_weaknesses: [],
    recommended_action: type === 'human' ? 'Accept with minor revision' : 'Accept without revision',
    status: 'finalized',
    revision: 2,
    evaluation_timestamp: '2026-07-17T10:00:00Z',
    created_at: '2026-07-17T10:00:00Z',
    updated_at: '2026-07-17T10:00:00Z',
    finalized_at: '2026-07-17T10:05:00Z',
    criteria: criterionKeys.map((key) => ({
      criterion_key: key,
      score: type === 'human' ? 4 : 5,
      comment: type === 'human' ? `Human comment for ${key}.` : null,
      suggested_modification: type === 'human' && key === criterionKeys[0] ? 'Clarify the phase boundary.' : null,
      issue_flags: type === 'human' && key === criterionKeys[0] ? ['minor_clarity'] : [],
      justification: type === 'llm' ? `Evidence for ${key}.` : null,
      strengths: type === 'llm' ? ['Clear strength.'] : [],
      weaknesses: [],
      suggested_improvements: [],
      suggested_modifications: [],
    })),
  }
}

function finalizedHistoryContext(): HistoryEvaluationContext {
  const criteria = criterionKeys.map((key) => ({
    criterion_key: key,
    human_score: 4,
    llm_score: 5,
    difference: -1,
    absolute_difference: 1,
    indicator: 'minor_difference' as const,
  }))
  return {
    run_id: 8,
    assessment_id: 5,
    question_id: 11,
    question: {
      type: 'long_answer',
      metadata: {
        question_title: 'Chemical potential and phase stability',
        question_type: 'long_answer',
        difficulty_level: 'advanced',
        mse202_concepts: ['Equilibrium'],
        mse302_concepts: ['Chemical potential'],
        concept_map_bridge: 'A bridge.',
        materials_science_context: 'An alloy.',
        estimated_time_minutes: 10,
      },
      body: 'Analyze which alloy phase is stable.',
      model_answer: 'The phase with lower Gibbs energy is stable.',
    },
    rubric,
    llm_evaluation: evaluation('llm'),
    human_evaluation: evaluation('human'),
    comparison: {
      criteria,
      mean_absolute_score_difference: 1,
      exact_agreement_rate: 0,
      agreement_within_one_point: 1,
      largest_disagreement: criteria[0],
      human_weighted_score: 80,
      llm_weighted_score: 100,
      weighted_score_difference: -20,
      human_overall_decision: 'Strong - minor revision',
      llm_overall_decision: 'Instructor-ready',
      decision_difference: true,
    },
    previous_question_id: 10,
    next_question_id: 12,
    history_path: '/runs/8/history',
  }
}

function mockHistoryContext(context: HistoryEvaluationContext) {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => context } as Response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function renderAtHistoryEvaluation() {
  window.history.replaceState({}, '', '/runs/8/history/questions/11/evaluation')
  return render(<App />)
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  window.history.replaceState({}, '', '/')
})

test('renders history evaluations without editable controls', async () => {
  mockHistoryContext(finalizedHistoryContext())
  renderAtHistoryEvaluation()

  expect(await screen.findByRole('heading', { name: 'Chemical potential and phase stability' })).toBeVisible()
  expect(screen.queryByRole('radio')).not.toBeInTheDocument()
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Save Draft|Finalize|Reopen|Reset/ })).not.toBeInTheDocument()
  expect(screen.getByText('Saved human review.')).toBeVisible()
})

test('shows missing finalized human evaluation', async () => {
  mockHistoryContext({ ...finalizedHistoryContext(), human_evaluation: null, comparison: null })
  renderAtHistoryEvaluation()

  expect(await screen.findAllByText('Human evaluation not completed')).toHaveLength(2)
  expect(screen.getByRole('button', { name: 'Compare Human and LLM Results' })).toBeDisabled()
})

test('uses approved accordion defaults', async () => {
  mockHistoryContext(finalizedHistoryContext())
  renderAtHistoryEvaluation()

  expect(await screen.findByRole('button', { name: 'View LLM Assessment' })).toHaveAttribute('aria-expanded', 'false')
  expect(screen.getByRole('button', { name: 'Human Assessment' })).toHaveAttribute('aria-expanded', 'true')
  expect(screen.getByRole('button', { name: 'Compare Human and LLM Results' })).toHaveAttribute('aria-expanded', 'false')
})

test('Previous and Next remain under the selected run', async () => {
  mockHistoryContext(finalizedHistoryContext())
  renderAtHistoryEvaluation()

  expect(await screen.findByRole('link', { name: 'Previous Assessment' })).toHaveAttribute('href', '/runs/8/history/questions/10/evaluation')
  expect(screen.getByRole('link', { name: 'Next Assessment' })).toHaveAttribute('href', '/runs/8/history/questions/12/evaluation')
  expect(screen.getByRole('link', { name: 'Return to Run History' })).toHaveAttribute('href', '/runs/8/history')
})

test('opening panels sends no mutation request', async () => {
  const fetchMock = mockHistoryContext(finalizedHistoryContext())
  const user = userEvent.setup()
  renderAtHistoryEvaluation()

  await user.click(await screen.findByRole('button', { name: 'View LLM Assessment' }))
  await user.click(screen.getByRole('button', { name: 'Compare Human and LLM Results' }))
  expect(fetchMock.mock.calls.every(([, init]) => !init?.method)).toBe(true)
  expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith('/llm-access'))).toBe(false)
})

test('failed-run evaluation redirects to limited history', async () => {
  window.history.replaceState({}, '', '/runs/9/history/questions/44/evaluation')
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: false,
    status: 409,
    json: async () => ({ detail: 'Completed runs only' }),
  }))
  render(<App />)

  await waitFor(() => expect(window.location.pathname).toBe('/runs/9/history'))
})

test('history evaluation has no automated accessibility violations', async () => {
  mockHistoryContext(finalizedHistoryContext())
  const { container } = renderAtHistoryEvaluation()
  await screen.findByRole('heading', { name: 'Chemical potential and phase stability' })

  expect(await axe(container)).toHaveNoViolations()
})
