/**
 * WebSocket Hook
 *
 * Provides real-time event streaming from the backend with automatic reconnection.
 *
 * Features:
 * - Automatic connection with token authentication
 * - Exponential backoff reconnection (up to 10 attempts)
 * - Close code 4001 (Unauthorized) prevents reconnection
 * - Event filtering and subscription management
 * - Connection status tracking
 */

import { useState, useEffect, useCallback, useRef } from 'react'

export interface WebSocketEvent {
  type: string
  data: any
  timestamp: string
}

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

const DEFAULT_CONFIG: Required<WebSocketConfig> = {
  url: import.meta.env.VITE_WS_URL || `ws://${window.location.host}/api/v2/events/stream`,
  reconnectAttempts: 10,
  initialReconnectDelay: 1000, // 1 second
  maxReconnectDelay: 30000, // 30 seconds
}

export function useWebSocket(token: string | null, config: WebSocketConfig = {}) {
  const fullConfig = { ...DEFAULT_CONFIG, ...config }
  const [state, setState] = useState<WebSocketState>({
    isConnected: false,
    isConnecting: false,
    error: null,
    events: [],
    reconnectAttempt: 0,
  })

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const shouldReconnectRef = useRef(true)
  const subscriptionsRef = useRef<Set<string>>(new Set())

  const calculateReconnectDelay = useCallback(
    (attempt: number) => {
      // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s (max)
      const delay = Math.min(
        fullConfig.initialReconnectDelay * Math.pow(2, attempt),
        fullConfig.maxReconnectDelay
      )
      return delay
    },
    [fullConfig.initialReconnectDelay, fullConfig.maxReconnectDelay]
  )

  const connect = useCallback(() => {
    if (!token) {
      setState((prev) => ({
        ...prev,
        isConnecting: false,
        error: 'No authentication token available',
      }))
      return
    }

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return // Already connected
    }

    setState((prev) => ({ ...prev, isConnecting: true, error: null }))

    try {
      // Add token as query parameter for WebSocket authentication
      const wsUrl = `${fullConfig.url}?token=${token}`
      const ws = new WebSocket(wsUrl)

      ws.onopen = () => {
        console.log('[WebSocket] Connected')
        setState((prev) => ({
          ...prev,
          isConnected: true,
          isConnecting: false,
          error: null,
          reconnectAttempt: 0,
        }))

        // Send any pending subscriptions
        subscriptionsRef.current.forEach((eventType) => {
          ws.send(
            JSON.stringify({
              type: 'subscribe',
              event_type: eventType,
            })
          )
        })
      }

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)

          // Handle connected message
          if (message.type === 'connected') {
            console.log('[WebSocket] Server acknowledged connection')
            return
          }

          // Handle flow control warnings
          if (message.type === 'flow_control') {
            console.warn('[WebSocket] Flow control warning:', message.message)
            return
          }

          // Add event to state
          setState((prev) => ({
            ...prev,
            events: [
              {
                type: message.type,
                data: message.data || message,
                timestamp: message.timestamp || new Date().toISOString(),
              },
              ...prev.events,
            ].slice(0, 100), // Keep last 100 events
          }))
        } catch (err) {
          console.error('[WebSocket] Failed to parse message:', err)
        }
      }

      ws.onerror = (event) => {
        console.error('[WebSocket] Error:', event)
        setState((prev) => ({
          ...prev,
          error: 'WebSocket error occurred',
        }))
      }

      ws.onclose = (event) => {
        console.log('[WebSocket] Disconnected:', event.code, event.reason)
        setState((prev) => ({
          ...prev,
          isConnected: false,
          isConnecting: false,
        }))

        wsRef.current = null

        // Handle unauthorized close (code 4001)
        if (event.code === 4001) {
          console.error('[WebSocket] Unauthorized - not reconnecting')
          shouldReconnectRef.current = false
          setState((prev) => ({
            ...prev,
            error: 'Unauthorized - invalid token',
          }))
          // Trigger auth event to clear token
          localStorage.removeItem('codetoreum_token')
          window.dispatchEvent(new CustomEvent('auth:unauthorized'))
          return
        }

        // Attempt reconnection if enabled and within limit
        if (shouldReconnectRef.current && state.reconnectAttempt < fullConfig.reconnectAttempts) {
          const delay = calculateReconnectDelay(state.reconnectAttempt)
          console.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${state.reconnectAttempt + 1}/${fullConfig.reconnectAttempts})`)

          setState((prev) => ({
            ...prev,
            reconnectAttempt: prev.reconnectAttempt + 1,
          }))

          reconnectTimeoutRef.current = setTimeout(() => {
            connect()
          }, delay)
        } else if (state.reconnectAttempt >= fullConfig.reconnectAttempts) {
          setState((prev) => ({
            ...prev,
            error: 'Max reconnection attempts reached',
          }))
        }
      }

      wsRef.current = ws
    } catch (err) {
      console.error('[WebSocket] Connection error:', err)
      setState((prev) => ({
        ...prev,
        isConnecting: false,
        error: err instanceof Error ? err.message : 'Unknown error',
      }))
    }
  }, [token, fullConfig.url, fullConfig.reconnectAttempts, calculateReconnectDelay, state.reconnectAttempt])

  const disconnect = useCallback(() => {
    shouldReconnectRef.current = false

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }

    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }

    setState({
      isConnected: false,
      isConnecting: false,
      error: null,
      events: [],
      reconnectAttempt: 0,
    })
  }, [])

  const subscribe = useCallback(
    (eventType: string) => {
      subscriptionsRef.current.add(eventType)

      // If connected, send subscription immediately
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(
          JSON.stringify({
            type: 'subscribe',
            event_type: eventType,
          })
        )
      }
    },
    []
  )

  const unsubscribe = useCallback((eventType: string) => {
    subscriptionsRef.current.delete(eventType)

    // If connected, send unsubscribe immediately
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: 'unsubscribe',
          event_type: eventType,
        })
      )
    }
  }, [])

  const clearEvents = useCallback(() => {
    setState((prev) => ({ ...prev, events: [] }))
  }, [])

  // Connect on mount if token is available
  useEffect(() => {
    if (token) {
      shouldReconnectRef.current = true
      connect()
    }

    return () => {
      disconnect()
    }
  }, [token, connect, disconnect])

  return {
    ...state,
    subscribe,
    unsubscribe,
    clearEvents,
    reconnect: connect,
    disconnect,
  }
}
