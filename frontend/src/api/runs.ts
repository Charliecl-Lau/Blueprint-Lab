import { api } from './client'
import type { RecentRun, Run } from '../types'

export const runsApi = {
  get: (id: number): Promise<Run> => api.get(`/runs/${id}`),
  recent: (limit = 10): Promise<RecentRun[]> => api.get(`/runs/recent?limit=${limit}`),
  retry: (id: number, referencePdfs?: File[]): Promise<Run> => {
    if (!referencePdfs) return api.post(`/runs/${id}/retry`, {})
    const form = new FormData()
    referencePdfs.forEach((pdf) => form.append('reference_pdfs', pdf))
    return api.post(`/runs/${id}/retry`, form)
  },
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
