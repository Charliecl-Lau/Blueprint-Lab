import { beforeEach, describe, expect, test } from 'vitest'
import type { Experiment } from '../types'
import { useRunStore } from './runStore'

const experiment: Experiment = {
  id: 1,
  course: 'Statics',
  topic: 'Equilibrium',
  learning_objectives: 'Resolve forces',
  assessment_type: 'mixed',
  difficulty: 'medium',
  number_of_questions: 4,
  estimated_time_minutes: 30,
  created_at: '2026-07-10T00:00:00Z',
  conditions: [],
  runs: [{ id: 8, condition_id: 3, run_number: 1, status: 'complete' }],
}

describe('run store', () => {
  beforeEach(() => useRunStore.getState().reset())

  test('indexes runs when an experiment is loaded', () => {
    useRunStore.getState().setExperiment(experiment)
    expect(useRunStore.getState().runs[8]?.condition_id).toBe(3)
  })

  test('normalizes deprecated generation ids in progress events', () => {
    useRunStore.getState().setExperiment(experiment)
    useRunStore.getState().applySSEEvent({ generation_id: 8, condition_id: 3, stage: 'documenting' })
    expect(useRunStore.getState().runs[8]?.status).toBe('documenting')
  })

  test('keeps the original run and selects the newly retried run', () => {
    useRunStore.getState().setExperiment(experiment)
    useRunStore.getState().addRetriedRun({ id: 9, condition_id: 3, run_number: 2, status: 'pending' })

    expect(Object.keys(useRunStore.getState().runs).map(Number)).toEqual([8, 9])
    expect(useRunStore.getState().runs[8]?.status).toBe('complete')
    expect(useRunStore.getState().selectedRunId).toBe(9)
  })
})
