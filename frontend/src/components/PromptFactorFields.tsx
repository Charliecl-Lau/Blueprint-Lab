export const PROMPT_FACTORS = [
  { key: 'conceptBridge', label: 'Concept Bridge', help: 'Connect the topic to concepts students already know.' },
  { key: 'fewShot', label: 'Few-shot Examples', help: 'Provide representative question-and-answer examples.' },
  { key: 'referenceContent', label: 'Reference Content', help: 'Provide notes, excerpts, facts, or source material.' },
  { key: 'reasoningGuidance', label: 'Reasoning Guidance (chain-of-thought condition)', help: 'Request concise rationale or structured solution steps, not hidden model reasoning.' },
] as const

export type FactorKey = typeof PROMPT_FACTORS[number]['key']

interface Props {
  enabled: Record<FactorKey, boolean>
  content: Record<FactorKey, string>
  errors: Partial<Record<FactorKey, string>>
  onToggle: (key: FactorKey) => void
  onContent: (key: FactorKey, value: string) => void
}

export function PromptFactorFields({ enabled, content, errors, onToggle, onContent }: Props) {
  return <div className="factor-list">
    {PROMPT_FACTORS.map((factor) => {
      const inputId = `${factor.key}-content`
      return <div className="factor" key={factor.key}>
        <label className="factor-toggle">
          <input type="checkbox" aria-label={factor.label} checked={enabled[factor.key]} onChange={() => onToggle(factor.key)} aria-expanded={enabled[factor.key]} />
          <span><strong>{factor.label}</strong><small>{factor.help}</small></span>
        </label>
        {enabled[factor.key] && <div className="factor-content">
          <label htmlFor={inputId}>{factor.label.replace(' (chain-of-thought condition)', '')} content</label>
          <textarea id={inputId} value={content[factor.key]} maxLength={20000} rows={4} onChange={(event) => onContent(factor.key, event.target.value)} />
          <div className="field-meta"><span className="error">{errors[factor.key]}</span><span>{content[factor.key].length}/20,000</span></div>
        </div>}
      </div>
    })}
  </div>
}
