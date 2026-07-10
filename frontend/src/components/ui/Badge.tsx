import type { ReactNode, HTMLAttributes } from 'react'

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'info' | 'success' | 'warning' | 'error' | 'purple'
  size?: 'sm' | 'md' | 'lg'
  dot?: boolean
  children?: ReactNode
}

export function Badge({ children, variant = 'default', size = 'md', dot = false, style, ...props }: BadgeProps) {
  const variants: Record<string, object> = {
    default: { background: 'var(--color-gray-100)', color: 'var(--color-text-secondary)', border: '1px solid var(--color-border)', dotColor: 'var(--color-gray-400)' },
    info:    { background: 'var(--color-accent-subtle)', color: 'var(--color-blue-600)', border: '1px solid var(--color-blue-200)', dotColor: 'var(--color-accent)' },
    success: { background: 'var(--color-success-subtle)', color: 'var(--color-green-600)', border: '1px solid var(--color-green-200)', dotColor: 'var(--color-success)' },
    warning: { background: 'var(--color-warning-subtle)', color: 'var(--color-amber-600)', border: '1px solid var(--color-amber-100)', dotColor: 'var(--color-warning)' },
    error:   { background: 'var(--color-error-subtle)', color: 'var(--color-red-600)', border: '1px solid var(--color-red-100)', dotColor: 'var(--color-error)' },
    purple:  { background: 'var(--color-purple-50)', color: 'var(--color-purple-500)', border: '1px solid var(--color-purple-200)', dotColor: 'var(--color-purple-500)' },
  }

  const sizes: Record<string, object> = {
    sm: { fontSize: '10px', padding: '1px 6px', height: '17px', borderRadius: '5px', gap: '3px', dotSize: '4px' },
    md: { fontSize: '11px', padding: '2px 7px', height: '20px', borderRadius: '6px', gap: '4px', dotSize: '5px' },
    lg: { fontSize: '12px', padding: '3px 9px', height: '24px', borderRadius: '7px', gap: '5px', dotSize: '6px' },
  }

  const v = variants[variant] as any
  const s = sizes[size] as any

  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: s.gap, height: s.height,
      padding: s.padding, borderRadius: s.borderRadius, fontSize: s.fontSize,
      fontFamily: 'var(--font-sans)', fontWeight: '500', letterSpacing: '0.01em',
      whiteSpace: 'nowrap', background: v.background, color: v.color, border: v.border, lineHeight: 1,
      ...style,
    }} {...props}>
      {dot && <span style={{ width: s.dotSize, height: s.dotSize, borderRadius: '50%', background: v.dotColor, flexShrink: 0, display: 'inline-block' }} />}
      {children}
    </span>
  )
}
