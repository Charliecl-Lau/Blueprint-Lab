import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe, toHaveNoViolations } from 'jest-axe'
import { beforeEach, expect, test, vi } from 'vitest'
import App from '../App'

expect.extend(toHaveNoViolations)

const criterionKeys = [
  'technical_correctness',
  'course_alignment',
  'blooms_alignment',
  'clarity_solution',
  'materials_context',
] as const

const criterionTitles = [
  'Technical Correctness & Solvability',
  'Course Alignment & Concept Bridge',
  'Bloom’s Taxonomy Alignment & Assessment Design',
  'Clarity, Prompt Alignment & Solution Quality',
  'Materials Science Context & Relevance',
]

function evaluation(type: 'human' | 'llm', finalized = type === 'llm') {
  return {
    id: type === 'human' ? 21 : 22,
    assessment_id: 5,
    question_id: 11,
    evaluation_type: type,
    evaluator_identity: type === 'human' ? 'local-reviewer' : 'gemini-evaluator',
    evaluation_model: type === 'llm' ? 'gemini-evaluator' : null,
    evaluation_model_version: type === 'llm' ? 'evaluation-v1' : null,
    rubric_version: '2026-07-16',
    rubric_snapshot: rubric,
    weighted_score: finalized ? 100 : null,
    critical_gate: finalized ? 'PASS' : null,
    overall_decision: finalized ? 'Instructor-ready' : null,
    instructor_readiness: finalized ? 'Instructor-ready' : null,
    highest_priority_issue: null,
    highest_priority_revision: type === 'llm' ? 'No revision required.' : null,
    overall_comments: null,
    major_strengths: type === 'llm' ? ['Technically sound.'] : [],
    major_weaknesses: [],
    recommended_action: finalized ? 'Accept without revision' : null,
    status: finalized ? 'finalized' : 'draft',
    revision: 1,
    evaluation_timestamp: '2026-07-17T10:00:00Z',
    created_at: '2026-07-17T10:00:00Z',
    updated_at: '2026-07-17T10:00:00Z',
    finalized_at: finalized ? '2026-07-17T10:05:00Z' : null,
    criteria: type === 'llm' || finalized
      ? criterionKeys.map((key) => ({
          criterion_key: key,
          score: type === 'llm' ? 5 : 4,
          comment: null,
          suggested_modification: null,
          issue_flags: [],
          justification: type === 'llm' ? `Evidence for ${key}.` : null,
          strengths: type === 'llm' ? ['Clear strength.'] : [],
          weaknesses: [],
          suggested_improvements: [],
          suggested_modifications: [],
        }))
      : [],
  }
}

const rubric = {
  version: '2026-07-16',
  criteria: criterionKeys.map((key, index) => ({
    key,
    title: criterionTitles[index],
    weight: [30, 25, 10, 25, 10][index],
    covers: 'Quality',
    description: `Authoritative description for ${criterionTitles[index]}.`,
    comment_prompt: 'Explain the score.',
    anchors: {
      '1': 'Substantive problems.',
      '3': 'Generally acceptable with revisions.',
      '5': 'Instructor-ready quality.',
    },
  })),
}

function context(humanFinalized = false) {
  return {
    experiment_id: 1,
    run_id: 8,
    assessment_id: 5,
    question_id: 11,
    question: {
      type: 'long_answer',
      metadata: {
        question_title: 'Chemical potential and phase stability',
        question_type: 'long_answer',
        difficulty_level: 'advanced',
        intended_assessment_setting: 'Homework',
        mse202_concepts: ['Equilibrium'],
        mse302_concepts: ['Chemical potential'],
        concept_map_bridge: 'A bridge.',
        materials_science_context: 'An alloy.',
      },
      body: 'Analyze which alloy phase is stable.',
      model_answer: 'The phase with lower Gibbs energy is stable.',
    },
    rubric,
    llm_evaluation: evaluation('llm'),
    human_evaluation: evaluation('human', humanFinalized),
    previous_question_id: 10,
    next_question_id: 12,
    viewer_path: '/experiments/1/viewer/8',
  }
}

