import { expect, test, type Page, type Request } from '@playwright/test'

type MockRun = {
  id: number
  experiment_id: number
  condition_id: number
  run_number: number
  topic: string
  total: number
  referencePdfFilenames: string[]
}

function multipartExperimentRequest(request: Request) {
  const raw = request.postData() ?? ''
  const payloadMatch = raw.match(/name="payload"\r?\n\r?\n([\s\S]*?)\r?\n--/)
  if (!payloadMatch) throw new Error('Multipart experiment payload was not found')
  const referencePdfFilenames = Array.from(
    raw.matchAll(/name="reference_pdfs"; filename="([^"]+)"/g),
    (match) => match[1],
  )
  return {
    payload: JSON.parse(payloadMatch[1]) as Record<string, unknown>,
    referencePdfFilenames,
  }
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
  let latestReferencePdfFilenames: string[] = []

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    if (!path.startsWith('/api/')) {
      await route.continue()
      return
    }

    if (request.method() === 'GET' && path === '/api/runs/history/recent') {
      await route.fulfill({ json: [
        {
          id: 101,
          experiment_id: 1,
          condition_id: 201,
          run_number: 1,
          status: 'complete',
          display_status: 'completed',
          topic: 'Statics',
          display_at: '2026-08-02T14:30:00Z',
        },
        {
          id: 102,
          experiment_id: 2,
          condition_id: 202,
          run_number: 2,
          status: 'error',
          display_status: 'failed',
          topic: 'Dynamics failure',
          display_at: '2026-08-02T14:20:00Z',
        },
      ] })
      return
    }

    if (request.method() === 'GET' && path === '/api/runs/101/history') {
      await route.fulfill({ json: historyDetail({
        id: 101,
        topic: 'Statics',
        actualPrompt: 'Exact persisted actual prompt',
        question: historyQuestion(),
        artifact: { available: true, filename: 'statics.docx' },
      }) })
      return
    }

    if (request.method() === 'GET' && path === '/api/runs/102/history') {
      await route.fulfill({ json: historyDetail({
        id: 102,
        topic: 'Dynamics failure',
        actualPrompt: null,
        question: null,
        artifact: null,
      }) })
      return
    }

    if (request.method() === 'GET' && path === '/api/assessment-questions/11/history-context') {
      await route.fulfill({ json: historyEvaluationContext() })
      return
    }

    if (request.method() === 'GET' && path === '/api/runs/101/export-docx') {
      await route.fulfill({
        body: 'stored docx bytes',
        contentType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        headers: { 'Content-Disposition': 'attachment; filename="statics.docx"' },
      })
      return
    }

    if (request.method() === 'POST' && path === '/api/experiments') {
      experimentPosts += 1
      const { payload, referencePdfFilenames } = multipartExperimentRequest(request)
      latestReferencePdfFilenames = referencePdfFilenames
      const id = experimentPosts
      const run: MockRun = {
        id: 100 + id,
        experiment_id: id,
        condition_id: 200 + id,
        run_number: id,
        topic: String(payload.topic),
        total: id === 1 ? 42 : 420,
        referencePdfFilenames,
      }
      const condition = {
        id: run.condition_id,
        condition_code: `C${id}`,
        prompt_structure: payload.prompt_structure,
        concept_bridge_enabled: false,
        few_shot_enabled: false,
        reference_content_enabled: referencePdfFilenames.length > 0,
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
          reference_pdf_filenames: referencePdfFilenames,
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

  return {
    experimentPostCount: () => experimentPosts,
    latestReferencePdfFilenames: () => latestReferencePdfFilenames,
  }
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
    reference_pdf_filenames: run.referencePdfFilenames,
  }
}

function historyQuestion() {
  return {
    id: 11,
    type: 'short_answer',
    metadata: {
      question_title: 'Static equilibrium',
      question_type: 'short_answer',
      difficulty_level: 'medium',
      mse202_concepts: ['Equilibrium'],
      mse302_concepts: [],
      concept_map_bridge: null,
      materials_science_context: 'A supported beam.',
      estimated_time_minutes: 10,
    },
    body: 'Determine the support reactions.',
    model_answer: 'Apply force and moment equilibrium.',
  }
}

