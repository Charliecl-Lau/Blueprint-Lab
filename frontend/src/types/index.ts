export type Stage =
  | 'preparing_prompt'
  | 'generating_assessment'
  | 'validating_assessment'
  | 'evaluating_quality'
  | 'saving_results'
  | 'complete'
  | 'generation_failed'
  | 'evaluation_failed'
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
  id: number
  question_ids: number[]
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
  viewer_ready_at?: string | null
  progress_message?: string | null
  evaluation_status?: 'not_started' | 'in_progress' | 'complete' | 'failed'
  grading_available?: boolean
  grading_question_id?: number | null
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
  metadata?: {
    prompt_template_id?: string
    actual_prompt_id?: string
    output_id?: string
    final_question_id?: string
    question_title: string
    question_type: 'mcq' | 'long_answer' | 'short_answer'
    difficulty_level: string
    intended_assessment_setting: string
    mse202_concepts: string[]
    mse302_concepts: string[]
    concept_map_bridge: string
    materials_science_context: string
    estimated_time?: string
    learning_objectives?: string[]
    id_requirements?: string
  }
  body: string
  body_segments?: ContentSegment[]
  order?: number
  options?: MCQOption[]
  model_answer?: string | null
  model_answer_segments?: ContentSegment[]
  equations?: EquationEntry[]
  revision_options?: string[]
}

export type CriterionKey =
  | 'technical_correctness'
  | 'course_alignment'
  | 'blooms_alignment'
  | 'clarity_solution'
  | 'materials_context'

export type EvaluationStatus = 'draft' | 'finalized' | 'failed' | 'reopened'

export type RecommendedAction =
  | 'Accept without revision'
  | 'Accept with minor revision'
  | 'Revise before use'
  | 'Major revision required'
  | 'Reject assessment'

export interface EvaluationCriterion {
  criterion_key: CriterionKey
  score: number | null
  comment?: string | null
  suggested_modification?: string | null
  issue_flags: string[]
  justification?: string | null
  strengths: string[]
  weaknesses: string[]
  suggested_improvements: string[]
  suggested_modifications: string[]
}

export interface Evaluation {
  id: number
  assessment_id: number
  question_id: number
  evaluation_type: 'llm' | 'human'
  evaluator_identity: string
  evaluation_model: string | null
  evaluation_model_version: string | null
  rubric_version: string
  rubric_snapshot: RubricSnapshot
  weighted_score: number | null
  critical_gate: string | null
  overall_decision: string | null
  instructor_readiness: string | null
  highest_priority_issue: string | null
  highest_priority_revision: string | null
  overall_comments: string | null
  major_strengths: string[]
  major_weaknesses: string[]
  recommended_action: string | null
  status: EvaluationStatus
  revision: number
  evaluation_timestamp: string | null
  created_at: string
  updated_at: string
  finalized_at: string | null
  criteria: EvaluationCriterion[]
}

export interface RubricCriterion {
  key: CriterionKey
  title: string
  weight: number
  covers: string
  description: string
  comment_prompt: string
  anchors: Record<'1' | '3' | '5', string>
}

export interface RubricSnapshot {
  version: string
  criteria: RubricCriterion[]
}

export interface HumanCriterionPatch {
  criterion_key: CriterionKey
  score?: number | null
  comment?: string | null
  suggested_modification?: string | null
  issue_flags?: string[]
}

export interface HumanEvaluationPatch {
  revision: number
  criteria?: HumanCriterionPatch[]
  highest_priority_issue?: string | null
  overall_comments?: string | null
  recommended_action?: RecommendedAction | null
}

export interface AssessmentQuestionSummary {
  id: number
  assessment_id: number
  ordinal: number
  assessment_version: number
  content_hash: string
  question: Question
}

export interface GradingContext {
  experiment_id: number
  run_id: number
  assessment_id: number
  question_id: number
  question: Question
  rubric: RubricSnapshot
  llm_evaluation: Evaluation
  human_evaluation: Evaluation
  previous_question_id: number | null
  next_question_id: number | null
  viewer_path: string
}

export type ComparisonIndicator =
  | 'agreement'
  | 'minor_difference'
  | 'significant_difference'

export interface CriterionComparison {
  criterion_key: CriterionKey
  human_score: number
  llm_score: number
  difference: number
  absolute_difference: number
  indicator: ComparisonIndicator
}

export interface EvaluationComparison {
  criteria: CriterionComparison[]
  mean_absolute_score_difference: number
  exact_agreement_rate: number
  agreement_within_one_point: number
  largest_disagreement: CriterionComparison
  human_weighted_score: number
  llm_weighted_score: number
  weighted_score_difference: number
  human_overall_decision: string
  llm_overall_decision: string
  decision_difference: boolean
}

export interface EvaluationAccessDetail {
  first_opened_at: string
  opened_before_finalization: boolean
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
