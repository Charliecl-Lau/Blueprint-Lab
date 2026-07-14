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
    help: 'Provide notes, excerpts, facts, or source material.',
    missingLabel: 'Reference Content: add reference content',
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
  promptStructure: string
  enabled: Record<FactorKey, boolean>
  content: Record<FactorKey, string>
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

  for (const factor of PROMPT_FACTORS) {
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

  return errors
}
