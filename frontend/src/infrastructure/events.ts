/**
 * Event System
 *
 * Type-safe event dispatching and handling for application events.
 * Provides a centralized event bus for decoupled component communication.
 */

/**
 * Application event types
 */
export enum AppEventType {
  // Authentication events
  AUTH_UNAUTHORIZED = 'auth:unauthorized',
  AUTH_TOKEN_EXPIRED = 'auth:token-expired',
  AUTH_LOGIN_SUCCESS = 'auth:login-success',
  AUTH_LOGOUT = 'auth:logout',

  // API events
  API_RATE_LIMITED = 'api:rate-limited',
  API_CIRCUIT_BREAKER_OPEN = 'api:circuit-breaker-open',
  API_CIRCUIT_BREAKER_CLOSED = 'api:circuit-breaker-closed',
  API_ERROR = 'api:error',

  // Network events
  NETWORK_ONLINE = 'network:online',
  NETWORK_OFFLINE = 'network:offline',
}

/**
 * Event payload types for each event
 */
export interface AppEventPayloads {
  [AppEventType.AUTH_UNAUTHORIZED]: { message: string; statusCode: number }
  [AppEventType.AUTH_TOKEN_EXPIRED]: { message: string }
  [AppEventType.AUTH_LOGIN_SUCCESS]: { userId: string }
  [AppEventType.AUTH_LOGOUT]: { reason?: string }
  [AppEventType.API_RATE_LIMITED]: { retryAfter?: number; message: string }
  [AppEventType.API_CIRCUIT_BREAKER_OPEN]: { failureCount: number }
  [AppEventType.API_CIRCUIT_BREAKER_CLOSED]: { recoveryTime: number }
  [AppEventType.API_ERROR]: { error: any; correlationId?: string }
  [AppEventType.NETWORK_ONLINE]: Record<string, never>
  [AppEventType.NETWORK_OFFLINE]: Record<string, never>
}

/**
 * Type-safe event handler function
 */
export type EventHandler<T extends AppEventType> = (
  payload: AppEventPayloads[T]
) => void | Promise<void>

/**
 * Event subscription handle for cleanup
 */
export interface EventSubscription {
  unsubscribe: () => void
}

/**
 * Central event bus for application events
 */
class EventBus {
  private handlers: Map<AppEventType, Set<EventHandler<any>>> = new Map()

  /**
   * Subscribe to an event
   */
  on<T extends AppEventType>(
    eventType: T,
    handler: EventHandler<T>
  ): EventSubscription {
    if (!this.handlers.has(eventType)) {
      this.handlers.set(eventType, new Set())
    }

    this.handlers.get(eventType)!.add(handler)

    return {
      unsubscribe: () => this.off(eventType, handler),
    }
  }

  /**
   * Unsubscribe from an event
   */
  off<T extends AppEventType>(eventType: T, handler: EventHandler<T>): void {
    const handlers = this.handlers.get(eventType)
    if (handlers) {
      handlers.delete(handler)
      if (handlers.size === 0) {
        this.handlers.delete(eventType)
      }
    }
  }

  /**
   * Subscribe to an event once
   */
  once<T extends AppEventType>(
    eventType: T,
    handler: EventHandler<T>
  ): EventSubscription {
    const wrappedHandler: EventHandler<T> = async (payload) => {
      this.off(eventType, wrappedHandler)
      await handler(payload)
    }

    return this.on(eventType, wrappedHandler)
  }

  /**
   * Dispatch an event to all subscribers
   */
  async emit<T extends AppEventType>(
    eventType: T,
    payload: AppEventPayloads[T]
  ): Promise<void> {
    const handlers = this.handlers.get(eventType)
    if (!handlers || handlers.size === 0) {
      return
    }

    // Execute all handlers concurrently
    const promises = Array.from(handlers).map((handler) =>
      Promise.resolve(handler(payload)).catch((error) => {
        console.error(`Error in event handler for ${eventType}:`, error)
      })
    )

    await Promise.all(promises)
  }

  /**
   * Clear all event handlers (useful for testing)
   */
  clear(): void {
    this.handlers.clear()
  }

  /**
   * Get count of handlers for an event (useful for testing)
   */
  getHandlerCount(eventType: AppEventType): number {
    return this.handlers.get(eventType)?.size ?? 0
  }
}

/**
 * Global event bus instance
 */
export const eventBus = new EventBus()

/**
 * Helper function to dispatch events
 */
export function dispatchEvent<T extends AppEventType>(
  eventType: T,
  payload: AppEventPayloads[T]
): Promise<void> {
  return eventBus.emit(eventType, payload)
}

/**
 * Helper function to subscribe to events
 */
export function subscribeToEvent<T extends AppEventType>(
  eventType: T,
  handler: EventHandler<T>
): EventSubscription {
  return eventBus.on(eventType, handler)
}

/**
 * Helper function to subscribe to events once
 */
export function subscribeOnce<T extends AppEventType>(
  eventType: T,
  handler: EventHandler<T>
): EventSubscription {
  return eventBus.once(eventType, handler)
}
