import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import App from './App'

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

  await waitFor(() => expect(fetch).toHaveBeenCalled())
  const [, init] = vi.mocked(fetch).mock.calls[0]
  expect(JSON.parse(String(init?.body))).toMatchObject({
    estimated_time_minutes: 30,
    factors: { concept_bridge: true, reasoning_guidance: false },
    factor_inputs: { concept_bridge: 'Connect vectors to force balance.' },
  })
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
