import { create } from 'zustand'
import { useAuthStore } from './authStore'

/**
 * WebSocket Message Types
 */
export interface WebSocketMessage {
  type: string
  data?: unknown
  timestamp?: string
  message?: string
  event_type?: string
}

/**
 * WebSocket Event Interface
 */
export interface WebSocketEvent {
  type: string
  data: unknown
  timestamp: string
}

/**
 * WebSocket Configuration
 */
export interface WebSocketConfig {
  url?: string
  reconnectAttempts?: number
  initialReconnectDelay?: number
  maxReconnectDelay?: number
}

/**
 * WebSocket State Interface
 */
interface WebSocketState {
  // Connection state
  ws: WebSocket | null
  isConnected: boolean
  isConnecting: boolean
  error: string | null
  reconnectAttempt: number

  // Event buffer (last 100 events)
  events: WebSocketEvent[]

  // Subscriptions
  subscriptions: Set<string>

  // Config
  config: Required<WebSocketConfig>

  // Actions
  connect: (isAuthenticated: boolean) => void
  disconnect: () => void
  subscribe: (eventType: string) => void
  unsubscribe: (eventType: string) => void
  subscribeToWorkflowRun: (workflowRunId: string, eventTypes?: string[]) => void
  unsubscribeFromWorkflowRun: (workflowRunId: string) => void
  clearEvents: () => void
  reconnect: () => void
}

const DEFAULT_CONFIG: Required<WebSocketConfig> = {
  url: typeof window !== 'undefined'
    ? (import.meta.env.VITE_WS_URL || `ws://${window.location.host}/api/v2/events/stream`)
    : 'ws://localhost/api/v2/events/stream',
  reconnectAttempts: 10,
  initialReconnectDelay: 1000, // 1 second
  maxReconnectDelay: 30000, // 30 seconds
}

// Singleton reconnect timeout
let reconnectTimeout: ReturnType<typeof setTimeout> | null = null

/**
 * Calculate exponential backoff delay for reconnection
 */
const calculateReconnectDelay = (attempt: number, config: Required<WebSocketConfig>): number => {
  // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s (max)
  return Math.min(
    config.initialReconnectDelay * Math.pow(2, attempt),
    config.maxReconnectDelay
  )
}

/**
 * Zustand Store for WebSocket Connection Management
 *
 * This store provides a centralized WebSocket singleton that:
 * - Manages a single WebSocket connection across the entire app
 * - Provides automatic reconnection with exponential backoff
 * - Buffers the last 100 events for component consumption
 * - Manages subscriptions to specific event types
 * - Uses httpOnly cookies for authentication (no token in URL)
 *
 * Connection Lifecycle:
 * 1. Call connect(isAuthenticated) to establish connection
 * 2. Subscribe to event types via subscribe(eventType)
 * 3. Connection automatically reconnects on disconnect (up to 10 attempts)
 * 4. On close code 4001 (Unauthorized), stops reconnecting and clears auth
 * 5. Call disconnect() to manually close connection
 *
 * Security:
 * - Uses httpOnly cookies for authentication (browser sends automatically)
 * - No token stored in state or localStorage
 * - Dispatches 'auth:unauthorized' event on 401 to clear auth state
 *
 * Example Usage:
 * ```tsx
 * const { isConnected, events, connect, subscribe } = useWebSocketStore()
 *
 * useEffect(() => {
 *   connect(isAuthenticated)
 *   subscribe('execution.started')
 *   subscribe('execution.completed')
 * }, [isAuthenticated])
 * ```
 */
