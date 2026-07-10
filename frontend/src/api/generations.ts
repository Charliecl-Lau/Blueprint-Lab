import { api } from './client'
import type { Generation } from '../types'

export const generationsApi = {
  get: (id: number): Promise<Generation> => api.get(`/generations/${id}`),
  regenerate: (id: number): Promise<{ generation_id: number; status: string }> => api.post(`/generations/${id}/regenerate`, {}),
  exportDocx: async (id: number): Promise<void> => {
    const response = await fetch(`/api/generations/${id}/export-docx`)
    if (!response.ok) throw new Error('DOCX export failed')
    const url = URL.createObjectURL(await response.blob())
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `blueprint-lab-generation-${id}.docx`
    anchor.click()
    URL.revokeObjectURL(url)
  },
}