function assessmentDetails(topic: string) {
  return {
    course: 'ENGR 101',
    topic,
    learning_objectives: ['Solve equilibrium problems.'],
    assessment_type: 'short_answer',
    difficulty: 'medium',
    number_of_questions: 1,
    estimated_time_minutes: 20,
    cognitive_demand: 'apply_analyze',
    additional_instruction: null,
    prompt_structure: 'openai',
    factor_configuration: {
      concept_bridge: false,
      few_shot: false,
      reference_content: false,
      reasoning_guidance: false,
    },
    factor_inputs: {},
    reference_pdf_filenames: [],
  }
}

function historyDetail({
  id,
  topic,
  actualPrompt,
  question,
  artifact,
}: {
  id: number
  topic: string
  actualPrompt: string | null
  question: ReturnType<typeof historyQuestion> | null
  artifact: { available: true; filename: string } | null
}) {
  const completed = id === 101
  return {
    id,
    experiment_id: id - 100,
    condition_id: id + 100,
    run_number: id - 100,
    status: completed ? 'complete' : 'error',
    display_status: completed ? 'completed' : 'failed',
    assessment_details: assessmentDetails(topic),
    actual_prompt: actualPrompt,
    questions: question ? [question] : null,
    question_ids: question ? [question.id] : null,
    artifact,
    evaluation_available: completed,
  }
}

const historyCriterionKeys = [
  'technical_correctness',
  'course_alignment',
  'blooms_alignment',
  'clarity_solution',
  'materials_context',
] as const

function historyRubric() {
  return {
    version: '2026-07-16',
    criteria: historyCriterionKeys.map((key) => ({
      key,
      title: key.replaceAll('_', ' '),
      weight: 20,
      covers: 'Quality',
      description: 'Criterion description.',
      comment_prompt: 'Explain the score.',
      anchors: { '1': 'Poor', '3': 'Acceptable', '5': 'Excellent' },
    })),
  }
}

function llmHistoryEvaluation() {
  const rubric = historyRubric()
  return {
    id: 22,
    assessment_id: 5,
    question_id: 11,
    evaluation_type: 'llm',
    evaluator_identity: 'gemini-evaluator',
    evaluation_model: 'gemini-evaluator',
    evaluation_model_version: 'evaluation-v1',
    rubric_version: rubric.version,
    rubric_snapshot: rubric,
    weighted_score: 100,
    critical_gate: 'PASS',
    overall_decision: 'Instructor-ready',
    instructor_readiness: 'Instructor-ready',
    highest_priority_issue: null,
    highest_priority_revision: null,
    overall_comments: null,
    major_strengths: ['Technically sound.'],
    major_weaknesses: [],
    recommended_action: 'Accept without revision',
    status: 'finalized',
    revision: 1,
    evaluation_timestamp: '2026-08-02T14:00:00Z',
    created_at: '2026-08-02T14:00:00Z',
    updated_at: '2026-08-02T14:00:00Z',
    finalized_at: '2026-08-02T14:01:00Z',
    criteria: historyCriterionKeys.map((criterion_key) => ({
      criterion_key,
      score: 5,
      comment: null,
      suggested_modification: null,
      issue_flags: [],
      justification: 'Saved LLM evidence.',
      strengths: ['Correct.'],
      weaknesses: [],
      suggested_improvements: [],
      suggested_modifications: [],
    })),
  }
}

function historyEvaluationContext() {
  return {
    run_id: 101,
    assessment_id: 5,
    question_id: 11,
    question: historyQuestion(),
    rubric: historyRubric(),
    llm_evaluation: llmHistoryEvaluation(),
    human_evaluation: null,
    comparison: null,
    previous_question_id: null,
    next_question_id: null,
    history_path: '/runs/101/history',
  }
}

async function fillRequiredFields(page: Page, topic: string) {
  await page.getByLabel('Course name').fill('ENGR 101')
  await page.getByLabel('Topic').fill(topic)
  await page.getByLabel('Learning objectives').fill('Solve equilibrium problems.')
}

