import { useState, ReactNode, ButtonHTMLAttributes } from 'react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'outline' | 'destructive'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  icon?: ReactNode
  iconPosition?: 'left' | 'right'
  fullWidth?: boolean
  children?: ReactNode
}

export function Button({
  children,
  variant = 'primary',
  size = 'md',
  disabled = false,
  loading = false,
  icon,
  iconPosition = 'left',
  fullWidth = false,
  onClick,
  type = 'button',
  style,
  ...props
}: ButtonProps) {
  const [hovered, setHovered] = useState(false)
  const [pressed, setPressed] = useState(false)

  const sizes = {
    sm: { fontSize: '12px', padding: '0 11px', height: '28px', borderRadius: '7px', gap: '5px', iconSize: '13px' },
    md: { fontSize: '13px', padding: '0 15px', height: '34px', borderRadius: '9px', gap: '6px', iconSize: '14px' },
    lg: { fontSize: '15px', padding: '0 20px', height: '42px', borderRadius: '11px', gap: '7px', iconSize: '16px' },
  }

  const s = sizes[size]
  const isActive = hovered && !disabled
  const isPressed = pressed && !disabled

  const variantStyles: Record<string, object> = {
    primary: {
      background: isPressed ? 'var(--color-blue-700)' : isActive ? 'var(--color-accent-hover)' : 'var(--color-accent)',
      color: 'var(--color-white)',
      border: 'none',
      boxShadow: isActive ? '0 2px 8px rgba(26,86,219,0.32)' : '0 1px 3px rgba(26,86,219,0.20)',
    },
    secondary: {
      background: isPressed ? 'var(--color-gray-200)' : isActive ? 'var(--color-gray-100)' : 'var(--color-gray-50)',
      color: 'var(--color-text-primary)',
      border: '1px solid var(--color-border)',
      boxShadow: 'var(--shadow-xs)',
    },
    ghost: {
      background: isPressed ? 'var(--color-gray-100)' : isActive ? 'var(--color-gray-50)' : 'transparent',
      color: 'var(--color-text-primary)',
      border: 'none',
      boxShadow: 'none',
    },
    outline: {
      background: isPressed ? 'var(--color-blue-50)' : isActive ? 'var(--color-accent-subtle)' : 'transparent',
      color: 'var(--color-accent)',
      border: '1.5px solid var(--color-accent)',
      boxShadow: 'none',
    },
    destructive: {
      background: isPressed ? 'var(--color-red-600)' : isActive ? '#e8342a' : 'var(--color-error)',
      color: 'var(--color-white)',
      border: 'none',
      boxShadow: isActive ? '0 2px 8px rgba(255,59,48,0.32)' : '0 1px 3px rgba(255,59,48,0.20)',
    },
  }

  const btnStyle: object = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: s.gap,
    height: s.height,
    padding: s.padding,
    borderRadius: s.borderRadius,
    fontSize: s.fontSize,
    fontFamily: 'var(--font-sans)',
    fontWeight: '500',
    letterSpacing: '-0.01em',
    whiteSpace: 'nowrap',
    cursor: disabled ? 'not-allowed' : 'pointer',
    transition: 'background 150ms var(--ease-out), box-shadow 150ms var(--ease-out), transform 100ms var(--ease-out)',
    outline: 'none',
    width: fullWidth ? '100%' : undefined,
    opacity: disabled ? 0.42 : 1,
    transform: isPressed ? 'scale(0.977)' : 'scale(1)',
    flexShrink: 0,
    ...variantStyles[variant],
    ...style,
  }

  const spinnerStyle: object = {
    display: 'inline-block',
    width: s.iconSize,
    height: s.iconSize,
    border: '1.5px solid currentColor',
    borderTopColor: 'transparent',
    borderRadius: '50%',
    animation: 'db-spin 0.55s linear infinite',
    flexShrink: 0,
  }

  return (
    <button
      type={type}
      style={btnStyle}
      disabled={disabled}
      onClick={!disabled ? onClick : undefined}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => { setHovered(false); setPressed(false) }}
      onMouseDown={() => setPressed(true)}
      onMouseUp={() => setPressed(false)}
      {...props}
    >
      {loading ? <span style={spinnerStyle} /> : (icon && iconPosition === 'left' ? icon : null)}
      {children}
      {!loading && icon && iconPosition === 'right' ? icon : null}
    </button>
  )
}
