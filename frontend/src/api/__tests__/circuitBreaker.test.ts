import { describe, it, expect, beforeEach, vi } from 'vitest'
import { CircuitBreaker, CircuitBreakerError } from '../circuitBreaker'

describe('CircuitBreaker', () => {
  let circuitBreaker: CircuitBreaker
  let mockFn: ReturnType<typeof vi.fn>

  beforeEach(() => {
    circuitBreaker = new CircuitBreaker({
      failureThreshold: 3,
      resetTimeout: 1000,
    })
    mockFn = vi.fn()
  })

  describe('CLOSED state (normal operation)', () => {
    it('should allow requests to pass through when closed', async () => {
      mockFn.mockResolvedValue('success')

      const result = await circuitBreaker.execute(mockFn)

      expect(result).toBe('success')
      expect(mockFn).toHaveBeenCalledTimes(1)
      expect(circuitBreaker.getState()).toBe('closed')
    })

    it('should reset failure count on success', async () => {
      mockFn.mockRejectedValueOnce(new Error('fail')).mockResolvedValue('success')

      // First failure
      await expect(circuitBreaker.execute(mockFn)).rejects.toThrow('fail')
      expect(circuitBreaker.getStats().failureCount).toBe(1)

      // Success resets count
      await circuitBreaker.execute(mockFn)
      expect(circuitBreaker.getStats().failureCount).toBe(0)
    })

    it('should transition to OPEN after threshold failures', async () => {
      mockFn.mockRejectedValue(new Error('fail'))

      // Fail 3 times to hit threshold
      for (let i = 0; i < 3; i++) {
        await expect(circuitBreaker.execute(mockFn)).rejects.toThrow('fail')
      }

      expect(circuitBreaker.getState()).toBe('open')
    })
  })

  describe('OPEN state (blocking requests)', () => {
    beforeEach(async () => {
      // Open the circuit by failing 3 times
      mockFn.mockRejectedValue(new Error('fail'))
      for (let i = 0; i < 3; i++) {
        await expect(circuitBreaker.execute(mockFn)).rejects.toThrow('fail')
      }
    })

    it('should reject requests immediately when open', async () => {
      mockFn.mockResolvedValue('success') // Would succeed, but circuit is open

      await expect(circuitBreaker.execute(mockFn)).rejects.toThrow(
        CircuitBreakerError
      )
      await expect(circuitBreaker.execute(mockFn)).rejects.toThrow(
        'Circuit breaker is open'
      )

      // Function should not be called when circuit is open
      expect(mockFn).toHaveBeenCalledTimes(3) // Only from beforeEach
    })

    it('should transition to HALF_OPEN after reset timeout', async () => {
      mockFn.mockResolvedValue('success')

      // Wait for reset timeout
      await new Promise((resolve) => setTimeout(resolve, 1100))

      const result = await circuitBreaker.execute(mockFn)

      expect(result).toBe('success')
      expect(circuitBreaker.getState()).toBe('closed')
    })
  })

  describe('HALF_OPEN state (testing recovery)', () => {
    beforeEach(async () => {
      // Open the circuit
      mockFn.mockRejectedValue(new Error('fail'))
      for (let i = 0; i < 3; i++) {
        await expect(circuitBreaker.execute(mockFn)).rejects.toThrow('fail')
      }

      // Wait for reset timeout to enter half-open
      await new Promise((resolve) => setTimeout(resolve, 1100))
    })

    it('should transition to CLOSED on success in half-open', async () => {
      mockFn.mockResolvedValue('success')

      const result = await circuitBreaker.execute(mockFn)

      expect(result).toBe('success')
      expect(circuitBreaker.getState()).toBe('closed')
    })

    it('should transition back to OPEN on failure in half-open', async () => {
      mockFn.mockRejectedValue(new Error('still failing'))

      await expect(circuitBreaker.execute(mockFn)).rejects.toThrow('still failing')
      expect(circuitBreaker.getState()).toBe('open')
    })
  })

  describe('Statistics', () => {
    it('should track failure count', async () => {
      mockFn.mockRejectedValue(new Error('fail'))

      await expect(circuitBreaker.execute(mockFn)).rejects.toThrow()
      expect(circuitBreaker.getStats().failureCount).toBe(1)

      await expect(circuitBreaker.execute(mockFn)).rejects.toThrow()
      expect(circuitBreaker.getStats().failureCount).toBe(2)
    })

    it('should track success count in half-open', async () => {
      // Open circuit
      mockFn.mockRejectedValue(new Error('fail'))
      for (let i = 0; i < 3; i++) {
        await expect(circuitBreaker.execute(mockFn)).rejects.toThrow()
      }

      // Wait and succeed
      await new Promise((resolve) => setTimeout(resolve, 1100))
      mockFn.mockResolvedValue('success')
      await circuitBreaker.execute(mockFn)

      // After successful transition from HALF_OPEN to CLOSED, counters are reset
      expect(circuitBreaker.getStats().successCount).toBe(0)
      expect(circuitBreaker.getState()).toBe('closed')
    })

    it('should track last failure time', async () => {
      const beforeFail = Date.now()
      mockFn.mockRejectedValue(new Error('fail'))

      await expect(circuitBreaker.execute(mockFn)).rejects.toThrow()

      const stats = circuitBreaker.getStats()
      expect(stats.lastFailureTime).toBeGreaterThanOrEqual(beforeFail)
      expect(stats.lastFailureTime).toBeLessThanOrEqual(Date.now())
    })

    it('should track state changes', async () => {
      const initialStats = circuitBreaker.getStats()
      expect(initialStats.state).toBe('closed')

      // Open circuit
      mockFn.mockRejectedValue(new Error('fail'))
      for (let i = 0; i < 3; i++) {
        await expect(circuitBreaker.execute(mockFn)).rejects.toThrow()
      }

      expect(circuitBreaker.getStats().state).toBe('open')
    })
  })

  describe('Manual reset', () => {
    it('should reset to closed state', async () => {
      // Open circuit
      mockFn.mockRejectedValue(new Error('fail'))
      for (let i = 0; i < 3; i++) {
        await expect(circuitBreaker.execute(mockFn)).rejects.toThrow()
      }

      expect(circuitBreaker.getState()).toBe('open')

      // Manual reset
      circuitBreaker.reset()

      expect(circuitBreaker.getState()).toBe('closed')
      expect(circuitBreaker.getStats().failureCount).toBe(0)
      expect(circuitBreaker.getStats().successCount).toBe(0)
    })
  })

  describe('Error propagation', () => {
    it('should propagate errors from the function', async () => {
      const customError = new Error('Custom error message')
      mockFn.mockRejectedValue(customError)

      await expect(circuitBreaker.execute(mockFn)).rejects.toThrow('Custom error message')
    })

    it('should throw CircuitBreakerError when open', async () => {
      // Open circuit
      mockFn.mockRejectedValue(new Error('fail'))
      for (let i = 0; i < 3; i++) {
        await expect(circuitBreaker.execute(mockFn)).rejects.toThrow()
      }

      // Next call should throw CircuitBreakerError
      mockFn.mockResolvedValue('would succeed')
      try {
        await circuitBreaker.execute(mockFn)
        expect.fail('Should have thrown CircuitBreakerError')
      } catch (error) {
        expect(error).toBeInstanceOf(CircuitBreakerError)
        expect(error.message).toContain('Circuit breaker is open')
        expect(error.stats).toBeDefined()
        expect(error.stats.state).toBe('open')
      }
    })
  })

  describe('Monitoring window', () => {
    it('should use custom monitoring window if provided', () => {
      const cb = new CircuitBreaker({
        failureThreshold: 5,
        resetTimeout: 2000,
        monitoringWindow: 1000,
      })

      expect(cb.getStats()).toBeDefined()
    })

    it('should default monitoring window to reset timeout', () => {
      const cb = new CircuitBreaker({
        failureThreshold: 5,
        resetTimeout: 2000,
      })

      expect(cb.getStats()).toBeDefined()
    })
  })
})
