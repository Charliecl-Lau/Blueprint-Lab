import { create } from 'zustand'
import type { Experiment, Generation, SSEEvent } from '../types'

interface ExperimentStore {
  experiment: Experiment | null
  generations: Record<number, Generation>
  selectedGenerationId: number | null
  setExperiment: (experiment: Experiment) => void
  applySSEEvent: (event: SSEEvent) => void
  setGeneration: (generation: Generation) => void
  selectGeneration: (id: number) => void
  reset: () => void
}

export const useRunStore = create<ExperimentStore>((set) => ({
  experiment: null,
  generations: {},
  selectedGenerationId: null,
  setExperiment: (experiment) => {
    const generations = Object.fromEntries(experiment.generations.map((generation) => [generation.id, generation]))
    set({ experiment, generations, selectedGenerationId: null })
  },
  applySSEEvent: (event) => set((state) => {
    const existing = state.generations[event.generation_id]
    if (!existing) return state
    return {
      generations: { ...state.generations, [existing.id]: { ...existing, status: event.stage } },
      selectedGenerationId: state.selectedGenerationId ?? (event.stage === 'complete' ? existing.id : null),
    }
  }),
  setGeneration: (generation) => set((state) => ({ generations: { ...state.generations, [generation.id]: generation } })),
  selectGeneration: (id) => set({ selectedGenerationId: id }),
  reset: () => set({ experiment: null, generations: {}, selectedGenerationId: null }),
}))
