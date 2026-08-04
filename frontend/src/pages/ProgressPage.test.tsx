import { render, screen } from '@testing-library/react'
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
  useRunStore.getState().reset()
  useRunStore.getState().mergeExperiment({ ...experiment, runs: [failedRun] })
  vi.stubGlobal('EventSource', undefined)
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: string | URL | Request) => ({
    ok: true,
    json: async () => String(input).includes('/experiments/') ? experiment : failedRun,
  })))
})

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
