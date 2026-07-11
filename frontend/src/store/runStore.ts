import { create } from 'zustand'
import type { Experiment, Run, SSEEvent } from '../types'

interface ExperimentStore {
  experiment: Experiment | null
  runs: Record<number, Run>
  selectedRunId: number | null
  setExperiment: (experiment: Experiment) => void
  applySSEEvent: (event: SSEEvent) => void
  setRun: (run: Run) => void
  addRetriedRun: (run: Run) => void
  selectRun: (id: number) => void
  reset: () => void
}

export const useRunStore = create<ExperimentStore>((set) => ({
  experiment: null,
  runs: {},
  selectedRunId: null,
  setExperiment: (experiment) => {
    const runs = Object.fromEntries(experiment.runs.map((run) => [run.id, run]))
    set({ experiment, runs, selectedRunId: null })
  },
  applySSEEvent: (event) => set((state) => {
    const runId = event.run_id ?? event.generation_id
    if (runId === undefined) return state
    const existing = state.runs[runId]
    if (!existing) return state
    return {
      runs: { ...state.runs, [existing.id]: { ...existing, status: event.stage } },
      selectedRunId: state.selectedRunId ?? (event.stage === 'complete' ? existing.id : null),
    }
  }),
  setRun: (run) => set((state) => ({ runs: { ...state.runs, [run.id]: run } })),
  addRetriedRun: (run) => set((state) => ({
    runs: { ...state.runs, [run.id]: run },
    selectedRunId: run.id,
  })),
  selectRun: (id) => set({ selectedRunId: id }),
  reset: () => set({ experiment: null, runs: {}, selectedRunId: null }),
}))
