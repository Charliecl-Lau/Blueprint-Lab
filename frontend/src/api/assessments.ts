import { api } from './client'
import type { Assessment } from '../types'

export const assessmentsApi = {
  get: (id: number): Promise<Assessment> =>
    api.get(`/assessments/${id}`),

  regenerate: (id: number): Promise<{ ok: boolean }> =>
    api.post(`/assessments/${id}/regenerate`, {}),

  exportPdf: async (id: number, variant: 'student' | 'answer_key'): Promise<void> => {
    const res = await fetch(`/api/assessments/${id}/export-pdf`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ variant }),
    })
    if (!res.ok) throw new Error('PDF export failed')
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `assessment-${id}-${variant}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  },
}
