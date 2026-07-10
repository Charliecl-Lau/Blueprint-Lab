import { api } from './client'
import type { CreateExperimentPayload, Experiment } from '../types'

export const experimentsApi = {
  create: (payload: CreateExperimentPayload): Promise<Experiment> => api.post('/experiments', payload),
  get: (id: number): Promise<Experiment> => api.get(`/experiments/${id}`),
}
