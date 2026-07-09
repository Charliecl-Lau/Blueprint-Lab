export type Stage =
  | 'pending'
  | 'prompting'
  | 'planning'
  | 'validating'
  | 'generating'
  | 'complete'
  | 'error'

export type Framework = 'forge' | 'openai' | 'risen'
export type Personality = 'formal' | 'socratic' | 'encouraging' | 'challenging'
export type Length = 'short' | 'medium' | 'long'

export interface ControlSet {
  id?: number
  personality: Personality
  prompt_length: Length
  result_length: Length
  action_word_count: number
}

export interface MCQOption {
  id: number
  body: string
  is_correct: boolean
}

export interface Question {
  id: number
  type: 'mcq' | 'long_answer'
  body: string
  order: number
  options?: MCQOption[]
  model_answer?: string
}

export interface Assessment {
  id: number
  run_id: number
  framework: Framework
  control_set_id: number
  status: Stage
  questions?: Question[]
}

export interface Run {
  id: number
  topic: string
  expectations: string
  mcq_count: number
  long_answer_count: number
  created_at: string
  control_sets: ControlSet[]
  assessments: Assessment[]
}

export interface SSEEvent {
  assessment_id: number
  framework: Framework
  control_set: number
  stage: Stage
}

export interface CreateRunPayload {
  topic: string
  expectations: string
  mcq_count: number
  long_answer_count: number
  frameworks: Framework[]
  control_sets: Omit<ControlSet, 'id'>[]
}