export const useWebSocketStore = create<WebSocketState>((set, get) => ({
  ws: null,
  isConnected: false,
  isConnecting: false,
  error: null,
  reconnectAttempt: 0,
  events: [],
  subscriptions: new Set(),
  config: DEFAULT_CONFIG,

  connect: (isAuthenticated: boolean) => {
    const state = get()

    // Don't connect if not authenticated
    if (!isAuthenticated) {
      set({
        isConnecting: false,
        error: 'Not authenticated',
      })
      return
    }

    // Close existing connection if any (prevents resource leak)
    if (state.ws) {
      console.log('[WebSocket] Closing existing connection before reconnect')
      state.ws.close()
    }

    // Don't connect if already connecting
    if (state.isConnecting) {
      return
    }

    set({ isConnecting: true, error: null })

    try {
      // WebSocket will use cookies for authentication (browser sends them automatically)
      const ws = new WebSocket(state.config.url)

      ws.onopen = () => {
        console.log('[WebSocket] Connected')
        set({
          isConnected: true,
          isConnecting: false,
          error: null,
          reconnectAttempt: 0,
        })

        // Send any pending subscriptions
        const currentState = get()
        currentState.subscriptions.forEach((eventType) => {
          ws.send(
            JSON.stringify({
              type: 'subscribe',
              subscription_type: 'all_events',
              event_types: [eventType],  // Send as array, matching backend expectation
            })
          )
        })
      }

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data)

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

          // Handle authentication errors
          if (message.type === 'error' && message.message?.includes('auth')) {
            console.error('[WebSocket] Authentication error:', message.message)
            ws.close(4001, 'Authentication failed')
            return
          }

          // Add event to buffer
          set((state) => ({
            events: [
              {
                type: message.type,
                data: message.data || message,
                timestamp: message.timestamp || new Date().toISOString(),
              },
              ...state.events,
            ].slice(0, 100), // Keep last 100 events
          }))
        } catch (err) {
          console.error('[WebSocket] Failed to parse message:', err)
        }
      }

      ws.onerror = (event) => {
        console.error('[WebSocket] Error:', event)
        set({ error: 'WebSocket error occurred' })
      }

      ws.onclose = (event) => {
        console.log('[WebSocket] Disconnected:', event.code, event.reason)
        set({
          ws: null,
          isConnected: false,
          isConnecting: false,
        })

        // Handle unauthorized close (code 4001)
        if (event.code === 4001) {
          console.error('[WebSocket] Unauthorized - not reconnecting')
          set({ error: 'Unauthorized - authentication required' })

          // Trigger auth event to update auth state
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('auth:unauthorized'))
          }
          return
        }

        // Attempt reconnection if within limit
        const currentState = get()
        if (currentState.reconnectAttempt < currentState.config.reconnectAttempts) {
          const delay = calculateReconnectDelay(currentState.reconnectAttempt, currentState.config)
          console.log(
            `[WebSocket] Reconnecting in ${delay}ms (attempt ${currentState.reconnectAttempt + 1}/${currentState.config.reconnectAttempts})`
          )

          set((state) => ({ reconnectAttempt: state.reconnectAttempt + 1 }))

          // Clear existing timeout
          if (reconnectTimeout) {
            clearTimeout(reconnectTimeout)
          }

          // Schedule reconnection - CRITICAL: Use get() to access current auth state (not closure)
          reconnectTimeout = setTimeout(() => {
            // Check if user is still authenticated at reconnection time
            // This prevents race condition where user logged out during reconnection delay
            const isStillAuthenticated = useAuthStore.getState().isAuthenticated

            if (isStillAuthenticated) {
              const stateAtReconnect = get()
              stateAtReconnect.connect(true)
            } else {
              console.log('[WebSocket] User logged out during reconnection delay, aborting reconnect')
            }
          }, delay)
        } else {
          set({ error: 'Max reconnection attempts reached' })
        }
      }

      set({ ws })
    } catch (err) {
      console.error('[WebSocket] Connection error:', err)
      set({
        isConnecting: false,
        error: err instanceof Error ? err.message : 'Unknown error',
      })
    }
  },

  disconnect: () => {
    // Clear reconnect timeout
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout)
      reconnectTimeout = null
    }

    const state = get()
    if (state.ws) {
      // Remove all event handlers before closing to prevent memory leaks
      state.ws.onopen = null
      state.ws.onmessage = null
      state.ws.onerror = null
      state.ws.onclose = null

      // Close the connection
      if (state.ws.readyState === WebSocket.OPEN || state.ws.readyState === WebSocket.CONNECTING) {
        state.ws.close()
      }
    }

    set({
      ws: null,
      isConnected: false,
      isConnecting: false,
      error: null,
      events: [],
      reconnectAttempt: 0,
    })
  },

  subscribe: (eventType: string) => {
    set((state) => {
      const newSubscriptions = new Set(state.subscriptions)

      // Prevent duplicate subscriptions
      // This is especially important in development with React.StrictMode
      // which intentionally double-invokes effects
      if (newSubscriptions.has(eventType)) {
        return { subscriptions: state.subscriptions }
      }

      newSubscriptions.add(eventType)

      // If connected, send subscription immediately
      if (state.ws?.readyState === WebSocket.OPEN) {
        state.ws.send(
          JSON.stringify({
            type: 'subscribe',
            subscription_type: 'all_events',
            event_types: [eventType],  // Send as array, matching backend expectation
          })
        )
      }

      return { subscriptions: newSubscriptions }
    })
  },

  unsubscribe: (eventType: string) => {
    set((state) => {
      const newSubscriptions = new Set(state.subscriptions)
      newSubscriptions.delete(eventType)

      // If connected, send unsubscribe immediately
      if (state.ws?.readyState === WebSocket.OPEN) {
        state.ws.send(
          JSON.stringify({
            type: 'unsubscribe',
            subscription_type: 'all_events',
            event_types: [eventType],  // Send as array, matching backend expectation
          })
        )
      }

      return { subscriptions: newSubscriptions }
    })
  },

  clearEvents: () => {
    set({ events: [] })
  },

  subscribeToWorkflowRun: (workflowRunId: string, eventTypes?: string[]) => {
    const state = get()

    // If connected, send subscription immediately
    if (state.ws?.readyState === WebSocket.OPEN) {
      state.ws.send(
        JSON.stringify({
          type: 'subscribe',
          subscription_type: 'workflow_events',
          workflow_run_id: workflowRunId,
          event_types: eventTypes || [
            'WorkflowStarted',
            'WorkflowCompleted',
            'WorkflowFailed',
            'StageStarted',
            'StageCompleted',
            'StageFailed',
            'AgentExecutionStarted',
            'AgentExecutionCompleted',
            'AgentExecutionFailed',
          ],
        })
      )
      console.log(`[WebSocket] Subscribed to workflow run: ${workflowRunId}`)
    }
  },

  unsubscribeFromWorkflowRun: (workflowRunId: string) => {
    const state = get()

    // If connected, send unsubscribe immediately
    if (state.ws?.readyState === WebSocket.OPEN) {
      state.ws.send(
        JSON.stringify({
          type: 'unsubscribe',
          workflow_run_id: workflowRunId,
        })
      )
      console.log(`[WebSocket] Unsubscribed from workflow run: ${workflowRunId}`)
    }
  },

  reconnect: () => {
    const state = get()
    state.disconnect()
    // Note: isAuthenticated needs to be passed from the component
    // We'll handle this in the hook wrapper
  },
}))

/**
 * Cleanup on page unload
 */
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    useWebSocketStore.getState().disconnect()
  })
}
