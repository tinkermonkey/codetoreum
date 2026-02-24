"""
Exception classes for Codetoreum SDK
"""
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import requests  # type: ignore[import-untyped]


class CodetoreumError(Exception):
    """Base exception for all Codetoreum SDK errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response: Optional["requests.Response"] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response = response


class AuthenticationError(CodetoreumError):
    """Raised when authentication fails (401)."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, status_code=401)


class NotFoundError(CodetoreumError):
    """Raised when a resource is not found (404)."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404)


class ValidationError(CodetoreumError):
    """Raised when request validation fails (422)."""

    def __init__(self, message: str = "Validation error", errors: Optional[list] = None):
        super().__init__(message, status_code=422)
        self.errors = errors or []


class RateLimitError(CodetoreumError):
    """Raised when rate limit is exceeded (429)."""

    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, status_code=429)


class ServerError(CodetoreumError):
    """Raised when server returns 5xx error."""

    def __init__(self, message: str = "Internal server error", status_code: int = 500):
        super().__init__(message, status_code=status_code)
