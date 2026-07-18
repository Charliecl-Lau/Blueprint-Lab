export const PROMPT_FACTORS = [
  {
    key: 'conceptBridge',
    label: 'Concept Bridge',
    help: 'Connect the topic to concepts students already know.',
    missingLabel: 'Concept Bridge: add bridge content',
  },
  {
    key: 'fewShot',
    label: 'Few-shot Examples',
    help: 'Provide representative question-and-answer examples.',
    missingLabel: 'Few-shot Examples: add example content',
  },
  {
    key: 'referenceContent',
    label: 'Reference Content',
    help: 'Attach PDF reference material for assessment generation.',
    missingLabel: 'Reference Content: upload PDF files',
  },
  {
    key: 'reasoningGuidance',
    label: 'Reasoning Guidance (chain-of-thought condition)',
    help: 'Request concise rationale or structured solution steps, not hidden model reasoning.',
    missingLabel: 'Reasoning Guidance: add guidance content',
  },
] as const

export type FactorKey = typeof PROMPT_FACTORS[number]['key']
export type ValidationSection = 'Assessment Details' | 'Prompt Design Factors'

export interface ExperimentFormValues {
  course: string
  topic: string
  learningObjectives: string
  assessmentType: string
  difficulty: string
  questionCount: string
  estimatedTime: string
  cognitiveDemand: string
  additionalInstruction: string
  promptStructure: string
  enabled: Record<FactorKey, boolean>
  content: Record<FactorKey, string>
  referencePdfs: File[]
}

export interface ValidationError {
  section: ValidationSection
  field: string
  label: string
  message: string
}

const requiredTextFields = [
  ['course', 'course', 'Course name'],
  ['topic', 'topic', 'Topic'],
  ['learningObjectives', 'learning-objectives', 'Learning objectives'],
] as const

export function factorContentId(key: FactorKey) {
  return `factor-${key}-content`
}

export const REFERENCE_PDF_INPUT_ID = 'factor-referenceContent-pdfs'
export const MAX_REFERENCE_PDF_BYTES = 20 * 1024 * 1024
export const MAX_REFERENCE_PDFS = 3

export function referencePdfValidationMessages(files: File[]): string[] {
  const messages: string[] = []
  if (files.length === 0) {
    messages.push('Upload at least one PDF for Reference Content.')
  } else if (files.length > MAX_REFERENCE_PDFS) {
    messages.push('Upload no more than 3 PDFs.')
  }
  for (const pdf of files) {
    if (!pdf.name.toLowerCase().endsWith('.pdf')) {
      messages.push(`${pdf.name} must use the .pdf extension.`)
    } else if (pdf.type !== 'application/pdf') {
      messages.push(`${pdf.name} must be a PDF file.`)
    } else if (pdf.size > MAX_REFERENCE_PDF_BYTES) {
      messages.push(`${pdf.name} exceeds the 20 MB per-file limit.`)
    }
  }
  return messages
}

export function validateExperimentForm(values: ExperimentFormValues): ValidationError[] {
  const errors: ValidationError[] = []

  for (const [property, field, label] of requiredTextFields) {
    if (!values[property].trim()) {
      errors.push({
        section: 'Assessment Details',
        field,
        label,
        message: `${label} is required.`,
      })
    }
  }

  const questionCount = Number(values.questionCount)
  if (!Number.isInteger(questionCount) || questionCount < 1 || questionCount > 50) {
    errors.push({
      section: 'Assessment Details',
      field: 'number-of-questions',
      label: 'Number of questions',
      message: 'Enter 1 to 50 questions.',
    })
  }

  const estimatedTime = Number(values.estimatedTime)
  if (!Number.isInteger(estimatedTime) || estimatedTime < 1 || estimatedTime > 480) {
    errors.push({
      section: 'Assessment Details',
      field: 'estimated-time',
      label: 'Estimated student completion time',
      message: 'Enter 1 to 480 minutes.',
    })
  }

  if (!['remember_understand', 'apply_analyze', 'evaluate_create'].includes(values.cognitiveDemand)) {
    errors.push({
      section: 'Assessment Details',
      field: 'cognitive-demand',
      label: 'Cognitive demand',
      message: 'Select a cognitive demand.',
    })
  }

  for (const factor of PROMPT_FACTORS) {
    if (factor.key === 'referenceContent') continue
    if (values.enabled[factor.key] && !values.content[factor.key].trim()) {
      const displayLabel = factor.label.replace(' (chain-of-thought condition)', '')
      errors.push({
        section: 'Prompt Design Factors',
        field: factorContentId(factor.key),
        label: factor.missingLabel,
        message: `Add content for ${displayLabel}.`,
      })
    }
  }

  if (values.enabled.referenceContent) {
    for (const message of referencePdfValidationMessages(values.referencePdfs)) {
      errors.push({
        section: 'Prompt Design Factors',
        field: REFERENCE_PDF_INPUT_ID,
        label: 'Reference Content: upload PDF files',
        message,
      })
    }
  }

  return errors
}
