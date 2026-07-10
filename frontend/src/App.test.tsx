import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import App from './App'

beforeEach(() => {
  vi.restoreAllMocks()
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
  fireEvent.click(screen.getByRole('checkbox', { name: /Concept Bridge/ }))
  fireEvent.change(screen.getByLabelText('Concept Bridge content'), { target: { value: 'Connect vectors to force balance.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Run Experiment' }))

  await waitFor(() => expect(fetch).toHaveBeenCalled())
  const [, init] = vi.mocked(fetch).mock.calls[0]
  expect(JSON.parse(String(init?.body))).toMatchObject({
    estimated_time_minutes: 30,
    factors: { concept_bridge: true, reasoning_guidance: false },
    factor_inputs: { concept_bridge: 'Connect vectors to force balance.' },
  })
})
