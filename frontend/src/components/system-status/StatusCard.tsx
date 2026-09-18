/**
 * StatusCard — compact system metric tile
 */

import * as React from 'react'
import { cn } from '../../lib/utils'

export interface StatusCardProps {
  title: string
  children: React.ReactNode
  className?: string
  headerAction?: React.ReactNode
  onClick?: () => void
  isExpandable?: boolean
  isExpanded?: boolean
}

export function StatusCard({
  title,
  children,
  className,
  headerAction,
  onClick,
  isExpandable = false,
  isExpanded = false,
}: StatusCardProps) {
  const interactive = Boolean(onClick || isExpandable)
  const contentId = React.useId()

  if (interactive) {
    return (
      <button
        type="button"
        className={cn(
          'min-w-[160px] flex-1 rounded-xl border border-border/80 bg-card px-3.5 py-3 text-left shadow-soft transition-colors',
          'cursor-pointer hover:bg-secondary/40',
          className
        )}
        onClick={onClick}
        aria-expanded={isExpandable ? isExpanded : undefined}
        aria-controls={isExpandable ? contentId : undefined}
      >
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <h3 className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
            {title}
          </h3>
          {headerAction ? <div>{headerAction}</div> : null}
        </div>
        <div id={isExpandable ? contentId : undefined}>{children}</div>
      </button>
    )
  }

  return (
    <div
      className={cn(
        'min-w-[160px] flex-1 rounded-xl border border-border/80 bg-card px-3.5 py-3 text-left shadow-soft',
        className
      )}
    >
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <h3 className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
          {title}
        </h3>
        {headerAction ? <div>{headerAction}</div> : null}
      </div>
      <div>{children}</div>
    </div>
  )
}
