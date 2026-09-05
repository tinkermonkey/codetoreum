/**
 * WebSocket Hook
 *
 * Provides real-time event streaming from the backend with automatic reconnection.
 * Now uses Zustand for centralized singleton WebSocket management.
 *
 * Features:
 * - Single WebSocket connection shared across all components (singleton pattern)
 * - Automatic connection with cookie-based authentication
 * - Exponential backoff reconnection (up to 10 attempts)
 * - Close code 4001 (Unauthorized) prevents reconnection
 * - Event filtering and subscription management
 * - Connection status tracking
 *
 * Security improvements:
 * - Uses httpOnly cookies for authentication (no token in URL)
 * - No localStorage usage (prevents XSS token theft)
 *
 * State Management:
 * - Uses Zustand store for global WebSocket connection
 * - Single connection shared across all components
 * - No duplicate connections
 * - Automatic cleanup on component unmount
 *
 * Migration Notes:
 * - This hook now wraps the Zustand WebSocket store
 * - API remains the same for backward compatibility
 * - WebSocket connection is now a singleton (only one connection for entire app)
 */

import { useEffect } from 'react'
import { useWebSocketStore, WebSocketEvent } from '../store/websocketStore'

export interface WebSocketConfig {
  url?: string
  reconnectAttempts?: number
  initialReconnectDelay?: number
  maxReconnectDelay?: number
}

export interface WebSocketState {
  isConnected: boolean
  isConnecting: boolean
  error: string | null
  events: WebSocketEvent[]
  reconnectAttempt: number
}

export type { WebSocketEvent }

/**
 * WebSocket Hook
 *
 * Connects to the WebSocket store and manages connection lifecycle.
 *
 * @param isAuthenticated - Whether the user is authenticated
 * @param isAuthLoading - Whether authentication is still being validated
 * @param config - Optional WebSocket configuration (currently not used, store uses defaults)
 * @returns WebSocket state and control methods
 *
 * Example:
 * ```tsx
 * const { isConnected, events, subscribe, unsubscribe } = useWebSocket(isAuthenticated, isAuthLoading)
 *
 * useEffect(() => {
 *   if (isConnected) {
 *     subscribe('execution.started')
 *     subscribe('execution.completed')
 *   }
 * }, [isConnected, subscribe])
 * ```
 */
export function useWebSocket(
  isAuthenticated: boolean,
  isAuthLoading = false,
  _config: WebSocketConfig = {}
) {
  const {
    isConnected,
    isConnecting,
    error,
    events,
    reconnectAttempt,
    connect,
    disconnect,
    subscribe,
    unsubscribe,
    clearEvents,
  } = useWebSocketStore()

  // Connect/disconnect based on authentication status
  // IMPORTANT: Wait for auth to finish loading before connecting
  useEffect(() => {
    // Don't connect while auth is loading (prevents race condition)
    if (isAuthLoading) {
      return
    }

    if (isAuthenticated) {
      connect(isAuthenticated)
    } else {
      disconnect()
    }

    // Cleanup on unmount
    return () => {
      // Note: We don't disconnect on unmount because the store is shared
      // across all components. The store manages its own cleanup.
    }
  }, [isAuthenticated, isAuthLoading, connect, disconnect])

  return {
    isConnected,
    isConnecting,
    error,
    events,
    reconnectAttempt,
    subscribe,
    unsubscribe,
    clearEvents,
    reconnect: () => connect(isAuthenticated),
    disconnect,
  }
}
