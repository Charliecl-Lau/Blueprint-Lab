import { act, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { useRunStore } from '../store/runStore'
import type { Experiment, Run } from '../types'
import { ProgressPage } from './ProgressPage'

const experiment: Experiment = {
  id: 1,
  course: 'MSE',
  topic: 'Phases',
  learning_objectives: ['Analyze'],
  assessment_type: 'mcq',
  difficulty: 'medium',
  number_of_questions: 1,
  estimated_time_minutes: 20,
  cognitive_demand: 'apply_analyze',
  additional_instruction: null,
  created_at: '2026-08-03T00:00:00Z',
  conditions: [{
    id: 2,
    condition_code: 'C1',
    prompt_structure: 'openai',
    concept_bridge_enabled: false,
    few_shot_enabled: false,
    reference_content_enabled: false,
    reasoning_guidance_enabled: false,
    factor_inputs: {},
    condition_label: 'Baseline',
  }],
  runs: [],
}

const failedRun: Run = {
  id: 7,
  experiment_id: 1,
  condition_id: 2,
  run_number: 1,
  status: 'rewrite_failed',
  progress_message: 'Assessment rewrite failed; original remains available',
  rewrite: {
    status: 'failed', attempt_count: 2, repair_available: true,
    original_assessment_id: 11, original_version: 1,
    canonical_assessment_id: 11, canonical_version: 1, source_version: 1,
    displaying: 'original_recovery', artifact_available: false,
    failure: { issue_codes: ['render_failed'] },
  },
}

beforeEach(() => {
  vi.useRealTimers()
  useRunStore.getState().reset()
  useRunStore.getState().mergeExperiment({ ...experiment, runs: [failedRun] })
  vi.stubGlobal('EventSource', undefined)
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: string | URL | Request) => ({
    ok: true,
    json: async () => String(input).includes('/experiments/') ? experiment : failedRun,
  })))
})

function renderProgress(run: Run) {
  useRunStore.getState().mergeExperiment({ ...experiment, runs: [run] })
  vi.mocked(fetch).mockImplementation(async (input: string | URL | Request) => ({
    ok: true,
    json: async () => String(input).includes('/experiments/') ? experiment : run,
  }) as Response)
  return render(
    <MemoryRouter initialEntries={[`/runs/${run.id}/progress`]}>
      <Routes><Route path="/runs/:runId/progress" element={<ProgressPage />} /></Routes>
    </MemoryRouter>,
  )
}

test('shows terminal rewrite failure recovery and the persisted detail', () => {
  render(
    <MemoryRouter initialEntries={['/runs/7/progress']}>
      <Routes><Route path="/runs/:runId/progress" element={<ProgressPage />} /></Routes>
    </MemoryRouter>,
  )

  expect(screen.getByText('Word rewrite failed')).toBeVisible()
  expect(screen.getByText('Assessment rewrite failed; original remains available')).toBeVisible()
  expect(screen.getByRole('link', { name: 'View original assessment' })).toHaveAttribute(
    'href', '/experiments/1/viewer/7',
  )
  expect(screen.getByRole('button', { name: 'Retry Word rewrite' })).toBeEnabled()
})

test('shows server-based elapsed time and rotates contextual activity wording', () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-08-06T12:00:30Z'))
  const run: Run = {
    id: 8, experiment_id: 1, condition_id: 2, run_number: 1,
    status: 'generating', started_at: '2026-08-06T12:00:00Z',
  }

  renderProgress(run)

  expect(screen.getByText('Generating questions')).toBeVisible()
  expect(screen.getByText('Structuring the assessment…')).toHaveAttribute('aria-live', 'polite')
  expect(screen.getByText('Working · 30s elapsed')).not.toHaveAttribute('aria-live')

  act(() => { vi.advanceTimersByTime(10000) })

  expect(screen.getByText('Preparing questions and solutions…')).toBeVisible()
  expect(screen.getByText('Working · 40s elapsed')).toBeVisible()
  expect(screen.queryByText(/%/)).not.toBeInTheDocument()
  expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
})

test('resets activity wording when the persisted stage changes', () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-08-06T12:00:30Z'))
  const run: Run = {
    id: 8, experiment_id: 1, condition_id: 2, run_number: 1,
    status: 'generating', started_at: '2026-08-06T12:00:00Z',
  }
  renderProgress(run)
  act(() => { vi.advanceTimersByTime(10000) })
  expect(screen.getByText('Preparing questions and solutions…')).toBeVisible()

  act(() => {
    useRunStore.getState().mergeRun({ ...run, status: 'docx_validating' })
  })

  expect(screen.getByText('Checking document structure…')).toBeVisible()
})

test('reassures users during long runs and falls back safely without a start time', () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-08-06T12:02:01Z'))
  const run: Run = {
    id: 8, experiment_id: 1, condition_id: 2, run_number: 1,
    status: 'docx_authoring', started_at: '2026-08-06T12:00:00Z',
  }
  const view = renderProgress(run)
  expect(screen.getByText('Working · 2m 1s elapsed')).toBeVisible()
  expect(screen.getByText('Still working. Complex assessments may take several minutes.')).toBeVisible()

  view.unmount()
  renderProgress({ ...run, id: 9, started_at: null })

  expect(screen.getByText('Working')).toBeVisible()
})

test('does not show active progress details for terminal runs', () => {
  renderProgress({
    id: 8, experiment_id: 1, condition_id: 2, run_number: 1,
    status: 'complete', started_at: '2026-08-06T12:00:00Z',
  })

  expect(screen.queryByText(/^Working/)).not.toBeInTheDocument()
  expect(screen.queryByText('Structuring the assessment…')).not.toBeInTheDocument()
})
