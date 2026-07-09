import { api } from './client'
import type { CreateRunPayload, Run } from '../types'

export const runsApi = {
  create: (payload: CreateRunPayload): Promise<{ id: number }> =>
    api.post('/runs', payload),

  get: (id: number): Promise<Run> =>
    api.get(`/runs/${id}`),
}
