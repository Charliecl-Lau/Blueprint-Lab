export type Stage = 'pending' | 'prompting' | 'generating' | 'documenting' | 'complete' | 'error'
export type PromptStructure = 'openai' | 'anthropic'
export type AssessmentType = 'mcq' | 'short_answer' | 'mixed'
export type CognitiveDemand = 'remember_understand' | 'apply_analyze' | 'evaluate_create'
export type RecordingState = 'not_recorded' | 'in_progress' | 'recorded'

export interface StageUsage {
  stage: string
  input_tokens: number | null
  output_tokens: number | null
  total_tokens: number | null
  model_calls: number
  cached_content_tokens?: number
  reasoning_tokens?: number
  extra_token_counts?: Record<string, number>
}

export interface TokenUsage {
  input_tokens: number | null
  output_tokens: number | null
  total_tokens: number | null
  model_calls: number | null
  recording_state: RecordingState
  stages: StageUsage[]
}

export type MathNode =
  | { type: 'text'; text: string }
  | { type: 'symbol'; name: string }
  | { type: 'number'; value: string }
  | { type: 'operator'; value: string }
  | { type: 'sequence'; items: MathNode[] }
  | { type: 'equation'; left: MathNode; right: MathNode }
  | { type: 'fraction'; numerator: MathNode; denominator: MathNode }
  | { type: 'differential'; variable: string }
  | { type: 'product'; terms: MathNode[]; operator?: 'implicit' | 'dot' | 'cross' }
  | { type: 'subscript'; base: MathNode; subscript: MathNode }
  | { type: 'superscript'; base: MathNode; superscript: MathNode }
  | { type: 'radical'; radicand: MathNode; degree?: MathNode | null }
  | { type: 'matrix'; rows: MathNode[][] }

export interface ContentSegment {
  type: 'text' | 'math'
  text?: string
  math?: MathNode
}

export interface EquationEntry {
  label: string
  expression?: string
  math?: MathNode
  location: 'question' | 'solution'
}

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
  condition_code?: string
  prompt_structure: PromptStructure
  concept_bridge_enabled: boolean
  few_shot_enabled: boolean
  reference_content_enabled: boolean
  reasoning_guidance_enabled: boolean
  factor_inputs: PromptFactorInputs
  condition_label: string
}

export interface PromptProvenance {
  text: string
  hash: string
  template_version: string
  generator_version: string
}

export interface AssessmentOutput {
  parsed_json: { questions: Question[] } | null
  output_hash: string
  schema_version: string
  raw_response_text?: string
}

export interface RunSource {
  source_document_id: number
  role: string
  ordinal: number
  included_text_hash: string
  name: string
  version: string
}

export interface Run {
  id: number
  run_id?: number
  experiment_id?: number
  condition_id: number
  run_number: number
  status: Stage
  model_settings?: Record<string, unknown>
  model_name?: string | null
  model_version?: string | null
  generation_time_ms?: number | null
  generated_json?: { questions: Question[] } | null
  condition?: Condition
  prompt_text?: string | null
  prompt?: PromptProvenance | null
  assessment?: AssessmentOutput | null
  sources?: RunSource[]
  artifact_available?: boolean
  token_usage?: TokenUsage
  error?: { type?: string | null; message?: string | null } | null
}

/** @deprecated Use Run. */
export type Generation = Run

export interface Experiment {
  id: number
  course: string
  topic: string
  learning_objectives: string
  assessment_type: AssessmentType
  difficulty: string
  number_of_questions: number
  estimated_time_minutes: number
  cognitive_demand: CognitiveDemand
  additional_instruction: string | null
  created_at: string
  conditions: Condition[]
  runs: Run[]
  generations?: Generation[]
}

export interface RecentRun {
  id: number
  experiment_id: number
  condition_id: number
  run_number: number
  status: Stage
  topic: string
  condition_label: string
  created_at: string
  completed_at: string | null
  token_usage: TokenUsage
}

export interface MCQOption {
  id?: number
  body: string
  is_correct: boolean
  segments?: ContentSegment[]
}
export interface Question {
  id?: number
  type: 'mcq' | 'long_answer' | 'short_answer'
  body: string
  body_segments?: ContentSegment[]
  order?: number
  options?: MCQOption[]
  model_answer?: string | null
  model_answer_segments?: ContentSegment[]
  equations?: EquationEntry[]
}

export interface SSEEvent { run_id?: number; generation_id?: number; condition_id: number; stage: Stage }

export type RunSnapshot = Run & { type?: 'run_detail' }

export interface ValidationError {
  section: string
  field: string
  label: string
  message: string
}

export interface ValidationErrorResponse {
  detail: { errors: ValidationError[] }
}

export interface CreateExperimentPayload {
  course: string
  topic: string
  learning_objectives: string
  assessment_type: AssessmentType
  difficulty: string
  number_of_questions: number
  estimated_time_minutes: number
  cognitive_demand: CognitiveDemand
  additional_instruction: string | null
  prompt_structure: PromptStructure
  factors: PromptFactors
  factor_inputs: PromptFactorInputs
}