test('two runs remain independently reopenable with isolated status', async ({ page }) => {
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
  await page.evaluate(() => {
    window.history.pushState({}, '', '/runs/101/progress')
    window.dispatchEvent(new PopStateEvent('popstate'))
  })
  await expect(page).toHaveURL(/\/runs\/101\/progress$/)
  await expect(page.getByText('Complete', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Statics' })).toBeVisible()
  await page.getByRole('link', { name: 'View Assessment' }).click()
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

test('submits ordered reference PDFs through multipart experiment creation', async ({ page }) => {
  const api = await mockResearchApi(page)
  await page.goto('/')
  await fillRequiredFields(page, 'Statics with references')
  await page.getByRole('button', { name: 'Prompt Design Factors', exact: true }).click()
  await page.getByText('Reference Content', { exact: true }).click()
  await page.getByLabel('Reference Content PDFs').setInputFiles([
    {
      name: 'one.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('%PDF-1.7\none'),
    },
    {
      name: 'two.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('%PDF-1.7\ntwo'),
    },
  ])
  await page.getByRole('button', { name: 'Review', exact: true }).click()
  await expect(page.getByText('one.pdf, two.pdf')).toBeVisible()
  await page.getByRole('button', { name: 'Run Experiment' }).click()

  await expect(page).toHaveURL(/\/runs\/101\/progress$/)
  expect(api.latestReferencePdfFilenames()).toEqual(['one.pdf', 'two.pdf'])
})

test('completed history exposes saved evidence, DOCX, and fixed grades', async ({ page }) => {
  await mockResearchApi(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'Recent Runs' }).click()
  await page.getByRole('link', { name: /Statics/ }).click()
  await expect(page).toHaveURL(/\/runs\/101\/history$/)

  await expect(page.getByRole('button', { name: 'Assessment Details' })).toHaveAttribute('aria-expanded', 'false')
  await expect(page.getByRole('button', { name: 'Questions and Solutions' })).toHaveAttribute('aria-expanded', 'true')

  await page.getByRole('button', { name: 'Actual Prompt' }).click()
  await expect(page.getByText('Exact persisted actual prompt')).toBeVisible()

  const downloadEvent = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download Word DOCX' }).click()
  expect((await downloadEvent).suggestedFilename()).toBe('statics.docx')

  await page.getByRole('link', { name: 'Next' }).click()
  await expect(page).toHaveURL(/\/runs\/101\/history\/questions\/11\/evaluation$/)
  await expect(page.getByText('Human evaluation not completed').first()).toBeVisible()
  await expect(page.getByRole('button', { name: /Save Draft|Finalize|Reopen/ })).toHaveCount(0)
})

test('failed history exposes only details and prompt state', async ({ page }) => {
  await mockResearchApi(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'Recent Runs' }).click()
  await page.getByRole('link', { name: /Dynamics failure/ }).click()

  await expect(page.getByRole('button', { name: 'Assessment Details' })).toHaveAttribute('aria-expanded', 'true')
  await expect(page.getByText('No actual prompt')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Questions and Solutions' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Download Word DOCX' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Next' })).toHaveCount(0)
})

type RewriteScenario = 'success' | 'repair_success' | 'failed' | 'validating' | 'agentic_success' | 'agentic_revision' | 'agentic_fatal' | 'agentic_exhausted'

async function mockRewriteLifecycle(page: Page, scenario: RewriteScenario) {
  const agentic = scenario.startsWith('agentic_')
  const failed = scenario === 'failed' || scenario === 'agentic_fatal' || scenario === 'agentic_exhausted'
  const status = failed ? 'rewrite_failed' : scenario === 'validating' ? 'docx_validating' : 'complete'
  const canonical = scenario === 'success' || scenario === 'repair_success' || scenario === 'agentic_success' || scenario === 'agentic_revision'
  const repair = scenario === 'repair_success' || scenario === 'agentic_revision'
  const run = {
    id: 501, run_id: 501, experiment_id: 51, condition_id: 61, run_number: 1,
    status,
    viewer_available: status !== 'docx_validating',
    progress_message: scenario === 'validating' ? 'Verifying Word document' : status === 'rewrite_failed' ? 'Word rewrite failed; original remains available' : 'Complete',
    evaluation_status: canonical ? 'complete' : 'not_started',
    grading_available: canonical,
    grading_question_id: canonical ? 801 : null,
    artifact_available: canonical,
    rewrite: {
      backend: agentic ? 'agentic_tools' : 'self_hosted_code',
      status: canonical ? 'succeeded' : status === 'rewrite_failed' ? 'failed' : 'in_progress',
      attempt_count: repair ? 2 : 1,
      repair_available: status === 'rewrite_failed' && !agentic,
      original_assessment_id: 701,
      original_version: 1,
      canonical_assessment_id: canonical ? 702 : 701,
      canonical_version: canonical ? 2 : 1,
      source_version: 1,
      displaying: canonical ? 'canonical_rewrite' : status === 'rewrite_failed' ? 'original_recovery' : 'original',
      artifact_available: canonical,
      iteration: agentic ? (repair ? 1 : 0) : null,
      maximum_revisions: agentic ? 2 : null,
      workspace_revision: agentic ? (repair ? 9 : 7) : null,
      failure: status === 'rewrite_failed' ? { issue_codes: [scenario === 'agentic_exhausted' ? 'revision_budget_exhausted' : scenario === 'agentic_fatal' ? 'machine_failed' : 'render_failed'] } : null,
    },
    token_usage: {
      input_tokens: repair ? 75 : 50,
      output_tokens: repair ? 35 : 20,
      total_tokens: repair ? 110 : 70,
      model_calls: repair ? 3 : 2,
      recording_state: status === 'docx_validating' ? 'in_progress' : 'recorded',
      stages: [
        { stage: 'assessment', input_tokens: 20, output_tokens: 10, total_tokens: 30, model_calls: 1 },
        { stage: agentic ? 'docx_tool_design' : 'docx_code_generation', input_tokens: 30, output_tokens: 10, total_tokens: 40, model_calls: 1 },
        ...(repair ? [{ stage: agentic ? 'docx_visual_review' : 'docx_code_repair', input_tokens: 25, output_tokens: 15, total_tokens: 40, model_calls: 1 }] : []),
      ],
    },
    assessment: {
      id: canonical ? 702 : 701,
      question_ids: canonical ? [801] : [],
      output_hash: 'hash',
      schema_version: canonical ? 'rewritten-assessment/1' : '1',
      parsed_json: { questions: [{
        id: canonical ? 801 : undefined,
        body: canonical ? 'Calculate diffusion flux.' : 'Original diffusion question.',
        options: canonical ? [
          { id: 'A', body: '1', is_correct: true }, { id: 'B', body: '2', is_correct: false },
          { id: 'C', body: '3', is_correct: false }, { id: 'D', body: '4', is_correct: false },
          { id: 'E', body: '5', is_correct: false },
        ] : undefined,
        solution: canonical ? {
          kind: 'computational', knowns_and_target: ['D and dc/dx'], governing_equation: 'J = -D dc/dx',
          substitution: 'Insert known values', calculation_steps: ['Multiply'], final_answer: 'J = 1', units: 'mol/m2/s',
          physical_meaning: 'Flux follows the gradient', distractor_analysis: [
            { option_id: 'B', explanation: 'sign' }, { option_id: 'C', explanation: 'units' },
            { option_id: 'D', explanation: 'value' }, { option_id: 'E', explanation: 'law' },
          ],
        } : undefined,
      }] },
    },
  }
  const experiment = {
    id: 51, course: 'MSE', topic: 'Diffusion', learning_objectives: ['Solve'],
    assessment_type: 'mcq', difficulty: 'medium', number_of_questions: 1,
    estimated_time_minutes: 20, cognitive_demand: 'apply_analyze', additional_instruction: null,
    conditions: [{ id: 61, condition_code: 'C1', prompt_structure: 'openai', condition_label: 'Baseline',
      concept_bridge_enabled: false, few_shot_enabled: false, reference_content_enabled: false,
      reasoning_guidance_enabled: false, factor_inputs: {} }],
    runs: [run],
  }
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) {
      await route.continue()
      return
    }
    if (path === '/api/runs/501/progress') {
      await route.fulfill({ contentType: 'text/event-stream', body: `data: ${JSON.stringify(run)}\n\n` })
    } else if (path === '/api/runs/501') {
      await route.fulfill({ json: run })
    } else if (path === '/api/experiments/51') {
      await route.fulfill({ json: experiment })
    } else if (path === '/api/runs/501/export-docx' && canonical) {
      await route.fulfill({ contentType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', body: 'PK-verified' })
    } else {
      await route.fulfill({ status: 404, json: { detail: 'Not available' } })
    }
  })
}

test('authoring success exposes the canonical rewrite and verified download', async ({ page }) => {
  await mockRewriteLifecycle(page, 'success')
  await page.goto('/runs/501/progress')
  await expect(page.getByText('Complete', { exact: true })).toBeVisible()
  await page.getByRole('link', { name: 'View Assessment' }).click()
  await expect(page.getByRole('heading', { name: 'Canonical LLM rewrite' })).toBeVisible()
  await expect(page.getByText(/Version 2, rewritten from source version 1/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Export Word document' })).toBeEnabled()
  await expect(page.getByRole('link', { name: 'Grade Assessment' })).toHaveAttribute('href', '/assessments/702/questions/801/grade')
})

test('repair success exposes repair-stage tokens', async ({ page }) => {
  await mockRewriteLifecycle(page, 'repair_success')
  await page.goto('/experiments/51/viewer/501')
  await page.getByText('Usage by stage').click()
  await expect(page.getByText('docx code generation')).toBeVisible()
  await expect(page.getByText('docx code repair')).toBeVisible()
  await expect(page.getByText('110', { exact: true })).toBeVisible()
})

test('terminal rewrite failure preserves the original and locks rewrite actions', async ({ page }) => {
  await mockRewriteLifecycle(page, 'failed')
  await page.goto('/runs/501/progress')
  await expect(page.getByText('Word rewrite failed', { exact: true })).toBeVisible()
  await page.getByRole('link', { name: 'View original assessment' }).click()
  await expect(page.getByRole('heading', { name: 'Original assessment — DOCX rewrite failed' })).toBeVisible()
  await expect(page.getByText('Original diffusion question.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Word export unavailable' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Retry Word rewrite' })).toBeEnabled()
  await expect(page.getByRole('link', { name: 'Grade Assessment' })).toHaveCount(0)
})

test('no artifact or grading access exists before canonicalization', async ({ page }) => {
  await mockRewriteLifecycle(page, 'validating')
  await page.goto('/experiments/51/viewer/501')
  await expect(page.getByRole('button', { name: 'Word export unavailable' })).toBeDisabled()
  await expect(page.getByRole('link', { name: 'Grade Assessment' })).toHaveCount(0)
})

test('agentic design approval exposes the canonical LLM-designed document', async ({ page }) => {
  await mockRewriteLifecycle(page, 'agentic_success')
  await page.goto('/experiments/51/viewer/501')
  await expect(page.getByRole('heading', { name: 'Canonical LLM-designed document' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Export Word document' })).toBeEnabled()
})

test('agentic visual revision reports separate design and review usage', async ({ page }) => {
  await mockRewriteLifecycle(page, 'agentic_revision')
  await page.goto('/experiments/51/viewer/501')
  await page.getByText('Usage by stage').click()
  await expect(page.getByText('docx tool design')).toBeVisible()
  await expect(page.getByText('docx visual review')).toBeVisible()
})

test('machine-fatal agentic output preserves original recovery and hides internals', async ({ page }) => {
  await mockRewriteLifecycle(page, 'agentic_fatal')
  await page.goto('/experiments/51/viewer/501')
  await expect(page.getByRole('heading', { name: 'Original recovery document' })).toBeVisible()
  await expect(page.getByText(/machine_failed/)).toBeVisible()
  const response = await page.evaluate(async () => (await fetch('/api/runs/501')).json())
  expect(JSON.stringify(response)).not.toContain('temporary_handle')
  expect(JSON.stringify(response)).not.toContain('validated_arguments')
})

test('agentic revision-budget exhaustion preserves the original', async ({ page }) => {
  await mockRewriteLifecycle(page, 'agentic_exhausted')
  await page.goto('/experiments/51/viewer/501')
  await expect(page.getByText(/revision_budget_exhausted/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Word export unavailable' })).toBeDisabled()
})
