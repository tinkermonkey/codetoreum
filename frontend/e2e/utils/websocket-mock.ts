/**
 * WebSocket Mock Utilities
 *
 * Helper functions for mocking WebSocket connections and events in E2E tests.
 */

import { Page } from '@playwright/test'

/**
 * WebSocket event for testing
 */
export interface MockWebSocketEvent {
  type: string
  data: any
  timestamp?: string
}

/**
 * Mock WebSocket connection
 *
 * This intercepts WebSocket creation and provides a mock implementation
 * that can send events programmatically during tests.
 */
export async function mockWebSocket(page: Page) {
  await page.addInitScript(() => {
    // Store original WebSocket
    const OriginalWebSocket = window.WebSocket

    // Mock WebSocket class
    class MockWebSocket extends EventTarget {
      public url: string
      public readyState: number = WebSocket.CONNECTING
      public protocol: string = ''
      public extensions: string = ''
      public bufferedAmount: number = 0
      public binaryType: BinaryType = 'blob'

      // Event handlers
      public onopen: ((event: Event) => void) | null = null
      public onclose: ((event: CloseEvent) => void) | null = null
      public onerror: ((event: Event) => void) | null = null
      public onmessage: ((event: MessageEvent) => void) | null = null

      // Store for programmatic control
      private static instances: MockWebSocket[] = []

      constructor(url: string | URL, protocols?: string | string[]) {
        super()
        this.url = url.toString()
        MockWebSocket.instances.push(this)

        // Simulate connection after a short delay
        setTimeout(() => {
          this.readyState = WebSocket.OPEN
          const event = new Event('open')
          this.dispatchEvent(event)
          if (this.onopen) this.onopen(event)
        }, 100)
      }

      send(data: string | ArrayBufferLike | Blob | ArrayBufferView): void {
        // Mock send - do nothing in tests
      }

      close(code?: number, reason?: string): void {
        this.readyState = WebSocket.CLOSED
        const event = new CloseEvent('close', { code, reason })
        this.dispatchEvent(event)
        if (this.onclose) this.onclose(event)
      }

      // Static methods for test control
      static getInstances(): MockWebSocket[] {
        return MockWebSocket.instances
      }

      static sendEvent(event: MockWebSocketEvent): void {
        const instances = MockWebSocket.getInstances()
        instances.forEach((ws) => {
          if (ws.readyState === WebSocket.OPEN) {
            const messageEvent = new MessageEvent('message', {
              data: JSON.stringify({
                type: event.type,
                data: event.data,
                timestamp: event.timestamp || new Date().toISOString(),
              }),
            })
            ws.dispatchEvent(messageEvent)
            if (ws.onmessage) ws.onmessage(messageEvent)
          }
        })
      }

      static clearInstances(): void {
        MockWebSocket.instances = []
      }

      // Required WebSocket constants
      static readonly CONNECTING = 0
      static readonly OPEN = 1
      static readonly CLOSING = 2
      static readonly CLOSED = 3
    }

    // Add constants to instance
    Object.defineProperties(MockWebSocket.prototype, {
      CONNECTING: { value: 0 },
      OPEN: { value: 1 },
      CLOSING: { value: 2 },
      CLOSED: { value: 3 },
    })

    // Expose mock control to window for test access
    ;(window as any).__mockWebSocket = {
      sendEvent: MockWebSocket.sendEvent.bind(MockWebSocket),
      getInstances: MockWebSocket.getInstances.bind(MockWebSocket),
      clearInstances: MockWebSocket.clearInstances.bind(MockWebSocket),
    }

    // Replace global WebSocket
    ;(window as any).WebSocket = MockWebSocket
  })
}

/**
 * Send a mock WebSocket event to all active connections
 */
export async function sendMockWebSocketEvent(page: Page, event: MockWebSocketEvent) {
  await page.evaluate((evt) => {
    ;(window as any).__mockWebSocket?.sendEvent(evt)
  }, event)
}

/**
 * Wait for WebSocket connection to be established
 */
export async function waitForMockWebSocketConnection(page: Page, timeout: number = 5000) {
  await page.waitForFunction(
    () => {
      const instances = (window as any).__mockWebSocket?.getInstances() || []
      return instances.some((ws: any) => ws.readyState === 1) // OPEN
    },
    { timeout }
  )
}

/**
 * Clear all WebSocket instances (cleanup)
 */
export async function clearMockWebSocketInstances(page: Page) {
  await page.evaluate(() => {
    ;(window as any).__mockWebSocket?.clearInstances()
  })
}

/**
 * Send a sequence of events with delays
 */
export async function sendEventSequence(
  page: Page,
  events: MockWebSocketEvent[],
  delayMs: number = 100
) {
  for (const event of events) {
    await sendMockWebSocketEvent(page, event)
    await page.waitForTimeout(delayMs)
  }
}
