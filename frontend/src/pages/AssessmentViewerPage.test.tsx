import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { useRunStore } from '../store/runStore'
import type { Experiment, Run } from '../types'
import { AssessmentViewerPage } from './AssessmentViewerPage'

const experiment: Experiment = {
  id: 1, course: 'MSE', topic: 'Diffusion', learning_objectives: ['Solve'],
  assessment_type: 'mcq', difficulty: 'medium', number_of_questions: 1,
  estimated_time_minutes: 20, cognitive_demand: 'apply_analyze',
  additional_instruction: null, created_at: '2026-08-03T00:00:00Z',
  conditions: [{ id: 2, condition_code: 'C1', prompt_structure: 'openai',
    concept_bridge_enabled: false, few_shot_enabled: false,
    reference_content_enabled: false, reasoning_guidance_enabled: false,
    factor_inputs: {}, condition_label: 'Baseline' }], runs: [],
}

function renderViewer(run: Run) {
  useRunStore.getState().mergeExperiment({ ...experiment, runs: [run] })
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: string | URL | Request) => ({
    ok: true,
    json: async () => String(input).includes('/experiments/') ? experiment : run,
  })))
  return render(
    <MemoryRouter initialEntries={['/experiments/1/viewer/7']}>
      <Routes><Route path="/experiments/:experimentId/viewer/:runId" element={<AssessmentViewerPage />} /></Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  useRunStore.getState().reset()
  vi.stubGlobal('EventSource', undefined)
})

test('renders canonical version provenance and typed computational solution', () => {
  renderViewer({
    id: 7, experiment_id: 1, condition_id: 2, run_number: 1, status: 'complete',
    evaluation_status: 'complete', grading_available: true, grading_question_id: 99,
    artifact_available: true,
    rewrite: { status: 'succeeded', attempt_count: 1, repair_available: false,
      original_assessment_id: 10, original_version: 1, canonical_assessment_id: 11,
      canonical_version: 2, source_version: 1, displaying: 'canonical_rewrite',
      artifact_available: true, failure: null },
    assessment: { id: 11, question_ids: [99], output_hash: 'hash',
      schema_version: 'rewritten-assessment/1', parsed_json: { questions: [{
        id: 99, body: 'Compute the flux', options: [
          { id: 'A', body: 'A', is_correct: true }, { id: 'B', body: 'B', is_correct: false },
          { id: 'C', body: 'C', is_correct: false }, { id: 'D', body: 'D', is_correct: false },
          { id: 'E', body: 'E', is_correct: false },
        ], solution: { kind: 'computational', knowns_and_target: ['D and gradient'],
          governing_equation: 'J = -D dc/dx', substitution: 'Insert values',
          calculation_steps: ['Multiply'], final_answer: 'J = 2', units: 'mol/m2/s',
          physical_meaning: 'Flux follows the gradient', distractor_analysis: [
            { option_id: 'B', explanation: 'wrong sign' }, { option_id: 'C', explanation: 'wrong units' },
            { option_id: 'D', explanation: 'wrong value' }, { option_id: 'E', explanation: 'wrong law' },
          ] },
      }] } },
  })

  expect(screen.getByRole('heading', { name: 'Canonical LLM rewrite' })).toBeVisible()
  expect(screen.getByText(/Version 2, rewritten from source version 1/)).toBeVisible()
  for (const label of ['Knowns and target', 'Governing equation', 'Substitution', 'Final answer', 'Physical meaning', 'Distractor analysis']) {
    expect(screen.getByText(label)).toBeVisible()
  }
  expect(screen.getByRole('button', { name: 'Export Word document' })).toBeEnabled()
})

test('renders original recovery without export or grading actions', () => {
  renderViewer({
    id: 7, experiment_id: 1, condition_id: 2, run_number: 1, status: 'rewrite_failed',
    evaluation_status: 'not_started', grading_available: false, artifact_available: false,
    rewrite: { status: 'failed', attempt_count: 2, repair_available: true,
      original_assessment_id: 10, original_version: 1, canonical_assessment_id: 10,
      canonical_version: 1, source_version: 1, displaying: 'original_recovery',
      artifact_available: false, failure: { issue_codes: ['policy_rejected'] } },
    assessment: { id: 10, question_ids: [], output_hash: 'hash', schema_version: '1',
      parsed_json: { questions: [{ body: 'Original question' }] } },
  })

  expect(screen.getByRole('heading', { name: 'Original assessment — DOCX rewrite failed' })).toBeVisible()
  expect(screen.getByText('Failure codes: policy_rejected')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Word export unavailable' })).toBeDisabled()
  expect(screen.queryByRole('button', { name: 'Retry LLM Evaluation' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Retry Word rewrite' })).toBeEnabled()
  expect(screen.getByText('Original question')).toBeVisible()
})
