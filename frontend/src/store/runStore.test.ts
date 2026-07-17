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
  cognitive_demand: 'remember_understand',
  additional_instruction: null,
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
    useRunStore.getState().applySSEEvent({ generation_id: 8, condition_id: 3, stage: 'saving_results' })
    expect(useRunStore.getState().runs[8]?.status).toBe('saving_results')
  })

  test('keeps the original run and selects the newly retried run', () => {
    useRunStore.getState().setExperiment(experiment)
    useRunStore.getState().addRetriedRun({ id: 9, condition_id: 3, run_number: 2, status: 'preparing_prompt' })

    expect(Object.keys(useRunStore.getState().runs).map(Number)).toEqual([8, 9])
    expect(useRunStore.getState().runs[8]?.status).toBe('complete')
    expect(useRunStore.getState().selectedRunId).toBe(9)
  })

  test('loading a second experiment preserves the first run', () => {
    const second: Experiment = {
      ...experiment,
      id: 2,
      topic: 'Dynamics',
      runs: [{ id: 9, condition_id: 4, run_number: 1, status: 'preparing_prompt' }],
    }

    useRunStore.getState().mergeExperiment(experiment)
    useRunStore.getState().mergeExperiment(second)

    expect(useRunStore.getState().runs[8]).toEqual(experiment.runs[0])
    expect(useRunStore.getState().runs[9]).toEqual(second.runs[0])
    expect(useRunStore.getState().experiments[1]).toMatchObject({ topic: 'Equilibrium' })
    expect(useRunStore.getState().experiments[2]).toMatchObject({ topic: 'Dynamics' })
  })

  test('a run snapshot updates only its matching id', () => {
    const runA = experiment.runs[0]
    const runB = { id: 9, condition_id: 4, run_number: 1, status: 'preparing_prompt' as const }
    useRunStore.getState().mergeRun(runA)
    useRunStore.getState().mergeRun(runB)

    useRunStore.getState().applyRunSnapshot({ ...runA, status: 'generating_assessment' })

    expect(useRunStore.getState().runs[runA.id].status).toBe('generating_assessment')
    expect(useRunStore.getState().runs[runB.id].status).toBe(runB.status)
  })
})
