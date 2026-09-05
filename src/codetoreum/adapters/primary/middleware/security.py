"""
Security Headers Middleware

Adds security-related HTTP headers to all responses to protect against
common web vulnerabilities.
"""

import os

from fastapi import Request


async def security_headers_middleware(request: Request, call_next):
    """
    Add security headers to all responses.

    Headers added:
    - X-Content-Type-Options: nosniff - Prevents MIME type sniffing
    - X-Frame-Options: DENY - Prevents clickjacking
    - X-XSS-Protection: 1; mode=block - Enables XSS filtering
    - Strict-Transport-Security: Enforces HTTPS (if enabled)
    - Content-Security-Policy: Restricts resource loading

    Args: request: The incoming HTTP request
        call_next: The next middleware or endpoint handler

    Returns: Response with security headers added
    """
    response = await call_next(request)

    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Add HSTS header if using HTTPS
    if os.getenv("API_USE_HTTPS", "false").lower() == "true":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    # Content Security Policy
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self' ws: wss:"
    )

    return response
