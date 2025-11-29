import { useState, useCallback } from 'react'

export interface Toast {
  title: string
  description?: string
  variant?: 'default' | 'destructive'
}

// Simple toast implementation - you can replace with a more sophisticated library
export function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([])

  const toast = useCallback((toast: Toast) => {
    // For now, just log to console
    // In a real implementation, this would show a toast notification
    if (toast.variant === 'destructive') {
      console.error(`[Toast] ${toast.title}`, toast.description)
    } else {
      console.log(`[Toast] ${toast.title}`, toast.description)
    }

    setToasts((prev) => [...prev, toast])

    // Auto-dismiss after 3 seconds
    setTimeout(() => {
      setToasts((prev) => prev.slice(1))
    }, 3000)
  }, [])

  return { toast, toasts }
}