function comparison() {
  const criteria = criterionKeys.map((key) => ({
    criterion_key: key,
    human_score: 4,
    llm_score: 5,
    difference: -1,
    absolute_difference: 1,
    indicator: 'minor_difference',
  }))
  return {
    criteria,
    mean_absolute_score_difference: 1,
    exact_agreement_rate: 0,
    agreement_within_one_point: 1,
    largest_disagreement: criteria[0],
    human_weighted_score: 80,
    llm_weighted_score: 100,
    weighted_score_difference: -20,
    human_overall_decision: 'Strong – minor revision',
    llm_overall_decision: 'Instructor-ready',
    decision_difference: true,
  }
}

function mockApi(initialContext = context()) {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input, init) => {
    const url = String(input)
    if (url.endsWith('/api/assessment-questions/11/grading-context')) {
      return { ok: true, json: async () => initialContext } as Response
    }
    if (url.endsWith('/llm-access') && init?.method === 'POST') {
      return {
        ok: true,
        json: async () => ({
          first_opened_at: '2026-07-17T10:01:00Z',
          opened_before_finalization: true,
        }),
      } as Response
    }
    if (url.endsWith('/evaluation-comparison')) {
      return { ok: true, json: async () => comparison() } as Response
    }
    if (url.endsWith('/api/evaluations/21') && init?.method === 'PATCH') {
      const body = JSON.parse(String(init.body))
      return {
        ok: true,
        json: async () => ({
          ...initialContext.human_evaluation,
          revision: body.revision + 1,
          criteria: body.criteria ?? initialContext.human_evaluation.criteria,
          overall_comments: body.overall_comments ?? null,
        }),
      } as Response
    }
    if (url.endsWith('/api/evaluations/21/finalize') && init?.method === 'POST') {
      return {
        ok: true,
        json: async () => ({
          ...initialContext.human_evaluation,
          status: 'finalized',
          revision: 2,
          finalized_at: '2026-07-17T10:10:00Z',
          weighted_score: 80,
          critical_gate: 'PASS',
          overall_decision: 'Strong – minor revision',
          instructor_readiness: 'Revision required',
        }),
      } as Response
    }
    if (url.endsWith('/api/evaluations/21/reopen') && init?.method === 'POST') {
      return {
        ok: true,
        json: async () => ({
          ...initialContext.human_evaluation,
          status: 'reopened',
          revision: 3,
          finalized_at: null,
        }),
      } as Response
    }
    return { ok: true, json: async () => ({}) } as Response
  }))
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  window.history.replaceState({}, '', '/assessments/5/questions/11/grade')
})

test('renders LLM first and closed, Human expanded, and comparison gated', async () => {
  mockApi()
  render(<App />)

  expect(await screen.findByRole('heading', { name: 'Chemical potential and phase stability' })).toBeVisible()
  expect(screen.queryByRole('heading', { name: 'Assessment Summary' })).not.toBeInTheDocument()
  const controls = [
    screen.getByRole('button', { name: 'View LLM Assessment' }),
    screen.getByRole('button', { name: 'Human Assessment' }),
    screen.getByRole('button', { name: 'Compare Human and LLM Results' }),
  ]
  expect(controls.map((item) => item.textContent)).toEqual([
    'View LLM Assessment',
    'Human Assessment',
    'Compare Human and LLM Results',
  ])
  expect(controls[0]).toHaveAttribute('aria-expanded', 'false')
  expect(controls[1]).toHaveAttribute('aria-expanded', 'true')
  expect(controls[2]).toBeDisabled()
  expect(screen.getAllByRole('radiogroup')).toHaveLength(5)
  expect(screen.getByRole('button', { name: 'Finalize Human Assessment' })).toBeDisabled()
})

