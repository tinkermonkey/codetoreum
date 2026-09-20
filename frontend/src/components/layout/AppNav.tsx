import { NavLink } from 'react-router-dom'
import { Settings, GitBranch, Users, Activity, History } from 'lucide-react'
import { cn } from '@/lib/utils'

const links = [
  { to: '/', label: 'Overview', icon: Activity, end: true },
  { to: '/config', label: 'Project', icon: Settings },
  { to: '/workflows', label: 'Workflows', icon: GitBranch },
  { to: '/agents', label: 'Agents', icon: Users },
  { to: '/history', label: 'History', icon: History },
]

export function AppNav() {
  return (
    <header className="sticky top-0 z-40 border-b border-border/70 nav-glass">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
        <NavLink
          to="/"
          className="group flex items-baseline gap-2 rounded-md focus-visible:outline-none"
          aria-label="Codetoreum home"
        >
          <span className="font-sans text-lg font-semibold tracking-tight text-foreground">
            Codetoreum
          </span>
          <span className="hidden font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground sm:inline">
            Orchestrator
          </span>
        </NavLink>

        <nav aria-label="Primary" className="flex items-center gap-0.5 overflow-x-auto">
          {links.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  'inline-flex min-h-9 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm font-medium transition-colors',
                  'text-muted-foreground hover:bg-secondary hover:text-foreground',
                  isActive && 'bg-secondary text-foreground'
                )
              }
            >
              <Icon className="h-3.5 w-3.5 opacity-70" aria-hidden />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  )
}
