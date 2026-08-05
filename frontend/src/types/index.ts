export type Stage =
  | 'pending'
  | 'prompting'
  | 'generating'
  | 'docx_authoring'
  | 'docx_executing'
  | 'docx_validating'
  | 'docx_repairing'
  | 'rewrite_failed'
  | 'documenting'
  | 'complete'
  | 'complete_with_warnings'
  | 'error'
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
  parsed_json: {
    traceability?: AssessmentTraceability
    assessment_metadata?: AssessmentMetadata
    questions: Question[]
  } | null
  output_hash: string
  schema_version: string
  raw_response_text?: string
  validation?: AssessmentValidation
}

export interface AssessmentMetadata {
  prompt_template_id?: string | null
  actual_prompt_id?: string | number | null
  output_id?: string | number | null
  final_question_id?: string | number | Array<string | number> | null
  question_title: string
  course: string
  topic: string
  question_type: string
  number_of_questions: number
  difficulty_level: string
  cognitive_demand: string
  intended_assessment_setting: string
  mse202_concepts: string[]
  mse302_concepts: string[]
  concept_map_bridge: string | null
  materials_science_context: string
  numerical_computation: string
  estimated_time: string
  learning_objectives: string[]
  prompt_design_factors: string[]
  additional_instructions?: string | null
}

export interface RewriteState {
  backend?: 'legacy' | 'self_hosted_code' | 'agentic_tools'
  status: 'not_started' | 'in_progress' | 'succeeded' | 'failed'
  attempt_count: number
  repair_available: boolean
  original_assessment_id: number | null
  original_version: number | null
  canonical_assessment_id: number | null
  canonical_version: number | null
  source_version: number | null
  displaying: 'original' | 'original_recovery' | 'canonical_rewrite'
  artifact_available: boolean
  iteration?: number | null
  maximum_revisions?: number | null
  workspace_revision?: number | null
  failure: { issue_codes: string[] } | null
}

export interface AssessmentTraceability {
  experiment_id: number
  condition_id: number
  run_id: number
  prompt_id: number | null
  prompt_template_version: string
  assessment_id: number
  assessment_version: number
  assessment_schema_version: string
}

export interface AssessmentValidationIssue {
  code: string
  question_ordinal: number | null
  field_path: string
  excerpt: string | null
  message: string
  recoverable: boolean
}

export interface AssessmentValidation {
  status: 'valid' | 'warning' | 'invalid'
  issues: AssessmentValidationIssue[]
  recovery_actions: Array<Record<string, unknown>>
  parsed_json_hash: string | null
  defects_accepted_at: string | null
  defects_accepted_by: string | null
  acceptance_required: boolean
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
  viewer_available?: boolean
  evaluation_status?: 'not_started' | 'in_progress' | 'complete' | 'failed'
  grading_available?: boolean
  grading_question_id?: number | null
  model_settings?: Record<string, unknown>
  model_name?: string | null
  model_version?: string | null
  generation_time_ms?: number | null
  condition?: Condition
  prompt_text?: string | null
  prompt?: PromptProvenance | null
  assessment?: AssessmentOutput | null
  sources?: RunSource[]
  artifact_available?: boolean
  rewrite?: RewriteState
  token_usage?: TokenUsage
  error?: { type?: string | null; message?: string | null } | null
  reference_pdf_filenames?: string[]
}

/** @deprecated Use Run. */
export type Generation = Run

export interface Experiment {
  id: number
  course: string
  topic: string
  learning_objectives: string[]
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
  reference_pdf_filenames?: string[]
}

export interface TerminalRunSummary {
  id: number
  experiment_id: number
  condition_id: number
  run_number: number
  status: 'complete' | 'complete_with_warnings' | 'error'
  display_status: 'completed' | 'failed'
  topic: string
  display_at: string
}

export interface HistoryAssessmentDetails {
  course: string
  topic: string
  learning_objectives: string[]
  assessment_type: AssessmentType
  difficulty: string
  number_of_questions: number
  estimated_time_minutes: number
  cognitive_demand: CognitiveDemand
  additional_instruction: string | null
  prompt_structure: PromptStructure
  factor_configuration: Record<string, boolean>
  factor_inputs: PromptFactorInputs
  reference_pdf_filenames: string[]
}

export interface RunHistoryDetail {
  id: number
  experiment_id: number
  condition_id: number
  run_number: number
  status: 'complete' | 'complete_with_warnings' | 'error'
  display_status: 'completed' | 'failed'
  assessment_details: HistoryAssessmentDetails
  actual_prompt: string | null
  questions: Question[] | null
  question_ids: number[] | null
  artifact: { available: true; filename: string } | null
  evaluation_available: boolean
}

export interface MCQOption {
  id?: number | string
  body: string
  is_correct: boolean
  segments?: ContentSegment[]
}
export interface Question {
  id?: number
  type?: 'mcq' | 'long_answer' | 'short_answer'
  metadata?: {
    question_title: string
    question_type: 'mcq' | 'long_answer' | 'short_answer'
    difficulty_level: string
    mse202_concepts: string[]
    mse302_concepts: string[]
    concept_map_bridge: string | null
    materials_science_context: string
    estimated_time_minutes: number
    learning_objectives?: string[]
  }
  traceability?: {
    assessment_question_id: number
    ordinal: number
    assessment_version: number
  }
  body: string
  body_segments?: ContentSegment[]
  order?: number
  options?: MCQOption[]
  model_answer?: string | null
  model_answer_segments?: ContentSegment[]
  equations?: EquationEntry[]
  revision_options?: string[]
  title?: string
  source_question_id?: string
  source_ordinal?: number
  solution?: ComputationalSolution | ConceptualSolution
}

export interface DistractorAnalysis {
  option_id: string
  explanation: string
}

export interface ComputationalSolution {
  kind: 'computational'
  knowns_and_target: string[]
  governing_equation: string
  substitution: string
  calculation_steps: string[]
  final_answer: string
  units: string
  physical_meaning: string
  distractor_analysis: DistractorAnalysis[]
}

export interface ConceptualSolution {
  kind: 'conceptual'
  governing_concept: string
  application_steps: string[]
  option_elimination: DistractorAnalysis[]
  conclusion: string
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

export interface HistoryEvaluationContext {
  run_id: number
  assessment_id: number
  question_id: number
  question: Question
  rubric: RubricSnapshot
  llm_evaluation: Evaluation
  human_evaluation: Evaluation | null
  comparison: EvaluationComparison | null
  previous_question_id: number | null
  next_question_id: number | null
  history_path: string
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
  learning_objectives: string[]
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
