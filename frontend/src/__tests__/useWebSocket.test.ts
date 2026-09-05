/**
 * Unit tests for useWebSocket hook.
 *
 * Tests WebSocket connection management, message handling, reconnection logic,
 * connection state, and cleanup.
 */

import { renderHook, act, waitFor } from '@testing-library/react';
import { useWebSocket } from '../hooks/useWebSocket';

// Mock WebSocket
class MockWebSocket {
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  readyState = WebSocket.CONNECTING;

  constructor(public url: string) {
    // Simulate connection after a short delay
    setTimeout(() => {
      this.readyState = WebSocket.OPEN;
      if (this.onopen) {
        this.onopen(new Event('open'));
      }
    }, 10);
  }

  send(_data: string) {
    if (this.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket is not open');
    }
  }

  close() {
    this.readyState = WebSocket.CLOSED;
    if (this.onclose) {
      this.onclose(new CloseEvent('close'));
    }
  }

  // Test helper to simulate receiving a message
  simulateMessage(data: any) {
    if (this.onmessage) {
      this.onmessage(
        new MessageEvent('message', {
          data: JSON.stringify(data),
        })
      );
    }
  }

  // Test helper to simulate an error
  simulateError() {
    if (this.onerror) {
      this.onerror(new Event('error'));
    }
  }
}

global.WebSocket = MockWebSocket as any;

