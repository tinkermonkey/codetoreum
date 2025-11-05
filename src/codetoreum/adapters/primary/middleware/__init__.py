"""
Middleware components for the FastAPI application.
"""

from codetoreum.adapters.primary.middleware.security import security_headers_middleware

__all__ = ["security_headers_middleware"]
