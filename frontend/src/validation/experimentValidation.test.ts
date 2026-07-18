import { expect, test } from 'vitest'
import {
  MAX_REFERENCE_PDF_BYTES,
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
  referencePdfs: [],
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

test('requires PDFs when reference content is enabled', () => {
  const errors = validateExperimentForm({
    ...validForm,
    enabled: { ...validForm.enabled, referenceContent: true },
    referencePdfs: [],
  })
  expect(errors).toContainEqual(expect.objectContaining({
    section: 'Prompt Design Factors',
    field: 'factor-referenceContent-pdfs',
  }))
})


test('validates reference PDF count, type, extension, and per-file size', () => {
  const pdf = (size: number, name = 'reference.pdf', type = 'application/pdf') =>
    new File([new Uint8Array(size)], name, { type })
  const enabled = { ...validForm.enabled, referenceContent: true }

  expect(validateExperimentForm({
    ...validForm,
    enabled,
    referencePdfs: [pdf(1), pdf(1), pdf(1), pdf(1)],
  })).toContainEqual(expect.objectContaining({ message: expect.stringContaining('3') }))
  expect(validateExperimentForm({
    ...validForm,
    enabled,
    referencePdfs: [pdf(MAX_REFERENCE_PDF_BYTES + 1)],
  })).toContainEqual(expect.objectContaining({ message: expect.stringContaining('20 MB') }))
  expect(validateExperimentForm({
    ...validForm,
    enabled,
    referencePdfs: [pdf(1, 'reference.txt')],
  })).toContainEqual(expect.objectContaining({ message: expect.stringContaining('.pdf') }))
  expect(validateExperimentForm({
    ...validForm,
    enabled,
    referencePdfs: [pdf(1, 'reference.pdf', 'text/plain')],
  })).toContainEqual(expect.objectContaining({ message: expect.stringContaining('PDF') }))
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