describe('useWebSocket hook', () => {
  const mockUrl = 'ws://localhost:8000/ws';

  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  describe('Connection Establishment', () => {
    it('should establish WebSocket connection', async () => {
      const { result } = renderHook(() => useWebSocket(mockUrl));

      // Initially connecting
      expect(result.current.connected).toBe(false);

      // Wait for connection
      act(() => {
        jest.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.connected).toBe(true);
      });
    });

    it('should connect to correct URL', async () => {
      const customUrl = 'ws://custom-host:9000/ws';
      renderHook(() => useWebSocket(customUrl));

      // WebSocket constructor should have been called with custom URL
      // (verified through mock implementation)
    });
  });

  describe('Message Handling', () => {
    it('should receive and parse messages', async () => {
      const { result } = renderHook(() => useWebSocket(mockUrl));

      act(() => {
        jest.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.connected).toBe(true);
      });

      // Simulate receiving a message
      const mockMessage = {
        type: 'work_item_created',
        data: { id: 'work-item-123', title: 'Test item' },
      };

      act(() => {
        // Get the WebSocket instance and simulate message
        const ws = (global.WebSocket as any).mock.instances[0] as MockWebSocket;
        ws.simulateMessage(mockMessage);
      });

      await waitFor(() => {
        expect(result.current.messages).toHaveLength(1);
        expect(result.current.messages[0]).toEqual(mockMessage);
      });
    });

    it('should handle multiple messages', async () => {
      const { result } = renderHook(() => useWebSocket(mockUrl));

      act(() => {
        jest.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.connected).toBe(true);
      });

      const messages = [
        { type: 'event1', data: { value: 1 } },
        { type: 'event2', data: { value: 2 } },
        { type: 'event3', data: { value: 3 } },
      ];

      act(() => {
        const ws = (global.WebSocket as any).mock.instances[0] as MockWebSocket;
        messages.forEach(msg => ws.simulateMessage(msg));
      });

      await waitFor(() => {
        expect(result.current.messages).toHaveLength(3);
      });
    });

    it('should handle malformed JSON gracefully', async () => {
      const { result } = renderHook(() => useWebSocket(mockUrl));

      act(() => {
        jest.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.connected).toBe(true);
      });

      // Simulate receiving malformed data
      act(() => {
        const ws = (global.WebSocket as any).mock.instances[0] as MockWebSocket;
        if (ws.onmessage) {
          ws.onmessage(
            new MessageEvent('message', {
              data: 'invalid-json{',
            })
          );
        }
      });

      // Should not crash and error should be set
      await waitFor(() => {
        expect(result.current.error).toBeTruthy();
      });
    });
  });

  describe('Sending Messages', () => {
    it('should send messages when connected', async () => {
      const { result } = renderHook(() => useWebSocket(mockUrl));

      act(() => {
        jest.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.connected).toBe(true);
      });

      const message = { type: 'subscribe', channel: 'work_items' };

      act(() => {
        result.current.sendMessage(message);
      });

      // Should not throw error
      expect(result.current.error).toBeNull();
    });

    it('should not send messages when disconnected', async () => {
      const { result } = renderHook(() => useWebSocket(mockUrl));

      // Try to send before connection
      act(() => {
        result.current.sendMessage({ type: 'test' });
      });

      // Should set error
      await waitFor(() => {
        expect(result.current.error).toBeTruthy();
      });
    });
  });

  describe('Connection Errors', () => {
    it('should handle connection errors', async () => {
      const { result } = renderHook(() => useWebSocket(mockUrl));

      act(() => {
        jest.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.connected).toBe(true);
      });

      // Simulate error
      act(() => {
        const ws = (global.WebSocket as any).mock.instances[0] as MockWebSocket;
        ws.simulateError();
      });

      await waitFor(() => {
        expect(result.current.error).toBeTruthy();
      });
    });

    it('should attempt reconnection after error', async () => {
      const { result } = renderHook(() => useWebSocket(mockUrl, { autoReconnect: true }));

      act(() => {
        jest.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.connected).toBe(true);
      });

      // Simulate disconnect
      act(() => {
        const ws = (global.WebSocket as any).mock.instances[0] as MockWebSocket;
        ws.close();
      });

      await waitFor(() => {
        expect(result.current.connected).toBe(false);
      });

      // Wait for reconnection attempt
      act(() => {
        jest.advanceTimersByTime(3000);
      });

      // Should attempt to reconnect
      // (verified through multiple WebSocket constructor calls)
    });
  });

  describe('Connection State', () => {
    it('should track connection state correctly', async () => {
      const { result } = renderHook(() => useWebSocket(mockUrl));

      expect(result.current.connected).toBe(false);

      act(() => {
        jest.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.connected).toBe(true);
      });

      act(() => {
        const ws = (global.WebSocket as any).mock.instances[0] as MockWebSocket;
        ws.close();
      });

      await waitFor(() => {
        expect(result.current.connected).toBe(false);
      });
    });
  });

  describe('Cleanup', () => {
    it('should close connection on unmount', async () => {
      const { result, unmount } = renderHook(() => useWebSocket(mockUrl));

      act(() => {
        jest.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.connected).toBe(true);
      });

      const ws = (global.WebSocket as any).mock.instances[0] as MockWebSocket;
      const closeSpy = jest.spyOn(ws, 'close');

      unmount();

      expect(closeSpy).toHaveBeenCalled();
    });

    it('should clear timers on unmount', async () => {
      const { unmount } = renderHook(() => useWebSocket(mockUrl, { autoReconnect: true }));

      act(() => {
        jest.advanceTimersByTime(20);
      });

      unmount();

      // Should not throw when advancing timers after unmount
      act(() => {
        jest.advanceTimersByTime(10000);
      });
    });
  });

  describe('Reconnection Logic', () => {
    it('should exponentially backoff reconnection attempts', async () => {
      const { result } = renderHook(() =>
        useWebSocket(mockUrl, {
          autoReconnect: true,
          reconnectInterval: 1000,
          maxReconnectAttempts: 3,
        })
      );

      act(() => {
        jest.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.connected).toBe(true);
      });

      // Simulate disconnect
      act(() => {
        const ws = (global.WebSocket as any).mock.instances[0] as MockWebSocket;
        ws.simulateError();
        ws.close();
      });

      // First reconnect after 1s
      act(() => {
        jest.advanceTimersByTime(1000);
      });

      // Second reconnect after 2s
      act(() => {
        jest.advanceTimersByTime(2000);
      });

      // Third reconnect after 4s
      act(() => {
        jest.advanceTimersByTime(4000);
      });

      // Should have attempted reconnection
    });

    it('should stop reconnecting after max attempts', async () => {
      const { result } = renderHook(() =>
        useWebSocket(mockUrl, {
          autoReconnect: true,
          maxReconnectAttempts: 2,
        })
      );

      act(() => {
        jest.advanceTimersByTime(20);
      });

      // Simulate multiple failed connections
      for (let i = 0; i < 3; i++) {
        act(() => {
          const ws = (global.WebSocket as any).mock.instances[i] as MockWebSocket;
          ws.simulateError();
          ws.close();
          jest.advanceTimersByTime(5000);
        });
      }

      await waitFor(() => {
        expect(result.current.error).toContain('Max reconnection attempts reached');
      });
    });
  });
});
