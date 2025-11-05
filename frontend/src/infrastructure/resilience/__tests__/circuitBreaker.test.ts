/**
 * Circuit Breaker Tests
 *
 * Comprehensive unit tests for the CircuitBreaker implementation
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { CircuitBreaker, CircuitBreakerError, CircuitState } from '../circuitBreaker'

describe('CircuitBreaker', () => {
  let circuitBreaker: CircuitBreaker

  beforeEach(() => {
    circuitBreaker = new CircuitBreaker({
      failureThreshold: 3,
      resetTimeout: 1000,
    })
    vi.clearAllMocks()
  })

  describe('Initial State', () => {
    it('should start in CLOSED state', () => {
      expect(circuitBreaker.getState()).toBe('closed')
    })

    it('should have zero failures initially', () => {
      const stats = circuitBreaker.getStats()
      expect(stats.failureCount).toBe(0)
      expect(stats.successCount).toBe(0)
      expect(stats.lastFailureTime).toBeNull()
    })
  })

  describe('CLOSED State', () => {
    it('should execute function successfully', async () => {
      const fn = vi.fn().mockResolvedValue('success')
      const result = await circuitBreaker.execute(fn)

      expect(result).toBe('success')
      expect(fn).toHaveBeenCalledTimes(1)
      expect(circuitBreaker.getState()).toBe('closed')
    })

    it('should remain closed after successful execution', async () => {
      const fn = vi.fn().mockResolvedValue('success')

      await circuitBreaker.execute(fn)
      await circuitBreaker.execute(fn)
      await circuitBreaker.execute(fn)

      expect(circuitBreaker.getState()).toBe('closed')
      const stats = circuitBreaker.getStats()
      expect(stats.failureCount).toBe(0)
    })

    it('should transition to OPEN after threshold failures', async () => {
      const fn = vi.fn().mockRejectedValue(new Error('test error'))

      // First 2 failures - should stay closed
      await expect(circuitBreaker.execute(fn)).rejects.toThrow('test error')
      await expect(circuitBreaker.execute(fn)).rejects.toThrow('test error')
      expect(circuitBreaker.getState()).toBe('closed')

      // 3rd failure - should open circuit
      await expect(circuitBreaker.execute(fn)).rejects.toThrow('test error')
      expect(circuitBreaker.getState()).toBe('open')
    })

    it('should reset failure count after success', async () => {
      const successFn = vi.fn().mockResolvedValue('success')
      const failFn = vi.fn().mockRejectedValue(new Error('error'))

      // 2 failures
      await expect(circuitBreaker.execute(failFn)).rejects.toThrow()
      await expect(circuitBreaker.execute(failFn)).rejects.toThrow()

      // Success should reset counter
      await circuitBreaker.execute(successFn)

      const stats = circuitBreaker.getStats()
      expect(stats.failureCount).toBe(0)
      expect(circuitBreaker.getState()).toBe('closed')
    })
  })

  describe('OPEN State', () => {
    beforeEach(async () => {
      // Trigger circuit to open
      const fn = vi.fn().mockRejectedValue(new Error('error'))
      for (let i = 0; i < 3; i++) {
        await expect(circuitBreaker.execute(fn)).rejects.toThrow()
      }
      expect(circuitBreaker.getState()).toBe('open')
    })

    it('should reject requests immediately', async () => {
      const fn = vi.fn().mockResolvedValue('success')

      await expect(circuitBreaker.execute(fn)).rejects.toThrow(CircuitBreakerError)
      expect(fn).not.toHaveBeenCalled()
    })

    it('should include stats in error', async () => {
      const fn = vi.fn().mockResolvedValue('success')

      try {
        await circuitBreaker.execute(fn)
        expect.fail('Should have thrown')
      } catch (error: any) {
        expect(error).toBeInstanceOf(CircuitBreakerError)
        expect(error.stats).toBeDefined()
        expect(error.stats.state).toBe('open')
      }
    })

    it('should transition to HALF_OPEN after reset timeout', async () => {
      const fn = vi.fn().mockResolvedValue('success')

      // Wait for reset timeout
      await new Promise((resolve) => setTimeout(resolve, 1100))

      // Should transition to half-open and execute
      const result = await circuitBreaker.execute(fn)
      expect(result).toBe('success')
      expect(circuitBreaker.getState()).toBe('closed')
    })
  })

  describe('HALF_OPEN State', () => {
    beforeEach(async () => {
      // Open circuit
      const failFn = vi.fn().mockRejectedValue(new Error('error'))
      for (let i = 0; i < 3; i++) {
        await expect(circuitBreaker.execute(failFn)).rejects.toThrow()
      }

      // Wait for reset timeout to enter half-open
      await new Promise((resolve) => setTimeout(resolve, 1100))
    })

    it('should transition to CLOSED on success', async () => {
      const fn = vi.fn().mockResolvedValue('success')

      const result = await circuitBreaker.execute(fn)

      expect(result).toBe('success')
      expect(circuitBreaker.getState()).toBe('closed')
    })

    it('should transition to OPEN on failure', async () => {
      const fn = vi.fn().mockRejectedValue(new Error('still failing'))

      await expect(circuitBreaker.execute(fn)).rejects.toThrow('still failing')

      expect(circuitBreaker.getState()).toBe('open')
    })

    it('should reset counters when transitioning to CLOSED', async () => {
      const fn = vi.fn().mockResolvedValue('success')

      await circuitBreaker.execute(fn)

      const stats = circuitBreaker.getStats()
      expect(stats.failureCount).toBe(0)
      expect(stats.successCount).toBe(0)
      expect(circuitBreaker.getState()).toBe('closed')
    })
  })

  describe('Statistics', () => {
    it('should track failure count', async () => {
      const fn = vi.fn().mockRejectedValue(new Error('error'))

      await expect(circuitBreaker.execute(fn)).rejects.toThrow()
      await expect(circuitBreaker.execute(fn)).rejects.toThrow()

      const stats = circuitBreaker.getStats()
      expect(stats.failureCount).toBe(2)
    })

    it('should track success count', async () => {
      const fn = vi.fn().mockResolvedValue('success')

      await circuitBreaker.execute(fn)
      await circuitBreaker.execute(fn)

      const stats = circuitBreaker.getStats()
      expect(stats.successCount).toBe(2)
    })

    it('should track last failure time', async () => {
      const fn = vi.fn().mockRejectedValue(new Error('error'))
      const beforeTime = Date.now()

      await expect(circuitBreaker.execute(fn)).rejects.toThrow()

      const stats = circuitBreaker.getStats()
      expect(stats.lastFailureTime).toBeGreaterThanOrEqual(beforeTime)
      expect(stats.lastFailureTime).toBeLessThanOrEqual(Date.now())
    })

    it('should track state change time', async () => {
      const beforeTime = Date.now()
      const stats = circuitBreaker.getStats()

      expect(stats.lastStateChange).toBeGreaterThanOrEqual(beforeTime)
      expect(stats.lastStateChange).toBeLessThanOrEqual(Date.now())
    })
  })

  describe('Reset', () => {
    it('should reset circuit to CLOSED state', async () => {
      // Open circuit
      const fn = vi.fn().mockRejectedValue(new Error('error'))
      for (let i = 0; i < 3; i++) {
        await expect(circuitBreaker.execute(fn)).rejects.toThrow()
      }
      expect(circuitBreaker.getState()).toBe('open')

      // Reset
      circuitBreaker.reset()

      expect(circuitBreaker.getState()).toBe('closed')
      const stats = circuitBreaker.getStats()
      expect(stats.failureCount).toBe(0)
      expect(stats.successCount).toBe(0)
    })
  })
})