test('blur autosaves only the changed field with the current revision', async () => {
  mockApi()
  const user = userEvent.setup()
  render(<App />)
  const group = (await screen.findAllByRole('radiogroup'))[0]

  await user.click(within(group).getByRole('radio', { name: /^4/ }))
  await user.tab()

  await waitFor(() => {
    const patchCall = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'PATCH')
    expect(patchCall).toBeDefined()
    expect(JSON.parse(String(patchCall?.[1]?.body))).toEqual({
      revision: 1,
      criteria: [{ criterion_key: 'technical_correctness', score: 4 }],
    })
  })
  expect(within(group).getAllByRole('radio')).toHaveLength(5)
})

test('reset restores the last server response and dirty navigation asks for confirmation', async () => {
  mockApi()
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  render(<App />)
  const comments = await screen.findByLabelText('Overall reviewer comments')
  fireEvent.change(comments, { target: { value: 'Unsaved local note' } })
  expect(comments).toHaveValue('Unsaved local note')
  fireEvent.click(screen.getByRole('button', { name: 'Next Assessment' }))
  expect(confirm).toHaveBeenCalled()
  expect(window.location.pathname).toBe('/assessments/5/questions/11/grade')

  fireEvent.click(screen.getByRole('button', { name: 'Reset Unsaved Changes' }))
  expect(comments).toHaveValue('')
})

test('opening LLM records disclosure once and reveals read-only evaluation', async () => {
  mockApi()
  const user = userEvent.setup()
  render(<App />)
  const trigger = await screen.findByRole('button', { name: 'View LLM Assessment' })

  await user.click(trigger)
  expect(screen.getByRole('heading', { name: 'LLM-Generated Evaluation' })).toBeVisible()
  expect(screen.getByText('Evidence for technical_correctness.')).toBeVisible()
  await user.click(trigger)
  await user.click(trigger)

  expect(vi.mocked(fetch).mock.calls.filter(([input]) => String(input).endsWith('/llm-access'))).toHaveLength(1)
})

test('five scores enable finalization, lock controls, and explicit reopen unlocks', async () => {
  mockApi()
  const user = userEvent.setup()
  render(<App />)
  for (const group of await screen.findAllByRole('radiogroup')) {
    await user.click(within(group).getByRole('radio', { name: /^4/ }))
  }
  const finalize = screen.getByRole('button', { name: 'Finalize Human Assessment' })
  expect(finalize).toBeEnabled()
  await user.click(screen.getByRole('button', { name: 'Save Draft' }))
  await user.click(finalize)

  expect(await screen.findByText('Finalized')).toBeVisible()
  expect(screen.getAllByRole('radio').every((item) => item.hasAttribute('disabled'))).toBe(true)
  const reopen = screen.getByRole('button', { name: 'Reopen Evaluation' })
  await user.click(reopen)
  expect(await screen.findByText('Reopened')).toBeVisible()
  expect(screen.getAllByRole('radio').some((item) => !item.hasAttribute('disabled'))).toBe(true)
})

test('finalized review enables neutral comparison and adjacent navigation', async () => {
  mockApi(context(true))
  const user = userEvent.setup()
  render(<App />)
  const comparisonButton = await screen.findByRole('button', { name: 'Compare Human and LLM Results' })
  expect(comparisonButton).toBeEnabled()
  await user.click(comparisonButton)

  expect(await screen.findByText('Agreement does not establish that either evaluator is correct.')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Previous Assessment' })).toBeEnabled()
  expect(screen.getByRole('button', { name: 'Next Assessment' })).toBeEnabled()
  expect(screen.getByRole('button', { name: 'Return to Assessment Viewer' })).toBeEnabled()
})

test('grading page has no automated accessibility violations', async () => {
  mockApi()
  const { container } = render(<App />)
  expect(await screen.findByRole('heading', { name: 'Chemical potential and phase stability' })).toBeVisible()
  expect(await axe(container)).toHaveNoViolations()
})
