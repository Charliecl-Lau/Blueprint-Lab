import { useState } from 'react'
import type { ReactNode, HTMLAttributes } from 'react'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'elevated' | 'bordered' | 'subtle'
  padding?: 'none' | 'sm' | 'md' | 'lg' | 'xl'
  interactive?: boolean
  selected?: boolean
  children?: ReactNode
}

export function Card({
  children,
  variant = 'default',
  padding = 'md',
  interactive = false,
  selected = false,
  onClick,
  style,
  ...props
}: CardProps) {
  const [hovered, setHovered] = useState(false)

  const paddingMap: Record<string, string> = {
    none: '0',
    sm:   'var(--space-4)',
    md:   'var(--space-5) var(--space-6)',
    lg:   'var(--space-6) var(--space-8)',
    xl:   'var(--space-8) var(--space-10)',
  }

  const baseStyles: Record<string, object> = {
    default:  { background: 'var(--color-surface)', border: selected ? '1.5px solid var(--color-accent)' : '1px solid var(--color-border)', boxShadow: interactive && hovered ? 'var(--shadow-md)' : 'var(--shadow-sm)' },
    elevated: { background: 'var(--color-surface)', border: selected ? '1.5px solid var(--color-accent)' : 'none', boxShadow: interactive && hovered ? 'var(--shadow-lg)' : 'var(--shadow-md)' },
    bordered: { background: 'var(--color-surface)', border: selected ? '1.5px solid var(--color-accent)' : 'var(--border-strong)', boxShadow: 'none' },
    subtle:   { background: selected ? 'var(--color-accent-subtle)' : 'var(--color-bg-secondary)', border: selected ? '1.5px solid var(--color-blue-200)' : 'var(--border-subtle)', boxShadow: 'none' },
  }

  return (
    <div
      style={{
        borderRadius: 'var(--radius-lg)',
        padding: paddingMap[padding],
        cursor: interactive ? 'pointer' : 'default',
        transition: 'box-shadow var(--transition-base), transform var(--transition-base), border-color var(--transition-fast)',
        transform: interactive && hovered && !selected ? 'translateY(-1px)' : 'translateY(0)',
        outline: 'none',
        ...baseStyles[variant],
        ...style,
      }}
      onClick={interactive ? onClick : undefined}
      onMouseEnter={interactive ? () => setHovered(true) : undefined}
      onMouseLeave={interactive ? () => setHovered(false) : undefined}
      {...props}
    >
      {children}
    </div>
  )
}
