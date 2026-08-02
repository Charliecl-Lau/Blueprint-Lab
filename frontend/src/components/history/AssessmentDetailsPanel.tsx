import type { HistoryAssessmentDetails } from '../../types'

const assessmentTypeLabels = {
  mcq: 'Multiple choice',
  short_answer: 'Short answer',
  mixed: 'Mixed',
}

const cognitiveDemandLabels = {
  remember_understand: 'Remember/Understand',
  apply_analyze: 'Apply/Analyze',
  evaluate_create: 'Evaluate/Create',
}

const factorLabels: Record<string, string> = {
  concept_bridge: 'Concept Bridge',
  few_shot: 'Few-shot Examples',
  reference_content: 'Reference Content',
  reasoning_guidance: 'Reasoning Guidance',
}

const factorKeys = [
  'concept_bridge',
  'few_shot',
  'reference_content',
  'reasoning_guidance',
]

const textFactorKeys = [
  'concept_bridge',
  'few_shot',
  'reasoning_guidance',
]

export function AssessmentDetailsPanel({ details }: { details: HistoryAssessmentDetails }) {
  return <div className="history-details">
    <dl>
      <div><dt>Course</dt><dd>{details.course}</dd></div>
      <div><dt>Topic</dt><dd>{details.topic}</dd></div>
      <div><dt>Assessment format</dt><dd>{assessmentTypeLabels[details.assessment_type]}</dd></div>
      <div><dt>Difficulty</dt><dd>{details.difficulty}</dd></div>
      <div><dt>Number of questions</dt><dd>{details.number_of_questions}</dd></div>
      <div><dt>Estimated student completion time</dt><dd>{details.estimated_time_minutes} minutes</dd></div>
      <div><dt>Cognitive demand</dt><dd>{cognitiveDemandLabels[details.cognitive_demand]}</dd></div>
      <div><dt>Prompt structure</dt><dd>{details.prompt_structure === 'openai' ? 'OpenAI' : 'Anthropic'}</dd></div>
      <div><dt>Additional instruction</dt><dd>{details.additional_instruction || 'None'}</dd></div>
    </dl>

    <section>
      <h3>Learning objectives</h3>
      {details.learning_objectives.length > 0
        ? <ul>{details.learning_objectives.map((objective) => <li key={objective}>{objective}</li>)}</ul>
        : <p>None</p>}
    </section>

    <section>
      <h3>Prompt design factors</h3>
      <dl className="history-factor-list">
        {factorKeys.map((key) => <div key={key}>
          <dt>{factorLabels[key]}</dt>
          <dd><strong>{details.factor_configuration[key] ? 'On' : 'Off'}</strong></dd>
        </div>)}
      </dl>
    </section>

    {textFactorKeys.filter((key) => details.factor_configuration[key]).map((key) => <section
      className="history-saved-factor-input"
      key={key}
    >
      <h3>{factorLabels[key]} input</h3>
      <p>{details.factor_inputs[key as keyof typeof details.factor_inputs] || 'No saved input'}</p>
    </section>)}

    <section>
      <h3>Reference PDFs</h3>
      {details.reference_pdf_filenames.length > 0
        ? <ul>{details.reference_pdf_filenames.map((filename) => <li key={filename}>{filename}</li>)}</ul>
        : <p>None</p>}
    </section>
  </div>
}
