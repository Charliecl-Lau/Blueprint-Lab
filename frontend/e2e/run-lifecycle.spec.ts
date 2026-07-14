import { expect, test, type Page } from '@playwright/test'

type MockRun = {
  id: number
  experiment_id: number
  condition_id: number
  run_number: number
  topic: string
  total: number
}

function tokenUsage(total: number) {
  return {
    input_tokens: total === 42 ? 30 : 300,
    output_tokens: total === 42 ? 12 : 120,
    total_tokens: total,
    model_calls: 2,
    recording_state: 'recorded',
    stages: [],
  }
}

async function mockResearchApi(page: Page) {
  const runs: MockRun[] = []
  const experiments = new Map<number, Record<string, unknown>>()
  let experimentPosts = 0

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname

    if (request.method() === 'POST' && path === '/api/experiments') {
      experimentPosts += 1
      const payload = request.postDataJSON()
      const id = experimentPosts
      const run: MockRun = {
        id: 100 + id,
        experiment_id: id,
        condition_id: 200 + id,
        run_number: id,
        topic: payload.topic,
        total: id === 1 ? 42 : 420,
      }
      const condition = {
        id: run.condition_id,
        condition_code: `C${id}`,
        prompt_structure: payload.prompt_structure,
        concept_bridge_enabled: false,
        few_shot_enabled: false,
        reference_content_enabled: false,
        reasoning_guidance_enabled: false,
        factor_inputs: {},
        condition_label: 'Baseline',
      }
      const experiment = {
        id,
        ...payload,
        created_at: '2026-07-14T12:00:00Z',
        conditions: [condition],
        runs: [{
          id: run.id,
          experiment_id: id,
          condition_id: run.condition_id,
          run_number: run.run_number,
          status: 'pending',
        }],
      }
      runs.unshift(run)
      experiments.set(id, experiment)
      await route.fulfill({ json: experiment })
      return
    }

    if (request.method() === 'GET' && path === '/api/runs/recent') {
      await route.fulfill({ json: runs.map((run) => ({
        id: run.id,
        experiment_id: run.experiment_id,
        condition_id: run.condition_id,
        run_number: run.run_number,
        status: 'generating',
        topic: run.topic,
        condition_label: 'Baseline',
        created_at: '2026-07-14T12:00:00Z',
        completed_at: null,
        token_usage: tokenUsage(run.total),
      })) })
      return
    }

    const progressMatch = path.match(/^\/api\/runs\/(\d+)\/progress$/)
    if (request.method() === 'GET' && progressMatch) {
      const run = runs.find((item) => item.id === Number(progressMatch[1]))!
      const snapshot = runDetail(run)
      await route.fulfill({
        contentType: 'text/event-stream',
        body: `data: ${JSON.stringify(snapshot)}\n\n`,
      })
      return
    }

    const runMatch = path.match(/^\/api\/runs\/(\d+)$/)
    if (request.method() === 'GET' && runMatch) {
      const run = runs.find((item) => item.id === Number(runMatch[1]))!
      await route.fulfill({ json: runDetail(run) })
      return
    }

    const experimentMatch = path.match(/^\/api\/experiments\/(\d+)$/)
    if (request.method() === 'GET' && experimentMatch) {
      await route.fulfill({ json: experiments.get(Number(experimentMatch[1])) })
      return
    }

    await route.fulfill({ status: 404, json: { detail: 'Not mocked' } })
  })

  return { experimentPostCount: () => experimentPosts }
}

function runDetail(run: MockRun) {
  return {
    id: run.id,
    run_id: run.id,
    experiment_id: run.experiment_id,
    condition_id: run.condition_id,
    run_number: run.run_number,
    status: 'complete',
    artifact_available: true,
    token_usage: tokenUsage(run.total),
    assessment: { parsed_json: { questions: [] }, output_hash: 'hash', schema_version: '1' },
  }
}

async function fillRequiredFields(page: Page, topic: string) {
  await page.getByLabel('Course name').fill('ENGR 101')
  await page.getByLabel('Topic').fill(topic)
  await page.getByLabel('Learning objectives').fill('Solve equilibrium problems.')
}

test('two runs remain independently reopenable with isolated status and tokens', async ({ page }) => {
  await mockResearchApi(page)
  await page.goto('/')

  await fillRequiredFields(page, 'Statics')
  await page.getByRole('button', { name: 'Run Experiment' }).click()
  await expect(page).toHaveURL(/\/runs\/101\/progress$/)
  await expect(page.getByText('Complete', { exact: true })).toBeVisible()

  await page.getByRole('link', { name: 'Back to Control Assessment' }).click()
  await fillRequiredFields(page, 'Dynamics')
  await page.getByRole('button', { name: 'Run Experiment' }).click()
  await expect(page).toHaveURL(/\/runs\/102\/progress$/)

  await page.getByRole('link', { name: 'Back to Control Assessment' }).click()
  const recent = page.getByRole('region', { name: 'Recent runs' })
  await expect(recent.getByText('Statics')).toBeVisible()
  await expect(recent.getByText('Dynamics')).toBeVisible()

  await recent.getByRole('link', { name: 'Reopen run 1: Statics' }).click()
  await expect(page).toHaveURL(/\/runs\/101\/progress$/)
  await expect(page.getByText('Complete', { exact: true })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Token usage' }).getByText('42', { exact: true })).toBeVisible()
})

test('invalid form shows every missing field and sends no experiment request', async ({ page }) => {
  const api = await mockResearchApi(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'Run Experiment' }).click()

  const dialog = page.getByRole('dialog', {
    name: 'Complete the required fields before running the experiment.',
  })
  await expect(dialog).toHaveClass(/validation-dialog/)
  await expect(dialog.getByRole('heading', { name: 'Assessment Details' })).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Course name' })).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Topic' })).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Learning objectives' })).toBeVisible()
  expect(api.experimentPostCount()).toBe(0)
})
