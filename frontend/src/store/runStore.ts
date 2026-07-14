import { create } from 'zustand'
import type { Experiment, Run, SSEEvent } from '../types'

interface ExperimentStore {
  experiments: Record<number, Experiment>
  runs: Record<number, Run>
  selectedRunId: number | null
  mergeExperiment: (experiment: Experiment) => void
  mergeRun: (run: Run) => void
  applyRunSnapshot: (run: Run) => void
  setExperiment: (experiment: Experiment) => void
  applySSEEvent: (event: SSEEvent) => void
  setRun: (run: Run) => void
  addRetriedRun: (run: Run) => void
  selectRun: (id: number) => void
  reset: () => void
}

export const useRunStore = create<ExperimentStore>((set) => ({
  experiments: {},
  runs: {},
  selectedRunId: null,
  mergeExperiment: (experiment) => set((state) => ({
    experiments: {
      ...state.experiments,
      [experiment.id]: { ...state.experiments[experiment.id], ...experiment },
    },
    runs: experiment.runs.reduce(
      (runs, run) => ({ ...runs, [run.id]: { ...runs[run.id], ...run } }),
      state.runs,
    ),
  })),
  mergeRun: (run) => set((state) => ({
    runs: { ...state.runs, [run.id]: { ...state.runs[run.id], ...run } },
  })),
  applyRunSnapshot: (run) => set((state) => ({
    runs: { ...state.runs, [run.id]: { ...state.runs[run.id], ...run } },
  })),
  setExperiment: (experiment) => set((state) => ({
    experiments: {
      ...state.experiments,
      [experiment.id]: { ...state.experiments[experiment.id], ...experiment },
    },
    runs: experiment.runs.reduce(
      (runs, run) => ({ ...runs, [run.id]: { ...runs[run.id], ...run } }),
      state.runs,
    ),
  })),
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
  setRun: (run) => set((state) => ({
    runs: { ...state.runs, [run.id]: { ...state.runs[run.id], ...run } },
  })),
  addRetriedRun: (run) => set((state) => ({
    runs: { ...state.runs, [run.id]: run },
    selectedRunId: run.id,
  })),
  selectRun: (id) => set({ selectedRunId: id }),
  reset: () => set({ experiments: {}, runs: {}, selectedRunId: null }),
}))
