/**
 * WebSocket Store Tests
 *
 * Tests for the Zustand-based WebSocket store.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { useWebSocketStore, WebSocketEvent, WebSocketMessage } from '../websocketStore'
import { useAuthStore } from '../authStore'

// Mock WebSocket
class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  readyState = MockWebSocket.CONNECTING
  url: string
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null

  sentMessages: string[] = []

  constructor(url: string) {
    this.url = url
    // Simulate async connection
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN
      if (this.onopen) {
        this.onopen(new Event('open'))
      }
    }, 0)
  }

  send(data: string): void {
    this.sentMessages.push(data)
  }

  close(code?: number, reason?: string): void {
    this.readyState = MockWebSocket.CLOSED
    if (this.onclose) {
      this.onclose(new CloseEvent('close', { code: code || 1000, reason: reason || '' }))
    }
  }

  // Helper to simulate receiving a message
  simulateMessage(data: WebSocketMessage): void {
    if (this.onmessage) {
      this.onmessage(new MessageEvent('message', { data: JSON.stringify(data) }))
    }
  }

  // Helper to simulate an error
  simulateError(): void {
    if (this.onerror) {
      this.onerror(new Event('error'))
    }
  }
}

describe('websocketStore', () => {
  beforeEach(() => {
    vi.useFakeTimers()

    // Mock global WebSocket
    ;(globalThis as typeof globalThis & { WebSocket: typeof WebSocket }).WebSocket = MockWebSocket as unknown as typeof WebSocket

    // Reset stores
    useWebSocketStore.setState({
      ws: null,
      isConnected: false,
      isConnecting: false,
      error: null,
      reconnectAttempt: 0,
      events: [],
      subscriptions: new Set(),
      config: {
        url: 'ws://localhost/api/v2/events/stream',
        reconnectAttempts: 10,
        initialReconnectDelay: 1000,
        maxReconnectDelay: 30000,
      },
    })

    useAuthStore.setState({
      isAuthenticated: false,
      isLoading: false,
      error: null,
      lastAuthTime: null,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    const state = useWebSocketStore.getState()
    if (state.ws) {
      state.disconnect()
    }
  })

  describe('initial state', () => {
    it('should have correct initial state', () => {
      const state = useWebSocketStore.getState()

      expect(state.ws).toBe(null)
      expect(state.isConnected).toBe(false)
      expect(state.isConnecting).toBe(false)
      expect(state.error).toBe(null)
      expect(state.reconnectAttempt).toBe(0)
      expect(state.events).toEqual([])
      expect(state.subscriptions.size).toBe(0)
    })
  })

  describe('connect', () => {
    it('should not connect if not authenticated', () => {
      const state = useWebSocketStore.getState()
      state.connect(false)

      expect(state.ws).toBe(null)
      expect(useWebSocketStore.getState().error).toBe('Not authenticated')
    })

    it('should create WebSocket connection when authenticated', async () => {
      const state = useWebSocketStore.getState()
      state.connect(true)

      expect(useWebSocketStore.getState().isConnecting).toBe(true)

      // Wait for connection to open
      await vi.runAllTimersAsync()

      const updatedState = useWebSocketStore.getState()
      expect(updatedState.ws).not.toBe(null)
      expect(updatedState.isConnected).toBe(true)
      expect(updatedState.isConnecting).toBe(false)
      expect(updatedState.error).toBe(null)
    })

    it('should close existing connection before creating new one', async () => {
      const state = useWebSocketStore.getState()

      // Create first connection
      state.connect(true)
      await vi.runAllTimersAsync()

      const firstWs = useWebSocketStore.getState().ws as unknown as MockWebSocket
      expect(firstWs).not.toBe(null)
      expect(firstWs.readyState).toBe(MockWebSocket.OPEN)

      // Create second connection
      state.connect(true)
      await vi.runAllTimersAsync()

      // First connection should be closed
      expect(firstWs.readyState).toBe(MockWebSocket.CLOSED)
    })

    it('should send pending subscriptions after connection opens', async () => {
      const state = useWebSocketStore.getState()

      // Add subscriptions before connecting
      state.subscribe('execution.started')
      state.subscribe('execution.completed')

      // Connect
      state.connect(true)
      await vi.runAllTimersAsync()

      const ws = useWebSocketStore.getState().ws as unknown as unknown as MockWebSocket
      expect(ws.sentMessages.length).toBe(2)
      expect(ws.sentMessages).toContainEqual(
        JSON.stringify({ type: 'subscribe', event_type: 'execution.started' })
      )
      expect(ws.sentMessages).toContainEqual(
        JSON.stringify({ type: 'subscribe', event_type: 'execution.completed' })
      )
    })
  })

  describe('disconnect', () => {
    it('should close WebSocket and reset state', async () => {
      const state = useWebSocketStore.getState()

      // Connect first
      state.connect(true)
      await vi.runAllTimersAsync()

      expect(useWebSocketStore.getState().isConnected).toBe(true)

      // Disconnect
      state.disconnect()

      const updatedState = useWebSocketStore.getState()
      expect(updatedState.ws).toBe(null)
      expect(updatedState.isConnected).toBe(false)
      expect(updatedState.isConnecting).toBe(false)
      expect(updatedState.error).toBe(null)
      expect(updatedState.events).toEqual([])
      expect(updatedState.reconnectAttempt).toBe(0)
    })

    it('should clear event handlers to prevent memory leaks', async () => {
      const state = useWebSocketStore.getState()

      state.connect(true)
      await vi.runAllTimersAsync()

      const ws = useWebSocketStore.getState().ws as unknown as MockWebSocket

      expect(ws.onopen).not.toBe(null)
      expect(ws.onmessage).not.toBe(null)
      expect(ws.onerror).not.toBe(null)
      expect(ws.onclose).not.toBe(null)

      state.disconnect()

      expect(ws.onopen).toBe(null)
      expect(ws.onmessage).toBe(null)
      expect(ws.onerror).toBe(null)
      expect(ws.onclose).toBe(null)
    })
  })

  describe('message handling', () => {
    it('should add received events to buffer', async () => {
      const state = useWebSocketStore.getState()
      state.connect(true)
      await vi.runAllTimersAsync()

      const ws = useWebSocketStore.getState().ws as unknown as MockWebSocket

      // Simulate message
      ws.simulateMessage({
        type: 'execution.started',
        data: { id: '123' },
        timestamp: '2025-01-01T00:00:00Z',
      })

      const updatedState = useWebSocketStore.getState()
      expect(updatedState.events.length).toBe(1)
      expect(updatedState.events[0].type).toBe('execution.started')
      expect(updatedState.events[0].data).toEqual({ id: '123' })
    })

    it('should limit events buffer to 100 items', async () => {
      const state = useWebSocketStore.getState()
      state.connect(true)
      await vi.runAllTimersAsync()

      const ws = useWebSocketStore.getState().ws as unknown as MockWebSocket

      // Send 150 messages
      for (let i = 0; i < 150; i++) {
        ws.simulateMessage({
          type: 'test.event',
          data: { count: i },
          timestamp: new Date().toISOString(),
        })
      }

      const updatedState = useWebSocketStore.getState()
      expect(updatedState.events.length).toBe(100)
      // Should keep most recent events (149, 148, ..., 50)
      expect(updatedState.events[0].data).toEqual({ count: 149 })
    })

    it('should ignore connected messages', async () => {
      const state = useWebSocketStore.getState()
      state.connect(true)
      await vi.runAllTimersAsync()

      const ws = useWebSocketStore.getState().ws as unknown as MockWebSocket

      ws.simulateMessage({ type: 'connected' })

      expect(useWebSocketStore.getState().events.length).toBe(0)
    })

    it('should ignore flow_control messages', async () => {
      const state = useWebSocketStore.getState()
      state.connect(true)
      await vi.runAllTimersAsync()

      const ws = useWebSocketStore.getState().ws as unknown as MockWebSocket

      ws.simulateMessage({ type: 'flow_control', message: 'Slow down' })

      expect(useWebSocketStore.getState().events.length).toBe(0)
    })

    it('should close connection on authentication error', async () => {
      const state = useWebSocketStore.getState()
      state.connect(true)
      await vi.runAllTimersAsync()

      const ws = useWebSocketStore.getState().ws as unknown as MockWebSocket

      ws.simulateMessage({
        type: 'error',
        message: 'Authentication failed',
      })

      // Should close with 4001 code
      expect(ws.readyState).toBe(MockWebSocket.CLOSED)
    })
  })

  describe('subscriptions', () => {
    it('should add subscription and send immediately if connected', async () => {
      const state = useWebSocketStore.getState()
      state.connect(true)
      await vi.runAllTimersAsync()

      const ws = useWebSocketStore.getState().ws as unknown as MockWebSocket

      state.subscribe('execution.started')

      const updatedState = useWebSocketStore.getState()
      expect(updatedState.subscriptions.has('execution.started')).toBe(true)
      expect(ws.sentMessages).toContainEqual(
        JSON.stringify({ type: 'subscribe', event_type: 'execution.started' })
      )
    })

    it('should remove subscription', async () => {
      const state = useWebSocketStore.getState()
      state.connect(true)
      await vi.runAllTimersAsync()

      state.subscribe('execution.started')
      expect(useWebSocketStore.getState().subscriptions.has('execution.started')).toBe(true)

      state.unsubscribe('execution.started')

      const updatedState = useWebSocketStore.getState()
      expect(updatedState.subscriptions.has('execution.started')).toBe(false)
    })
  })

  describe('reconnection', () => {
    it('should attempt reconnection on connection loss', async () => {
      // Set auth to authenticated
      useAuthStore.getState().setAuthenticated(true)

      const state = useWebSocketStore.getState()
      state.connect(true)
      await vi.runAllTimersAsync()

      const ws = useWebSocketStore.getState().ws as unknown as MockWebSocket

      // Simulate connection loss
      ws.close(1006, 'Connection lost')

      // Should schedule reconnection
      expect(useWebSocketStore.getState().reconnectAttempt).toBe(1)

      // Advance timer to trigger reconnection
      await vi.advanceTimersByTimeAsync(1000)

      // Should have new connection
      const newState = useWebSocketStore.getState()
      expect(newState.ws).not.toBe(null)
      expect(newState.ws).not.toBe(ws) // Different instance
    })

    it('should not reconnect if user logged out', async () => {
      // Set auth to authenticated
      useAuthStore.getState().setAuthenticated(true)

      const state = useWebSocketStore.getState()
      state.connect(true)
      await vi.runAllTimersAsync()

      const ws = useWebSocketStore.getState().ws as unknown as MockWebSocket

      // Simulate connection loss
      ws.close(1006, 'Connection lost')

      // User logs out before reconnection
      useAuthStore.getState().setAuthenticated(false)

      // Advance timer to trigger reconnection
      await vi.advanceTimersByTimeAsync(1000)

      // Should not reconnect
      const newState = useWebSocketStore.getState()
      expect(newState.isConnected).toBe(false)
    })

    it('should not reconnect on unauthorized close code', async () => {
      const state = useWebSocketStore.getState()
      state.connect(true)
      await vi.runAllTimersAsync()

      const ws = useWebSocketStore.getState().ws as unknown as MockWebSocket

      // Simulate unauthorized close
      ws.close(4001, 'Unauthorized')

      // Should not schedule reconnection
      expect(useWebSocketStore.getState().error).toBe('Unauthorized - authentication required')
      expect(useWebSocketStore.getState().reconnectAttempt).toBe(0)
    })

    it('should use exponential backoff for reconnection', async () => {
      useAuthStore.getState().setAuthenticated(true)

      const state = useWebSocketStore.getState()
      state.connect(true)
      await vi.runAllTimersAsync()

      // Simulate multiple connection losses
      for (let i = 0; i < 3; i++) {
        const ws = useWebSocketStore.getState().ws as unknown as MockWebSocket
        ws.close(1006, 'Connection lost')

        // Expected delays: 1s, 2s, 4s
        const expectedDelay = 1000 * Math.pow(2, i)
        await vi.advanceTimersByTimeAsync(expectedDelay)
      }

      expect(useWebSocketStore.getState().reconnectAttempt).toBe(3)
    })

    it('should stop reconnecting after max attempts', async () => {
      useAuthStore.getState().setAuthenticated(true)

      const state = useWebSocketStore.getState()

      // Set max attempts to 3 for testing
      state.config.reconnectAttempts = 3
      state.connect(true)
      await vi.runAllTimersAsync()

      // Simulate 3 connection losses
      for (let i = 0; i < 3; i++) {
        const ws = useWebSocketStore.getState().ws as unknown as MockWebSocket
        ws.close(1006, 'Connection lost')
        const delay = 1000 * Math.pow(2, i)
        await vi.advanceTimersByTimeAsync(delay)
      }

      // Final close should not trigger reconnection
      const ws = useWebSocketStore.getState().ws as unknown as MockWebSocket
      ws.close(1006, 'Connection lost')

      expect(useWebSocketStore.getState().error).toBe('Max reconnection attempts reached')
    })
  })

  describe('clearEvents', () => {
    it('should clear all events', async () => {
      const state = useWebSocketStore.getState()
      state.connect(true)
      await vi.runAllTimersAsync()

      const ws = useWebSocketStore.getState().ws as unknown as MockWebSocket

      // Add some events
      ws.simulateMessage({ type: 'test.event', data: { id: 1 } })
      ws.simulateMessage({ type: 'test.event', data: { id: 2 } })

      expect(useWebSocketStore.getState().events.length).toBe(2)

      state.clearEvents()

      expect(useWebSocketStore.getState().events.length).toBe(0)
    })
  })
})
