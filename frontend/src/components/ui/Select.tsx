import { useState, SelectHTMLAttributes } from 'react'

interface SelectOption { value: string; label: string; disabled?: boolean }

interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'size'> {
  label?: string
  options?: SelectOption[]
  error?: string
  hint?: string
  size?: 'sm' | 'md' | 'lg'
  placeholder?: string
}

export function Select({ label, value, onChange, options = [], disabled = false, error, hint, size = 'md', placeholder, id, ...props }: SelectProps) {
  const [focused, setFocused] = useState(false)
  const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined)
  const heights: Record<string, string> = { sm: '30px', md: '36px', lg: '44px' }
  const fontSizes: Record<string, string> = { sm: '12px', md: '13px', lg: '15px' }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', width: '100%' }}>
      {label && (
        <label htmlFor={inputId} style={{ fontSize: '12px', fontWeight: '500', fontFamily: 'var(--font-sans)', color: error ? 'var(--color-error)' : 'var(--color-text-secondary)', letterSpacing: '-0.01em', userSelect: 'none' }}>
          {label}
        </label>
      )}
      <div style={{ position: 'relative', width: '100%' }}>
        <select
          id={inputId}
          value={value}
          onChange={disabled ? undefined : onChange}
          disabled={disabled}
          style={{
            width: '100%', height: heights[size], padding: `0 32px 0 12px`,
            fontSize: fontSizes[size], fontFamily: 'var(--font-sans)', fontWeight: '400',
            letterSpacing: '-0.01em', color: value ? 'var(--color-text-primary)' : 'var(--color-text-tertiary)',
            background: disabled ? 'var(--color-bg-secondary)' : 'var(--color-white)',
            border: `1px solid ${error ? 'var(--color-error)' : focused ? 'var(--color-accent)' : 'var(--color-border)'}`,
            borderRadius: 'var(--radius-md)',
            boxShadow: focused ? (error ? 'var(--focus-ring-error)' : 'var(--focus-ring-blue)') : 'none',
            cursor: disabled ? 'not-allowed' : 'pointer',
            transition: 'border-color var(--transition-fast), box-shadow var(--transition-fast)',
            appearance: 'none', WebkitAppearance: 'none', outline: 'none',
            opacity: disabled ? 0.55 : 1,
          }}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          {...props}
        >
          {placeholder && <option value="" disabled hidden>{placeholder}</option>}
          {options.map(opt => (
            <option key={opt.value} value={opt.value} disabled={opt.disabled}>{opt.label}</option>
          ))}
        </select>
        <span style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none', color: 'var(--color-text-tertiary)', display: 'flex', alignItems: 'center' }}>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M3 5.5l4 4 4-4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </span>
      </div>
      {(error || hint) && (
        <span style={{ fontSize: '11px', fontFamily: 'var(--font-sans)', color: error ? 'var(--color-error)' : 'var(--color-text-tertiary)', lineHeight: '1.4' }}>
          {error || hint}
        </span>
      )}
    </div>
  )
}
