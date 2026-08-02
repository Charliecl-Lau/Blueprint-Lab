import { MathContent, StandaloneEquations } from '../MathContent'
import { referencedEquationLabels } from '../../math/equationReferences'
import type { Question } from '../../types'

export function QuestionsSolutionsPanel({ questions }: { questions: Question[] }) {
  return <div className="history-question-list">{questions.map((question, index) => {
    const equations = question.equations ?? []
    const referencedLabels = referencedEquationLabels(
      question.body,
      ...question.options?.map((option) => option.body) ?? [],
      question.model_answer,
    )
    return <div className="question" key={question.id ?? index}>
      <strong>{index + 1}. <MathContent text={question.body} segments={question.body_segments} equations={equations} location="question" /></strong>
      {question.options?.map((option, optionIndex) => (
        <p key={option.id ?? optionIndex}><MathContent text={option.body} segments={option.segments} equations={equations} location="question" />{option.is_correct ? ' ✓' : ''}</p>
      ))}
      <StandaloneEquations equations={equations} location="question" referencedLabels={referencedLabels} />
      {question.model_answer && <p><strong>Solution:</strong> <MathContent text={question.model_answer} segments={question.model_answer_segments} equations={equations} location="solution" /></p>}
      <StandaloneEquations equations={equations} location="solution" referencedLabels={referencedLabels} />
    </div>
  })}</div>
}
