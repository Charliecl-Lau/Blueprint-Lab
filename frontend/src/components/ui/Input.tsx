import { useState, ReactNode, InputHTMLAttributes } from 'react'

interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size' | 'prefix'> {
  label?: string
  error?: string
  hint?: string
  size?: 'sm' | 'md' | 'lg'
  prefix?: ReactNode
  suffix?: ReactNode
}

export function Input({
  label,
  placeholder,
  value,
  onChange,
  type = 'text',
  error,
  hint,
  disabled = false,
  readOnly = false,
  size = 'md',
  prefix,
  suffix,
  id,
  ...props
}: InputProps) {
  const [focused, setFocused] = useState(false)

  const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined)

  const heights: Record<string, string> = { sm: '30px', md: '36px', lg: '44px' }
  const fontSizes: Record<string, string> = { sm: '12px', md: '13px', lg: '15px' }
  const paddings: Record<string, string> = { sm: '0 10px', md: '0 12px', lg: '0 14px' }

  const wrapperStyle: object = {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    height: heights[size],
    padding: paddings[size],
    background: disabled ? 'var(--color-bg-secondary)' : readOnly ? 'var(--color-gray-50)' : 'var(--color-white)',
    border: `1px solid ${error ? 'var(--color-error)' : focused ? 'var(--color-accent)' : 'var(--color-border)'}`,
    borderRadius: 'var(--radius-md)',
    boxShadow: focused ? (error ? 'var(--focus-ring-error)' : 'var(--focus-ring-blue)') : 'none',
    transition: 'border-color var(--transition-fast), box-shadow var(--transition-fast)',
    cursor: disabled ? 'not-allowed' : readOnly ? 'default' : 'text',
  }

  const inputStyle: object = {
    flex: 1,
    border: 'none',
    outline: 'none',
    background: 'transparent',
    fontSize: fontSizes[size],
    fontFamily: 'var(--font-sans)',
    color: disabled ? 'var(--color-text-disabled)' : 'var(--color-text-primary)',
    letterSpacing: '-0.01em',
    width: '100%',
    minWidth: 0,
  }

  const affixStyle: object = {
    fontSize: fontSizes[size],
    color: 'var(--color-text-tertiary)',
    flexShrink: 0,
    whiteSpace: 'nowrap',
    userSelect: 'none',
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', width: '100%' }}>
      {label && (
        <label htmlFor={inputId} style={{
          fontSize: '12px', fontWeight: '500', fontFamily: 'var(--font-sans)',
          color: error ? 'var(--color-error)' : 'var(--color-text-secondary)',
          letterSpacing: '-0.01em', userSelect: 'none',
        }}>
          {label}
        </label>
      )}
      <div style={wrapperStyle}>
        {prefix && <span style={affixStyle}>{prefix}</span>}
        <input
          id={inputId}
          type={type}
          value={value}
          onChange={disabled || readOnly ? undefined : onChange}
          placeholder={placeholder}
          disabled={disabled}
          readOnly={readOnly}
          style={inputStyle}
          onFocus={() => !disabled && setFocused(true)}
          onBlur={() => setFocused(false)}
          {...props}
        />
        {suffix && <span style={affixStyle}>{suffix}</span>}
      </div>
      {(error || hint) && (
        <span style={{
          fontSize: '11px', fontFamily: 'var(--font-sans)',
          color: error ? 'var(--color-error)' : 'var(--color-text-tertiary)',
          lineHeight: '1.4', letterSpacing: '-0.01em',
        }}>
          {error || hint}
        </span>
      )}
    </div>
  )
}
