import { api } from './client'
import type { Run } from '../types'

export const runsApi = {
  get: (id: number): Promise<Run> => api.get(`/runs/${id}`),
  retry: (id: number): Promise<Run> => api.post(`/runs/${id}/retry`, {}),
  exportDocx: async (id: number): Promise<void> => {
    const response = await fetch(`/api/runs/${id}/export-docx`)
    if (!response.ok) throw new Error('DOCX export failed')
    const url = URL.createObjectURL(await response.blob())
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `blueprint-lab-run-${id}.docx`
    anchor.click()
    URL.revokeObjectURL(url)
  },
}
