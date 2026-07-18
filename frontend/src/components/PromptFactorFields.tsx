import {
  factorContentId,
  PROMPT_FACTORS,
  REFERENCE_PDF_INPUT_ID,
  type FactorKey,
} from '../validation/experimentValidation'

interface Props {
  enabled: Record<FactorKey, boolean>
  content: Record<FactorKey, string>
  errors: Record<string, string>
  onToggle: (key: FactorKey) => void
  onContent: (key: FactorKey, value: string) => void
  referencePdfs: File[]
  referencePdfInputKey: number
  onReferencePdfs: (files: File[]) => void
}

export function PromptFactorFields({ enabled, content, errors, onToggle, onContent, referencePdfs, referencePdfInputKey, onReferencePdfs }: Props) {
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
      if (!enabled[factor.key]) return null
      if (factor.key === 'referenceContent') {
        const error = errors[REFERENCE_PDF_INPUT_ID]
        const describedBy = [
          `${REFERENCE_PDF_INPUT_ID}-limits`,
          `${REFERENCE_PDF_INPUT_ID}-pages`,
          error ? `${REFERENCE_PDF_INPUT_ID}-error` : '',
        ].filter(Boolean).join(' ')
        return <div className="factor-content reference-pdf-input" key={factor.key}>
          <label htmlFor={REFERENCE_PDF_INPUT_ID}>Reference Content PDFs</label>
          <input
            key={referencePdfInputKey}
            id={REFERENCE_PDF_INPUT_ID}
            type="file"
            accept="application/pdf,.pdf"
            multiple
            aria-invalid={error ? 'true' : undefined}
            aria-describedby={describedBy}
            onChange={(event) => onReferencePdfs(Array.from(event.currentTarget.files ?? []))}
          />
          <small id={`${REFERENCE_PDF_INPUT_ID}-limits`}>Maximum 3 PDFs; 20 MB per PDF.</small>
          <small id={`${REFERENCE_PDF_INPUT_ID}-pages`}>Please do not upload PDFs longer than 100 pages.</small>
          {referencePdfs.length > 0 && <ol aria-label="Selected reference PDFs" className="reference-pdf-list">
            {referencePdfs.map((pdf, index) => <li key={`${pdf.name}-${pdf.size}-${index}`}>{pdf.name}</li>)}
          </ol>}
          {error && <span className="error" id={`${REFERENCE_PDF_INPUT_ID}-error`}>{error}</span>}
        </div>
      }
      const inputId = factorContentId(factor.key)
      const error = errors[inputId]
      return <div className="factor-content" key={factor.key}>
          <label htmlFor={inputId}>{factor.label.replace(' (chain-of-thought condition)', '')} content</label>
          <textarea id={inputId} value={content[factor.key]} maxLength={20000} rows={4} aria-invalid={error ? 'true' : undefined} aria-describedby={error ? `${inputId}-error` : undefined} onChange={(event) => onContent(factor.key, event.target.value)} />
          <div className="field-meta"><span className="error" id={error ? `${inputId}-error` : undefined}>{error}</span><span>{content[factor.key].length}/20,000</span></div>
        </div>
    })}
  </section></>
}
