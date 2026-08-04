import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { TokenUsage } from './TokenUsage'

test('shows distinct DOCX authoring and repair token stages', () => {
  render(<TokenUsage usage={{
    input_tokens: 50,
    output_tokens: 25,
    total_tokens: 75,
    model_calls: 2,
    recording_state: 'recorded',
    stages: [
      { stage: 'docx_code_generation', input_tokens: 30, output_tokens: 15, total_tokens: 45, model_calls: 1 },
      { stage: 'docx_code_repair', input_tokens: 20, output_tokens: 10, total_tokens: 30, model_calls: 1 },
    ],
  }} />)

  screen.getByText('Usage by stage').click()
  expect(screen.getByText('docx code generation')).toBeVisible()
  expect(screen.getByText('docx code repair')).toBeVisible()
  expect(screen.getByText('75')).toBeVisible()
})
