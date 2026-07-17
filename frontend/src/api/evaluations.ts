import { api } from './client'
import type {
  AssessmentQuestionSummary,
  Evaluation,
  EvaluationAccessDetail,
  EvaluationComparison,
  GradingContext,
  HumanEvaluationPatch,
  Run,
} from '../types'


export const evaluationsApi = {
  questions: (assessmentId: number): Promise<AssessmentQuestionSummary[]> => (
    api.get(`/assessments/${assessmentId}/questions`)
  ),
  list: (assessmentId: number): Promise<Evaluation[]> => (
    api.get(`/assessments/${assessmentId}/evaluations`)
  ),
  gradingContext: (questionId: number): Promise<GradingContext> => (
    api.get(`/assessment-questions/${questionId}/grading-context`)
  ),
  createHuman: (questionId: number): Promise<Evaluation> => (
    api.post(`/assessment-questions/${questionId}/evaluations/human`, {})
  ),
  update: (evaluationId: number, payload: HumanEvaluationPatch): Promise<Evaluation> => (
    api.patch(`/evaluations/${evaluationId}`, payload)
  ),
  finalize: (evaluationId: number): Promise<Evaluation> => (
    api.post(`/evaluations/${evaluationId}/finalize`, {})
  ),
  reopen: (evaluationId: number): Promise<Evaluation> => (
    api.post(`/evaluations/${evaluationId}/reopen`, {})
  ),
  recordLlmAccess: (
    humanEvaluationId: number,
    llmEvaluationId: number,
  ): Promise<EvaluationAccessDetail> => (
    api.post(`/evaluations/${humanEvaluationId}/llm-access`, {
      llm_evaluation_id: llmEvaluationId,
    })
  ),
  comparison: (questionId: number): Promise<EvaluationComparison> => (
    api.get(`/assessment-questions/${questionId}/evaluation-comparison`)
  ),
  retryLlm: (assessmentId: number): Promise<Run> => (
    api.post(`/assessments/${assessmentId}/evaluations/llm/retry`, {})
  ),
}
