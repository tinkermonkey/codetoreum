/**
 * Unified Error Types
 *
 * Error types that align with backend error structures.
 * Provides consistent error handling across the application.
 */

/**
 * Standard API error response structure
 * Matches backend error format
 */
export interface ApiErrorResponse {
  error: {
    code: string
    message: string
    details?: Record<string, any>
    timestamp?: string
    path?: string
    correlationId?: string
  }
}

/**
 * Enhanced API error with metadata
 * Used internally in the frontend for error handling
 */
export interface ApiError {
  message: string
  statusCode?: number
  code?: string
  details?: Record<string, any>
  correlationId?: string
  timestamp?: string
  path?: string
  originalError?: any
}

/**
 * Error codes that match backend error classifications
 */
export enum ErrorCode {
  // Client errors (4xx)
  BAD_REQUEST = 'BAD_REQUEST',
  UNAUTHORIZED = 'UNAUTHORIZED',
  FORBIDDEN = 'FORBIDDEN',
  NOT_FOUND = 'NOT_FOUND',
  CONFLICT = 'CONFLICT',
  VALIDATION_ERROR = 'VALIDATION_ERROR',
  RATE_LIMITED = 'RATE_LIMITED',

  // Server errors (5xx)
  INTERNAL_ERROR = 'INTERNAL_ERROR',
  SERVICE_UNAVAILABLE = 'SERVICE_UNAVAILABLE',
  GATEWAY_TIMEOUT = 'GATEWAY_TIMEOUT',

  // Network errors
  NETWORK_ERROR = 'NETWORK_ERROR',
  TIMEOUT = 'TIMEOUT',
  CANCELLED = 'CANCELLED',

  // Circuit breaker
  CIRCUIT_BREAKER_OPEN = 'CIRCUIT_BREAKER_OPEN',

  // Unknown
  UNKNOWN = 'UNKNOWN',
}

/**
 * User-friendly error messages for different error types
 */
export const ErrorMessages: Record<ErrorCode, string> = {
  [ErrorCode.BAD_REQUEST]: 'Invalid request. Please check your input.',
  [ErrorCode.UNAUTHORIZED]: 'You need to sign in to continue.',
  [ErrorCode.FORBIDDEN]: "You don't have permission to access this resource.",
  [ErrorCode.NOT_FOUND]: 'The requested resource was not found.',
  [ErrorCode.CONFLICT]: 'This action conflicts with existing data.',
  [ErrorCode.VALIDATION_ERROR]: 'Please check the form for errors.',
  [ErrorCode.RATE_LIMITED]: 'Too many requests. Please wait a moment.',
  [ErrorCode.INTERNAL_ERROR]: 'An unexpected error occurred. Please try again.',
  [ErrorCode.SERVICE_UNAVAILABLE]: 'Service temporarily unavailable. Please try again later.',
  [ErrorCode.GATEWAY_TIMEOUT]: 'Request timed out. Please try again.',
  [ErrorCode.NETWORK_ERROR]: 'Network error. Please check your connection.',
  [ErrorCode.TIMEOUT]: 'Request timed out. Please try again.',
  [ErrorCode.CANCELLED]: 'Request was cancelled.',
  [ErrorCode.CIRCUIT_BREAKER_OPEN]: 'Service temporarily unavailable due to errors. Please wait.',
  [ErrorCode.UNKNOWN]: 'An unexpected error occurred.',
}

/**
 * Maps HTTP status codes to error codes
 */
export function mapStatusToErrorCode(status: number): ErrorCode {
  if (status === 400) return ErrorCode.BAD_REQUEST
  if (status === 401) return ErrorCode.UNAUTHORIZED
  if (status === 403) return ErrorCode.FORBIDDEN
  if (status === 404) return ErrorCode.NOT_FOUND
  if (status === 409) return ErrorCode.CONFLICT
  if (status === 422) return ErrorCode.VALIDATION_ERROR
  if (status === 429) return ErrorCode.RATE_LIMITED
  if (status === 500) return ErrorCode.INTERNAL_ERROR
  if (status === 502 || status === 503) return ErrorCode.SERVICE_UNAVAILABLE
  if (status === 504) return ErrorCode.GATEWAY_TIMEOUT
  if (status >= 400 && status < 500) return ErrorCode.BAD_REQUEST
  if (status >= 500) return ErrorCode.INTERNAL_ERROR
  return ErrorCode.UNKNOWN
}

/**
 * Creates a standardized ApiError from various error sources
 */
export function createApiError(
  error: any,
  defaultMessage = 'An error occurred'
): ApiError {
  // If it's already an ApiError, return it
  if (error && typeof error === 'object' && 'statusCode' in error) {
    return error as ApiError
  }

  // Handle axios error responses
  if (error?.response) {
    const { status, data } = error.response
    const errorCode = mapStatusToErrorCode(status)

    // If backend sent structured error
    if (data?.error) {
      return {
        message: data.error.message || ErrorMessages[errorCode],
        statusCode: status,
        code: data.error.code || errorCode,
        details: data.error.details,
        correlationId: data.error.correlationId,
        timestamp: data.error.timestamp,
        path: data.error.path,
        originalError: error,
      }
    }

    // Generic error response
    return {
      message: data?.message || ErrorMessages[errorCode],
      statusCode: status,
      code: errorCode,
      originalError: error,
    }
  }

  // Handle network errors
  if (error?.code === 'ECONNABORTED' || error?.message?.includes('timeout')) {
    return {
      message: ErrorMessages[ErrorCode.TIMEOUT],
      code: ErrorCode.TIMEOUT,
      originalError: error,
    }
  }

  if (error?.code === 'ERR_NETWORK' || error?.message?.includes('Network Error')) {
    return {
      message: ErrorMessages[ErrorCode.NETWORK_ERROR],
      code: ErrorCode.NETWORK_ERROR,
      originalError: error,
    }
  }

  // Handle request cancellation
  if (error?.code === 'ERR_CANCELED') {
    return {
      message: ErrorMessages[ErrorCode.CANCELLED],
      code: ErrorCode.CANCELLED,
      originalError: error,
    }
  }

  // Handle circuit breaker errors
  if (error?.message?.includes('Circuit breaker')) {
    return {
      message: ErrorMessages[ErrorCode.CIRCUIT_BREAKER_OPEN],
      code: ErrorCode.CIRCUIT_BREAKER_OPEN,
      originalError: error,
    }
  }

  // Default error
  return {
    message: error?.message || defaultMessage,
    code: ErrorCode.UNKNOWN,
    originalError: error,
  }
}
