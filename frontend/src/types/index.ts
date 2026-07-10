export type Stage = 'pending' | 'prompting' | 'generating' | 'documenting' | 'complete' | 'error'
export type PromptStructure = 'openai' | 'anthropic'
export type AssessmentType = 'mcq' | 'short_answer' | 'mixed'

export interface PromptFactors {
  concept_bridge: boolean
  few_shot: boolean
  reference_content: boolean
  reasoning_guidance: boolean
}

export interface PromptFactorInputs {
  concept_bridge?: string
  few_shot?: string
  reference_content?: string
  reasoning_guidance?: string
}

export interface Condition {
  id: number
  prompt_structure: PromptStructure
  concept_bridge_enabled: boolean
  few_shot_enabled: boolean
  reference_content_enabled: boolean
  reasoning_guidance_enabled: boolean
  factor_inputs: PromptFactorInputs
  condition_label: string
}

export interface Generation {
  id: number
  condition_id: number
  status: Stage
  model_name?: string | null
  model_version?: string | null
  generation_time_ms?: number | null
  generated_json?: { questions: Question[] } | null
  condition?: Condition
  prompt_text?: string | null
}

export interface Experiment {
  id: number
  course: string
  topic: string
  learning_objectives: string
  assessment_type: AssessmentType
  difficulty: string
  number_of_questions: number
  estimated_time_minutes: number
  created_at: string
  conditions: Condition[]
  generations: Generation[]
}

export interface MCQOption { id?: number; body: string; is_correct: boolean }
export interface Question {
  id?: number
  type: 'mcq' | 'long_answer' | 'short_answer'
  body: string
  order?: number
  options?: MCQOption[]
  model_answer?: string | null
}

export interface SSEEvent { generation_id: number; condition_id: number; stage: Stage }

export interface CreateExperimentPayload {
  course: string
  topic: string
  learning_objectives: string
  assessment_type: AssessmentType
  difficulty: string
  number_of_questions: number
  estimated_time_minutes: number
  prompt_structure: PromptStructure
  factors: PromptFactors
  factor_inputs: PromptFactorInputs
}
