import { create } from 'zustand'
import type { Run, Assessment, SSEEvent } from '../types'

interface RunStore {
  run: Run | null
  assessments: Record<number, Assessment>
  selectedAssessmentId: number | null

  setRun: (run: Run) => void
  applySSEEvent: (event: SSEEvent) => void
  setAssessment: (assessment: Assessment) => void
  selectAssessment: (id: number) => void
  reset: () => void
}

export const useRunStore = create<RunStore>((set) => ({
  run: null,
  assessments: {},
  selectedAssessmentId: null,

  setRun: (run) => {
    const assessments: Record<number, Assessment> = {}
    run.assessments.forEach(a => { assessments[a.id] = a })
    set({ run, assessments, selectedAssessmentId: null })
  },

  applySSEEvent: (event) => set((state) => {
    const existing = Object.values(state.assessments).find(
      a => a.framework === event.framework && a.control_set_id === event.control_set
    )
    if (!existing) return state
    const updated = { ...existing, status: event.stage }
    const assessments = { ...state.assessments, [existing.id]: updated }
    const selectedAssessmentId =
      state.selectedAssessmentId === null && event.stage === 'complete'
        ? existing.id
        : state.selectedAssessmentId
    return { assessments, selectedAssessmentId }
  }),

  setAssessment: (assessment) => set((state) => ({
    assessments: { ...state.assessments, [assessment.id]: assessment },
  })),

  selectAssessment: (id) => set({ selectedAssessmentId: id }),

  reset: () => set({ run: null, assessments: {}, selectedAssessmentId: null }),
}))
