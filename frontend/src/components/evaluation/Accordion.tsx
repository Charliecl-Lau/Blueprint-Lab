import { useId, useState, type ReactNode } from 'react'

export function Accordion({
  title,
  children,
  defaultExpanded = false,
  disabled = false,
  notice,
  onExpandedChange,
}: {
  title: string
  children: ReactNode
  defaultExpanded?: boolean
  disabled?: boolean
  notice?: string
  onExpandedChange?: (expanded: boolean) => void
}) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const generatedId = useId()
  const panelId = `evaluation-panel-${generatedId.replaceAll(':', '')}`

  const toggle = () => {
    if (disabled) return
    const next = !expanded
    setExpanded(next)
    onExpandedChange?.(next)
  }

  return (
    <section className={`evaluation-accordion ${expanded ? 'expanded' : 'collapsed'}`}>
      <button
        className="evaluation-accordion-trigger"
        type="button"
        aria-expanded={expanded}
        aria-controls={panelId}
        disabled={disabled}
        onClick={toggle}
      >
        {title}
      </button>
      {notice && !expanded && <p className="bias-notice">{notice}</p>}
      {expanded && <div className="evaluation-accordion-panel" id={panelId}>{children}</div>}
    </section>
  )
}
