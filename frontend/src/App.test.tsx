import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import { axe, toHaveNoViolations } from 'jest-axe'
import App from './App'
import { normalizeExperiment } from './api/experiments'
import { useRunStore } from './store/runStore'

expect.extend(toHaveNoViolations)

test('normalizes deprecated generation collections at the API boundary', () => {
  const legacyRun = { id: 7, condition_id: 2, run_number: 1, status: 'complete' as const }
  const response = normalizeExperiment({
    id: 42,
    course: 'Statics',
    topic: 'Equilibrium',
    learning_objectives: 'Resolve forces',
    assessment_type: 'mixed',
    difficulty: 'medium',
    number_of_questions: 4,
    estimated_time_minutes: 30,
    cognitive_demand: 'remember_understand',
    additional_instruction: null,
    created_at: '2026-07-11T00:00:00Z',
    conditions: [],
    generations: [legacyRun],
  })

  expect(response.runs).toEqual([legacyRun])
})

beforeEach(() => {
  vi.restoreAllMocks()
  useRunStore.getState().reset()
  window.history.replaceState({}, '', '/')
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ id: 42, conditions: [], generations: [] }),
  }))
})

test('shows the streamlined research inputs and removes production controls', () => {
  render(<App />)
  expect(screen.getByRole('heading', { name: 'New Experiment' })).toBeInTheDocument()
  expect(screen.getByLabelText('Course name')).toBeInTheDocument()
  expect(screen.getByLabelText('Estimated student completion time')).toBeInTheDocument()
  expect(screen.getByLabelText('Cognitive demand')).toHaveValue('remember_understand')
  expect(screen.queryByText('Subject area')).not.toBeInTheDocument()
  expect(screen.queryByText("Bloom's taxonomy")).not.toBeInTheDocument()
})

