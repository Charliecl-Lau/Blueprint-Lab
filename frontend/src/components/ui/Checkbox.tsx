interface CheckboxProps {
  checked: boolean
  indeterminate?: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
  label?: string
  description?: string
}

export function Checkbox({ checked, indeterminate = false, onChange, disabled = false, label, description }: CheckboxProps) {
  const isChecked = checked || indeterminate

  return (
    <label style={{ display: 'inline-flex', alignItems: 'flex-start', gap: '8px', cursor: disabled ? 'not-allowed' : 'pointer', userSelect: 'none' }}>
      <div
        role="checkbox"
        aria-checked={indeterminate ? 'mixed' : checked}
        tabIndex={disabled ? -1 : 0}
        onClick={() => !disabled && onChange(!checked)}
        onKeyDown={(e) => { if ((e.key === ' ' || e.key === 'Enter') && !disabled) onChange(!checked) }}
        style={{
          width: 16, height: 16, borderRadius: 4, flexShrink: 0, marginTop: 1,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: isChecked ? 'var(--color-accent)' : 'var(--color-white)',
          border: isChecked ? '1.5px solid var(--color-accent)' : '1.5px solid var(--color-border)',
          transition: 'background var(--transition-fast), border-color var(--transition-fast)',
          opacity: disabled ? 0.45 : 1,
        }}
      >
        {indeterminate && (
          <svg width="8" height="2" viewBox="0 0 8 2" fill="none">
            <rect width="8" height="2" rx="1" fill="white"/>
          </svg>
        )}
        {!indeterminate && checked && (
          <svg width="9" height="7" viewBox="0 0 9 7" fill="none">
            <path d="M1 3.5L3.5 6L8 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        )}
      </div>
      {(label || description) && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          {label && <span style={{ fontSize: '13px', fontFamily: 'var(--font-sans)', color: 'var(--color-text-primary)', fontWeight: '500' }}>{label}</span>}
          {description && <span style={{ fontSize: '12px', fontFamily: 'var(--font-sans)', color: 'var(--color-text-secondary)' }}>{description}</span>}
        </div>
      )}
    </label>
  )
}
