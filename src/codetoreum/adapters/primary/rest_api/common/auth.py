"""
Authentication dependencies for REST API endpoints.
"""

from fastapi import Header

from .errors import unauthorized_error


class User:
    """Represents an authenticated user."""

    def __init__(self, user_id: str, username: str):
        self.user_id = user_id
        self.username = username


async def get_current_user(
    authorization: str | None = Header(None, description="Bearer token")
) -> User:
    """
    Dependency to extract and validate current user from Authorization header.

    Args:
        authorization: Authorization header value (Bearer token)

    Returns:
        Authenticated user

    Raises:
        HTTPException: If authentication fails (401)

    Note:
        This is a placeholder implementation. In production, this should:
        - Validate JWT tokens
        - Check token expiration
        - Verify token signature
        - Extract user claims
        - Check user permissions
    """
    if not authorization:
        raise unauthorized_error("Missing authorization header")

    if not authorization.startswith("Bearer "):
        raise unauthorized_error("Invalid authorization header format")

    token = authorization[7:]  # Remove "Bearer " prefix

    if not token:
        raise unauthorized_error("Missing token")

    # Placeholder: In production, validate token and extract user info
    # For now, return a mock user
    return User(user_id="mock-user-id", username="mock-user")
