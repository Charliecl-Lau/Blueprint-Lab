import { api } from './client'
import type { CreateExperimentPayload, Experiment, Run } from '../types'

type ExperimentResponse = Omit<Experiment, 'runs'> & { runs?: Run[] }

export function normalizeExperiment(response: ExperimentResponse): Experiment {
  return { ...response, runs: response.runs ?? response.generations ?? [] }
}

export const experimentsApi = {
  create: async (payload: CreateExperimentPayload): Promise<Experiment> => normalizeExperiment(await api.post('/experiments', payload)),
  get: async (id: number): Promise<Experiment> => normalizeExperiment(await api.get(`/experiments/${id}`)),
}
