import { Link } from 'react-router-dom'

export function AppHeader({ subtitle }: { subtitle: string }) {
  return (
    <header>
      <Link className="logo-link" to="/" aria-label="Go to Blueprint Lab home">
        Blueprint Lab
      </Link>
      <span>{subtitle}</span>
    </header>
  )
}
