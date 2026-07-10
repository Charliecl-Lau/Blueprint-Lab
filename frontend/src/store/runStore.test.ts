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
  generations: [{ id: 8, condition_id: 3, status: 'pending' }],
}

describe('experiment store', () => {
  beforeEach(() => useRunStore.getState().reset())

  test('indexes generations when an experiment is loaded', () => {
    useRunStore.getState().setExperiment(experiment)
    expect(useRunStore.getState().generations[8]?.condition_id).toBe(3)
  })

  test('applies progress events by generation id', () => {
    useRunStore.getState().setExperiment(experiment)
    useRunStore.getState().applySSEEvent({ generation_id: 8, condition_id: 3, stage: 'complete' })
    expect(useRunStore.getState().generations[8]?.status).toBe('complete')
    expect(useRunStore.getState().selectedGenerationId).toBe(8)
  })
})
