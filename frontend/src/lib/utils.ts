import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { formatDistanceToNow } from 'date-fns'

/** Merge Tailwind / conditional class names (shadcn-style). */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Human-readable relative time, e.g. "5 minutes ago". */
export function formatRelativeTime(date: string | number | Date): string {
  return formatDistanceToNow(new Date(date), { addSuffix: true })
}
