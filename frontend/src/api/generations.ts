import { runsApi } from './runs'

/** @deprecated Use runsApi. */
export const generationsApi = {
  get: runsApi.get,
  regenerate: async (id: number) => {
    const run = await runsApi.retry(id)
    return { ...run, run_id: run.id, generation_id: run.id }
  },
  exportDocx: runsApi.exportDocx,
}
