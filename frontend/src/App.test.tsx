import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import { axe, toHaveNoViolations } from 'jest-axe'
import App from './App'
import { normalizeExperiment } from './api/experiments'

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
    created_at: '2026-07-11T00:00:00Z',
    conditions: [],
    generations: [legacyRun],
  })

  expect(response.runs).toEqual([legacyRun])
})

beforeEach(() => {
  vi.restoreAllMocks()
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
  expect(screen.queryByText('Subject area')).not.toBeInTheDocument()
  expect(screen.queryByText("Bloom's taxonomy")).not.toBeInTheDocument()
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
  expect(screen.getByRole('dialog', { name: 'Your experiment isn’t ready yet' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /Assessment Details: Course name/ }))
  expect(screen.getByRole('heading', { name: 'Assessment Details' })).toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
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
