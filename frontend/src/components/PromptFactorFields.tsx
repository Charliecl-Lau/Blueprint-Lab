import {
  factorContentId,
  PROMPT_FACTORS,
  type FactorKey,
} from '../validation/experimentValidation'

interface Props {
  enabled: Record<FactorKey, boolean>
  content: Record<FactorKey, string>
  errors: Record<string, string>
  onToggle: (key: FactorKey) => void
  onContent: (key: FactorKey, value: string) => void
}

export function PromptFactorFields({ enabled, content, errors, onToggle, onContent }: Props) {
  return <><div className="factor-grid" role="group" aria-label="Prompt factor selection">
    {PROMPT_FACTORS.map((factor) => (
      <label className={`factor-card ${enabled[factor.key] ? 'selected' : ''}`} key={factor.key}>
        <input type="checkbox" aria-label={factor.label} checked={enabled[factor.key]} onChange={() => onToggle(factor.key)} />
        <span><strong>{factor.label}</strong><small>{factor.help}</small></span>
      </label>
    ))}
  </div>
  <section className="manual-input" role="region" aria-label="Manual Input">
    <h3>Manual Input</h3><p>Add the material used by each selected factor.</p>
    {(Object.keys(enabled) as FactorKey[]).every((key) => !enabled[key]) && <div className="empty-input">Select a factor above to add its content.</div>}
    {PROMPT_FACTORS.map((factor) => {
      const inputId = factorContentId(factor.key)
      const error = errors[inputId]
      return enabled[factor.key] && <div className="factor-content" key={factor.key}>
          <label htmlFor={inputId}>{factor.label.replace(' (chain-of-thought condition)', '')} content</label>
          <textarea id={inputId} value={content[factor.key]} maxLength={20000} rows={4} aria-invalid={error ? 'true' : undefined} aria-describedby={error ? `${inputId}-error` : undefined} onChange={(event) => onContent(factor.key, event.target.value)} />
          <div className="field-meta"><span className="error" id={error ? `${inputId}-error` : undefined}>{error}</span><span>{content[factor.key].length}/20,000</span></div>
        </div>
    })}
  </section></>
}
