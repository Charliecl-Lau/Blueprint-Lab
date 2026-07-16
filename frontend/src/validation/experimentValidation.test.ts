import { expect, test } from 'vitest'
import {
  validateExperimentForm,
  type ExperimentFormValues,
} from './experimentValidation'

const validForm: ExperimentFormValues = {
  course: 'Statics',
  topic: 'Equilibrium',
  learningObjectives: 'Resolve forces in two dimensions.',
  assessmentType: 'mixed',
  difficulty: 'medium',
  questionCount: '5',
  estimatedTime: '30',
  cognitiveDemand: 'remember_understand',
  additionalInstruction: '',
  promptStructure: 'openai',
  enabled: {
    conceptBridge: false,
    fewShot: false,
    referenceContent: false,
    reasoningGuidance: false,
  },
  content: {
    conceptBridge: '',
    fewShot: '',
    referenceContent: '',
    reasoningGuidance: '',
  },
}

const emptyForm: ExperimentFormValues = {
  ...validForm,
  course: '',
  topic: '   ',
  learningObjectives: '',
}

test('returns every missing field grouped by user-facing section', () => {
  const errors = validateExperimentForm(emptyForm)
  expect(errors.map(({ section, label }) => ({ section, label }))).toEqual([
    { section: 'Assessment Details', label: 'Course name' },
    { section: 'Assessment Details', label: 'Topic' },
    { section: 'Assessment Details', label: 'Learning objectives' },
  ])
})

test('requires only enabled factor content', () => {
  const errors = validateExperimentForm({
    ...validForm,
    enabled: { ...validForm.enabled, referenceContent: true },
    content: { ...validForm.content, referenceContent: '   ' },
  })
  expect(errors).toContainEqual(expect.objectContaining({
    section: 'Prompt Design Factors',
    label: 'Reference Content: add reference content',
  }))
})

test('matches backend integer bounds and visual field order', () => {
  const errors = validateExperimentForm({
    ...validForm,
    questionCount: '2.5',
    estimatedTime: '481',
  })
  expect(errors.map(({ field, message }) => ({ field, message }))).toEqual([
    { field: 'number-of-questions', message: 'Enter 1 to 50 questions.' },
    { field: 'estimated-time', message: 'Enter 1 to 480 minutes.' },
  ])
})

test('requires a supported cognitive demand', () => {
  expect(validateExperimentForm({ ...validForm, cognitiveDemand: '' }))
    .toContainEqual(expect.objectContaining({
      field: 'cognitive-demand',
      message: 'Select a cognitive demand.',
    }))
})
