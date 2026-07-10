import { useState } from 'react'
import type { ReactNode } from 'react'

export interface TabItem { id: string; label: string; icon?: ReactNode; count?: number }

interface TabsProps {
  tabs?: TabItem[]
  activeTab?: string
  onTabChange?: (id: string) => void
  variant?: 'underline' | 'pill' | 'boxed'
}

export function Tabs({ tabs = [], activeTab, onTabChange, variant = 'underline' }: TabsProps) {
  const [hovered, setHovered] = useState<string | null>(null)

  const containerStyles: Record<string, object> = {
    underline: { display: 'flex', borderBottom: '1px solid var(--color-border)', gap: '0' },
    pill: { display: 'inline-flex', gap: '2px', background: 'var(--color-bg-secondary)', borderRadius: 'var(--radius-lg)', padding: '3px' },
    boxed: { display: 'flex', gap: 'var(--space-1)' },
  }

  function getTabStyle(active: boolean, isHovered: boolean): object {
    if (variant === 'underline') return {
      padding: '8px 16px', fontSize: '13px', fontWeight: active ? '500' : '400',
      fontFamily: 'var(--font-sans)', letterSpacing: '-0.01em',
      color: active ? 'var(--color-text-primary)' : isHovered ? 'var(--color-text-secondary)' : 'var(--color-text-tertiary)',
      cursor: 'pointer', background: 'none', border: 'none',
      borderBottom: `2px solid ${active ? 'var(--color-accent)' : 'transparent'}`,
      marginBottom: '-1px', transition: 'color var(--transition-fast), border-color var(--transition-fast)',
      outline: 'none', display: 'flex', alignItems: 'center', gap: '6px', whiteSpace: 'nowrap', flexShrink: 0,
    }
    if (variant === 'pill') return {
      padding: '5px 13px', fontSize: '13px', fontWeight: active ? '500' : '400',
      fontFamily: 'var(--font-sans)', letterSpacing: '-0.01em',
      color: active ? 'var(--color-text-primary)' : isHovered ? 'var(--color-text-secondary)' : 'var(--color-text-tertiary)',
      cursor: 'pointer', background: active ? 'var(--color-white)' : isHovered ? 'rgba(0,0,0,0.03)' : 'transparent',
      border: 'none', borderRadius: 'var(--radius-md)', boxShadow: active ? 'var(--shadow-sm)' : 'none',
      transition: 'all var(--transition-base)', outline: 'none',
      display: 'flex', alignItems: 'center', gap: '6px', whiteSpace: 'nowrap', flexShrink: 0,
    }
    return {
      padding: '5px 13px', fontSize: '13px', fontWeight: active ? '500' : '400',
      fontFamily: 'var(--font-sans)', letterSpacing: '-0.01em',
      color: active ? 'var(--color-accent)' : isHovered ? 'var(--color-text-secondary)' : 'var(--color-text-tertiary)',
      cursor: 'pointer', background: active ? 'var(--color-accent-subtle)' : isHovered ? 'var(--color-bg-secondary)' : 'transparent',
      border: active ? '1px solid var(--color-blue-200)' : '1px solid transparent',
      borderRadius: 'var(--radius-md)', transition: 'all var(--transition-fast)', outline: 'none',
      display: 'flex', alignItems: 'center', gap: '6px', whiteSpace: 'nowrap', flexShrink: 0,
    }
  }

  return (
    <div style={containerStyles[variant]} role="tablist">
      {tabs.map(tab => (
        <button
          key={tab.id}
          role="tab"
          aria-selected={activeTab === tab.id}
          style={getTabStyle(activeTab === tab.id, hovered === tab.id)}
          onClick={() => onTabChange?.(tab.id)}
          onMouseEnter={() => setHovered(tab.id)}
          onMouseLeave={() => setHovered(null)}
        >
          {tab.icon && <span style={{ display: 'inline-flex', flexShrink: 0 }}>{tab.icon}</span>}
          {tab.label}
          {tab.count != null && (
            <span style={{
              fontSize: '10px', fontWeight: '500',
              background: activeTab === tab.id ? 'var(--color-accent)' : 'var(--color-gray-200)',
              color: activeTab === tab.id ? 'white' : 'var(--color-text-secondary)',
              borderRadius: 'var(--radius-full)', padding: '1px 5px', lineHeight: '14px', minWidth: '16px', textAlign: 'center',
            }}>
              {tab.count}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}
