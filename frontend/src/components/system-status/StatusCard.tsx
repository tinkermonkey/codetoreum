/**
 * StatusCard Component
 *
 * Shared card component for displaying system status information.
 * Provides consistent styling and layout for header cards.
 */

import * as React from 'react'
import { Card } from '../ui/card'
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
  return (
    <Card
      className={cn(
        'min-w-[180px] transition-all',
        isExpandable && 'cursor-pointer hover:shadow-md',
        className
      )}
      onClick={onClick}
    >
      <div className="p-3">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-muted-foreground">{title}</h3>
          {headerAction && <div className="ml-2">{headerAction}</div>}
        </div>
        <div className={cn('transition-all', isExpanded && 'mt-3')}>{children}</div>
      </div>
    </Card>
  )
}