test('submits cognitive demand and optional additional instruction', async () => {
  render(<App />)
  fireEvent.change(screen.getByLabelText('Course name'), { target: { value: 'Statics' } })
  fireEvent.change(screen.getByLabelText('Topic'), { target: { value: 'Equilibrium' } })
  fireEvent.change(screen.getByLabelText('Learning objectives'), { target: { value: 'Resolve forces' } })
  fireEvent.change(screen.getByLabelText('Cognitive demand'), { target: { value: 'evaluate_create' } })
  fireEvent.change(screen.getByLabelText('Additional instruction (optional)'), {
    target: { value: 'Use one laboratory scenario.' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Review' }))

  expect(screen.getByText('Evaluate/Create')).toBeVisible()
  expect(screen.getByText('Use one laboratory scenario.')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Run Experiment' }))

  await waitFor(() => expect(
    vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'POST'),
  ).toBe(true))
  const [, init] = vi.mocked(fetch).mock.calls.find(([, value]) => value?.method === 'POST')!
  expect(JSON.parse(String(init?.body))).toMatchObject({
    cognitive_demand: 'evaluate_create',
    additional_instruction: 'Use one laboratory scenario.',
  })
})

test('reveals and validates content for a selected prompt factor', async () => {
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Prompt Design Factors' }))
  fireEvent.click(screen.getByRole('checkbox', { name: /Reasoning Guidance/ }))
  expect(screen.getByLabelText('Reasoning Guidance content')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Run Experiment' }))
  expect(await screen.findByText('Add content for Reasoning Guidance.')).toBeInTheDocument()
})

test('submits exact enabled factor content and estimated time', async () => {
  render(<App />)
  fireEvent.change(screen.getByLabelText('Course name'), { target: { value: 'Statics' } })
  fireEvent.change(screen.getByLabelText('Topic'), { target: { value: 'Equilibrium' } })
  fireEvent.change(screen.getByLabelText('Learning objectives'), { target: { value: 'Resolve forces' } })
  fireEvent.click(screen.getByRole('button', { name: 'Prompt Design Factors' }))
  fireEvent.click(screen.getByRole('checkbox', { name: /Concept Bridge/ }))
  fireEvent.change(screen.getByLabelText('Concept Bridge content'), { target: { value: 'Connect vectors to force balance.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Run Experiment' }))

  await waitFor(() => expect(
    vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'POST'),
  ).toBe(true))
  const [, init] = vi.mocked(fetch).mock.calls.find(([, value]) => value?.method === 'POST')!
  expect(JSON.parse(String(init?.body))).toMatchObject({
    estimated_time_minutes: 30,
    factors: { concept_bridge: true, reasoning_guidance: false },
    factor_inputs: { concept_bridge: 'Connect vectors to force balance.' },
  })
  expect(new Headers(init?.headers).get('Idempotency-Key')).toBeTruthy()
})

test('navigates the three form sections from the side panel and section buttons', () => {
  render(<App />)
  expect(screen.getByRole('navigation', { name: 'Experiment sections' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Assessment Details' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Next: Prompt Design Factors' }))
  expect(screen.getByRole('heading', { name: 'Prompt Design Factors' })).toBeInTheDocument()
  expect(screen.queryByLabelText('Course name')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Review' }))
  expect(screen.getByRole('heading', { name: 'Review Experiment' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Previous' }))
  expect(screen.getByRole('heading', { name: 'Prompt Design Factors' })).toBeInTheDocument()
})

test('shows selected factor inputs beneath the selection grid', () => {
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Prompt Design Factors' }))
  const grid = screen.getByRole('group', { name: 'Prompt factor selection' })
  expect(grid).toHaveClass('factor-grid')
  fireEvent.click(screen.getByRole('checkbox', { name: /Concept Bridge/ }))
  expect(screen.getByRole('region', { name: 'Manual Input' })).toContainElement(screen.getByLabelText('Concept Bridge content'))
})

test('opens an incomplete experiment modal and links to missing sections', () => {
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Run Experiment' }))
  expect(screen.getByRole('dialog', { name: 'Complete the required fields before running the experiment.' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Course name' }))
  expect(screen.getByRole('heading', { name: 'Assessment Details' })).toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

test('shows a red grouped dialog and sends no request for an incomplete form', async () => {
  const user = userEvent.setup()
  render(<App />)
  await user.click(screen.getByRole('button', { name: 'Run Experiment' }))

  const dialog = screen.getByRole('dialog', {
    name: 'Complete the required fields before running the experiment.',
  })
  expect(dialog).toHaveClass('validation-dialog')
  expect(within(dialog).getByRole('heading', { name: 'Assessment Details' })).toBeVisible()
  expect(vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0)
})

test('focuses the first invalid field and clears only its error when valid', async () => {
  const user = userEvent.setup()
  render(<App />)
  await user.click(screen.getByRole('button', { name: 'Run Experiment' }))
  await user.click(screen.getByRole('button', { name: 'Close' }))

  const course = screen.getByLabelText('Course name')
  await waitFor(() => expect(course).toHaveFocus())
  expect(course).toHaveAttribute('aria-invalid', 'true')
  await user.type(course, 'Statics')
  expect(course).not.toHaveAttribute('aria-invalid', 'true')
  expect(screen.getByText('Topic is required.')).toBeVisible()
})

test('keeps the run action in a fixed bottom-right action bar', () => {
  render(<App />)
  expect(screen.getByTestId('fixed-run-action')).toHaveClass('fixed-run-action')
})

test('uses valid ARIA semantics and no inappropriate state attributes', async () => {
  const { container } = render(<App />)
  expect(await axe(container)).toHaveNoViolations()
  const detailsStep = screen.getByRole('button', { name: 'Assessment Details' })
  expect(detailsStep).toHaveAttribute('aria-current', 'step')
  expect(detailsStep).not.toHaveAttribute('aria-selected')
  fireEvent.click(screen.getByRole('button', { name: 'Prompt Design Factors' }))
  const factor = screen.getByRole('checkbox', { name: 'Concept Bridge' })
  expect(factor).not.toHaveAttribute('aria-expanded')
  expect(factor).not.toHaveAttribute('aria-checked')
})

test('uses icons instead of numbered markers and supports native keyboard activation', async () => {
  const user = userEvent.setup()
  render(<App />)
  const factorsStep = screen.getByRole('button', { name: 'Prompt Design Factors' })
  expect(screen.queryByTestId('step-number')).not.toBeInTheDocument()
  expect(factorsStep.querySelector('svg')).toBeInTheDocument()
  factorsStep.focus()
  await user.keyboard('{Enter}')
  expect(screen.getByRole('heading', { name: 'Prompt Design Factors' })).toBeInTheDocument()
  const factor = screen.getByRole('checkbox', { name: 'Concept Bridge' })
  factor.focus()
  await user.keyboard(' ')
  expect(factor).toBeChecked()
})

test('uses compact wide run action and chevron section navigation', () => {
  render(<App />)
  expect(screen.queryByText(/Section 1 of 3/)).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Run Experiment' })).toHaveClass('run-button')
  const next = screen.getByRole('button', { name: 'Next: Prompt Design Factors' })
  expect(next.querySelector('svg')).toBeInTheDocument()
  fireEvent.click(next)
  expect(screen.getByRole('button', { name: 'Previous' }).querySelector('svg')).toBeInTheDocument()
})


test.each(['/', '/runs/8/progress', '/experiments/1/viewer/8'])(
  'logo navigates client-side from %s',
  async (path) => {
    window.history.replaceState({}, '', path)
    render(<App />)
    const logo = await screen.findByRole('link', {
      name: 'Go to Blueprint Lab home',
    })
    expect(logo).toHaveAttribute('href', '/')
    await userEvent.click(logo)
    expect(window.location.pathname).toBe('/')
  },
)


test('recent active run reopens run-specific progress', async () => {
  vi.mocked(fetch).mockImplementation(async (input) => {
    if (String(input).endsWith('/api/runs/recent?limit=10')) {
      return {
        ok: true,
        json: async () => ([{
          id: 8,
          experiment_id: 1,
          condition_id: 3,
          run_number: 1,
          status: 'generating',
          topic: 'Equilibrium',
          condition_label: 'Baseline',
          created_at: '2026-07-14T00:00:00Z',
          completed_at: null,
          token_usage: {
            input_tokens: 10,
            output_tokens: 4,
            total_tokens: 14,
            model_calls: 1,
            recording_state: 'in_progress',
            stages: [],
          },
        }]),
      } as Response
    }
    return { ok: true, json: async () => ({ id: 42, conditions: [], runs: [] }) } as Response
  })

  render(<App />)
  await userEvent.click(
    await screen.findByRole('link', { name: /Reopen.*Equilibrium/ }),
  )
  expect(window.location.pathname).toBe('/runs/8/progress')
})

test('shows a top-right shortcut back to the latest run progress', async () => {
  vi.mocked(fetch).mockImplementation(async (input) => {
    if (String(input).includes('/api/runs/recent?limit=')) {
      return {
        ok: true,
        json: async () => ([{
          id: 9,
          experiment_id: 2,
          condition_id: 4,
          run_number: 1,
          status: 'complete',
          topic: 'Dynamics',
          condition_label: 'Baseline',
          created_at: '2026-07-14T01:00:00Z',
          completed_at: '2026-07-14T01:05:00Z',
          token_usage: {
            input_tokens: 30,
            output_tokens: 12,
            total_tokens: 42,
            model_calls: 2,
            recording_state: 'recorded',
            stages: [],
          },
        }]),
      } as Response
    }
    return { ok: true, json: async () => ({}) } as Response
  })

  render(<App />)
  const shortcut = await screen.findByRole('link', {
    name: 'Return to run progress: Dynamics',
  })
  expect(shortcut).toHaveClass('run-progress-shortcut')
  expect(shortcut).toHaveAttribute('href', '/runs/9/progress')
  await userEvent.click(shortcut)
  expect(window.location.pathname).toBe('/runs/9/progress')
})

test('keeps the progress shortcut after returning home when recent runs cannot load', async () => {
  useRunStore.getState().mergeExperiment({
    id: 3,
    course: 'Mechanics',
    topic: 'Kinematics',
    learning_objectives: 'Analyze motion.',
    assessment_type: 'mixed',
    difficulty: 'medium',
    number_of_questions: 4,
    estimated_time_minutes: 30,
    cognitive_demand: 'remember_understand',
    additional_instruction: null,
    created_at: '2026-07-14T02:00:00Z',
    conditions: [],
    runs: [{
      id: 10,
      experiment_id: 3,
      condition_id: 5,
      run_number: 1,
      status: 'generating',
    }],
  })
  vi.mocked(fetch).mockRejectedValue(new Error('recent runs unavailable'))

  render(<App />)

  expect(await screen.findByRole('link', {
    name: 'Return to run progress: Kinematics',
  })).toHaveAttribute('href', '/runs/10/progress')
})

test('does not display token usage on run progress', async () => {
  window.history.replaceState({}, '', '/runs/8/progress')
  vi.mocked(fetch).mockImplementation(async (input) => {
    const url = String(input)
    if (url.endsWith('/api/runs/8')) {
      return {
        ok: true,
        json: async () => ({
          id: 8,
          experiment_id: 1,
          condition_id: 3,
          run_number: 1,
          status: 'complete',
          token_usage: {
            input_tokens: 30,
            output_tokens: 12,
            total_tokens: 42,
            model_calls: 2,
            recording_state: 'recorded',
            stages: [],
          },
        }),
      } as Response
    }
    if (url.endsWith('/api/experiments/1')) {
      return {
        ok: true,
        json: async () => ({
          id: 1,
          course: 'Statics',
          topic: 'Equilibrium',
          learning_objectives: 'Resolve forces',
          assessment_type: 'mixed',
          difficulty: 'medium',
          number_of_questions: 4,
          estimated_time_minutes: 30,
          cognitive_demand: 'remember_understand',
          additional_instruction: null,
          created_at: '2026-07-14T00:00:00Z',
          conditions: [],
          runs: [{ id: 8, experiment_id: 1, condition_id: 3, run_number: 1, status: 'complete' }],
        }),
      } as Response
    }
    return { ok: true, json: async () => ({}) } as Response
  })

  render(<App />)

  expect(await screen.findByText('Equilibrium')).toBeVisible()
  expect(screen.queryByRole('region', { name: 'Token usage' })).not.toBeInTheDocument()
  expect(screen.queryByText('Token usage is loading.')).not.toBeInTheDocument()
})

test('keeps usage in the viewer and renders readable conditions and MathML questions', async () => {
  window.history.replaceState({}, '', '/experiments/1/viewer/8')
  vi.mocked(fetch).mockImplementation(async (input) => {
    const url = String(input)
    if (url.endsWith('/api/experiments/1')) {
      return {
        ok: true,
        json: async () => ({
          id: 1,
          course: 'MSE202',
          topic: 'Thermodynamics',
          learning_objectives: 'Apply equilibrium relations.',
          assessment_type: 'mixed',
          difficulty: 'medium',
          number_of_questions: 1,
          estimated_time_minutes: 30,
          cognitive_demand: 'evaluate_create',
          additional_instruction: 'Use one laboratory scenario.',
          created_at: '2026-07-14T00:00:00Z',
          conditions: [{
            id: 3,
            condition_code: 'C1',
            prompt_structure: 'openai',
            concept_bridge_enabled: true,
            few_shot_enabled: false,
            reference_content_enabled: true,
            reasoning_guidance_enabled: false,
            factor_inputs: { concept_bridge: 'Hidden factor input' },
            condition_label: 'ConceptBridge=ON; FewShot=OFF; ReferenceContent=ON; ReasoningGuidance=OFF',
          }],
          runs: [{ id: 8, experiment_id: 1, condition_id: 3, run_number: 1, status: 'complete' }],
        }),
      } as Response
    }
    if (url.endsWith('/api/runs/8')) {
      return {
        ok: true,
        json: async () => ({
          id: 8,
          experiment_id: 1,
          condition_id: 3,
          run_number: 1,
          status: 'complete',
          prompt: {
            text: 'Hidden generated prompt',
            hash: 'hash',
            template_version: '10',
            generator_version: '7',
          },
          token_usage: {
            input_tokens: 30,
            output_tokens: 12,
            total_tokens: 42,
            model_calls: 2,
            recording_state: 'recorded',
            stages: [],
          },
          assessment: {
            output_hash: 'hash',
            schema_version: '1',
            parsed_json: { questions: [{
              type: 'mcq',
              body: 'Calculate [[EQ:fraction]].',
              options: [{ body: 'Choose [[EQ:scripts]].', is_correct: true }],
              model_answer: 'Then use [[EQ:root]].',
              equations: [
                { label: 'fraction', expression: 'DeltaH/(T DeltaS)', location: 'question' },
                { label: 'scripts', expression: 'x_a^2', location: 'question' },
                { label: 'root', expression: 'sqrt(x_a)', location: 'solution' },
              ],
            }] },
          },
        }),
      } as Response
    }
    return { ok: true, json: async () => ({}) } as Response
  })

  const { container } = render(<App />)

  expect(await screen.findByText('Concept Bridge = ON')).toBeVisible()
  expect(screen.getByText('Few-shot Examples = OFF')).toBeVisible()
  expect(screen.getByText('Reference Content = ON')).toBeVisible()
  expect(screen.getByText('Reasoning Guidance = OFF')).toBeVisible()
  expect(screen.getByText('Evaluate/Create')).toBeVisible()
  expect(screen.getByText('Use one laboratory scenario.')).toBeVisible()
  expect(screen.getByRole('region', { name: 'Token usage' })).toBeVisible()
  expect(screen.queryByText(/Prompt structure/i)).not.toBeInTheDocument()
  expect(screen.queryByText('Prompt and factor metadata')).not.toBeInTheDocument()
  expect(screen.queryByText('Hidden generated prompt')).not.toBeInTheDocument()
  expect(screen.queryByText('Hidden factor input')).not.toBeInTheDocument()
  expect(container.querySelector('mfrac')).not.toBeNull()
  expect(container.querySelector('msubsup')).not.toBeNull()
  expect(container.querySelector('msqrt')).not.toBeNull()
})

test('asks for confirmation before retrying a run', async () => {
  window.history.replaceState({}, '', '/experiments/1/viewer/8')
  vi.mocked(fetch).mockImplementation(async (input, init) => {
    const url = String(input)
    if (url.endsWith('/api/experiments/1')) {
      return {
        ok: true,
        json: async () => ({
          id: 1,
          course: 'Statics',
          topic: 'Equilibrium',
          learning_objectives: 'Resolve forces',
          assessment_type: 'mixed',
          difficulty: 'medium',
          number_of_questions: 4,
          estimated_time_minutes: 30,
          created_at: '2026-07-14T00:00:00Z',
          conditions: [{
            id: 3,
            condition_code: 'C1',
            prompt_structure: 'openai',
            concept_bridge_enabled: false,
            few_shot_enabled: false,
            reference_content_enabled: false,
            reasoning_guidance_enabled: false,
            factor_inputs: {},
            condition_label: 'Baseline',
          }],
          runs: [{ id: 8, experiment_id: 1, condition_id: 3, run_number: 1, status: 'complete' }],
        }),
      } as Response
    }
    if (url.endsWith('/api/runs/8/retry') && init?.method === 'POST') {
      return {
        ok: true,
        json: async () => ({ id: 9, experiment_id: 1, condition_id: 3, run_number: 2, status: 'pending' }),
      } as Response
    }
    if (url.endsWith('/api/runs/8')) {
      return {
        ok: true,
        json: async () => ({
          id: 8,
          experiment_id: 1,
          condition_id: 3,
          run_number: 1,
          status: 'complete',
          assessment: { parsed_json: { questions: [] }, output_hash: 'hash', schema_version: '1' },
        }),
      } as Response
    }
    return { ok: true, json: async () => ({}) } as Response
  })

  render(<App />)
  const retry = await screen.findByRole('button', { name: 'Retry run' })
  expect(retry).toHaveClass('retry-run-button')
  await userEvent.click(retry)

  const dialog = screen.getByRole('dialog', { name: 'Retry this run?' })
  expect(dialog).toBeVisible()
  expect(vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0)
  await userEvent.click(within(dialog).getByRole('button', { name: 'Confirm retry' }))

  await waitFor(() => expect(
    vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === 'POST'),
  ).toHaveLength(1))
  expect(window.location.pathname).toBe('/runs/9/progress')
})
