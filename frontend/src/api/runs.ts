import { api } from './client'
import type { RecentRun, Run, RunHistoryDetail, TerminalRunSummary } from '../types'

export const runsApi = {
  get: (id: number): Promise<Run> => api.get(`/runs/${id}`),
  recent: (limit = 10): Promise<RecentRun[]> => api.get(`/runs/recent?limit=${limit}`),
  historyRecent: (limit = 10): Promise<TerminalRunSummary[]> => (
    api.get(`/runs/history/recent?limit=${limit}`)
  ),
  historyDetail: (id: number): Promise<RunHistoryDetail> => (
    api.get(`/runs/${id}/history`)
  ),
  retry: (id: number, referencePdfs?: File[]): Promise<Run> => {
    if (!referencePdfs) return api.post(`/runs/${id}/retry`, {})
    const form = new FormData()
    referencePdfs.forEach((pdf) => form.append('reference_pdfs', pdf))
    return api.post(`/runs/${id}/retry`, form)
  },
  recoverAssessment: (id: number): Promise<Run> => api.post(`/runs/${id}/recover-assessment`, {}),
  acceptAssessmentDefects: (id: number): Promise<Run> => api.post(`/runs/${id}/accept-assessment-defects`, {}),
  exportDocx: async (id: number): Promise<void> => {
    const response = await fetch(`/api/runs/${id}/export-docx`)
    if (!response.ok) throw new Error('DOCX export failed')
    const disposition = response.headers.get('Content-Disposition') ?? ''
    const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
    const quoted = disposition.match(/filename="([^"]+)"/i)?.[1]
    const filename = encoded
      ? decodeURIComponent(encoded)
      : quoted ?? `blueprint-lab-run-${id}.docx`
    const url = URL.createObjectURL(await response.blob())
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.click()
    URL.revokeObjectURL(url)
  },
}
