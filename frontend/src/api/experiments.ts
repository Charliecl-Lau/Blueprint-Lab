import { api } from './client'
import type { CreateExperimentPayload, Experiment, Run } from '../types'

type ExperimentResponse = Omit<Experiment, 'runs'> & { runs?: Run[] }

export function normalizeExperiment(response: ExperimentResponse): Experiment {
  return { ...response, runs: response.runs ?? response.generations ?? [] }
}

export const experimentsApi = {
  create: async (payload: CreateExperimentPayload, referencePdfs: File[], idempotencyKey: string): Promise<Experiment> => {
    const form = new FormData()
    form.append('payload', JSON.stringify(payload))
    referencePdfs.forEach((pdf) => form.append('reference_pdfs', pdf))
    return normalizeExperiment(await api.post('/experiments', form, { 'Idempotency-Key': idempotencyKey }))
  },
  get: async (id: number): Promise<Experiment> => normalizeExperiment(await api.get(`/experiments/${id}`)),
}
