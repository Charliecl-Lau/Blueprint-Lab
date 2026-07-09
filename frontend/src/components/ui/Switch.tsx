interface SwitchProps {
  checked: boolean
  onChange: (checked: boolean) => void
  size?: 'sm' | 'md' | 'lg'
  disabled?: boolean
  label?: string
}

export function Switch({ checked, onChange, size = 'md', disabled = false, label }: SwitchProps) {
  const sizes: Record<string, { track: object; knob: object; knobOn: string }> = {
    sm: { track: { width: 28, height: 16, borderRadius: 99 }, knob: { width: 12, height: 12, top: 2, left: 2 }, knobOn: '14px' },
    md: { track: { width: 36, height: 20, borderRadius: 99 }, knob: { width: 16, height: 16, top: 2, left: 2 }, knobOn: '18px' },
    lg: { track: { width: 44, height: 24, borderRadius: 99 }, knob: { width: 20, height: 20, top: 2, left: 2 }, knobOn: '22px' },
  }
  const s = sizes[size]

  return (
    <label style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', cursor: disabled ? 'not-allowed' : 'pointer', userSelect: 'none' }}>
      <div
        role="switch"
        aria-checked={checked}
        tabIndex={disabled ? -1 : 0}
        onClick={() => !disabled && onChange(!checked)}
        onKeyDown={(e) => { if ((e.key === ' ' || e.key === 'Enter') && !disabled) onChange(!checked) }}
        style={{
          position: 'relative', flexShrink: 0, opacity: disabled ? 0.45 : 1,
          background: checked ? 'var(--color-accent)' : 'var(--color-gray-300)',
          transition: 'background var(--transition-base)',
          ...s.track,
        }}
      >
        <span style={{
          position: 'absolute',
          top: (s.knob as any).top,
          left: checked ? s.knobOn : `${(s.knob as any).left}px`,
          width: (s.knob as any).width,
          height: (s.knob as any).height,
          borderRadius: '50%',
          background: 'white',
          boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
          transition: 'left var(--transition-spring)',
        }} />
      </div>
      {label && <span style={{ fontSize: '13px', fontFamily: 'var(--font-sans)', color: 'var(--color-text-primary)' }}>{label}</span>}
    </label>
  )
}
