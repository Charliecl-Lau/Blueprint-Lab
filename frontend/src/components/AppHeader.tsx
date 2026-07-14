import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

export function AppHeader({ subtitle, action }: { subtitle: string; action?: ReactNode }) {
  return (
    <header>
      <Link className="logo-link" to="/" aria-label="Go to Blueprint Lab home">
        Blueprint Lab
      </Link>
      <span>{subtitle}</span>
      {action && <div className="header-action">{action}</div>}
    </header>
  )
}
