"""Authentication input port interface.

This module defines the input port interface for authentication operations.
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from codetoreum.domain.user import APIKey, AuthContext, User, UserRole

# ============================================================================
# Exceptions
# ============================================================================


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass


class UserAlreadyExistsError(Exception):
    """Raised when trying to create a user that already exists."""

    pass


class UserNotFoundError(Exception):
    """Raised when a user is not found."""

    pass


class APIKeyNotFoundError(Exception):
    """Raised when an API key is not found."""

    pass


class ValidationError(Exception):
    """Raised when validation fails."""

    pass


# ============================================================================
# Validation Functions
# ============================================================================


def validate_email(email: str) -> None:
    """Validate email format.

    Args:
        email: Email address to validate

    Raises:
        ValidationError: If email format is invalid
    """
    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not re.match(email_pattern, email):
        msg = f"Invalid email format: {email}"
        raise ValidationError(msg)


def validate_username(username: str) -> None:
    """Validate username format.

    Args:
        username: Username to validate

    Raises:
        ValidationError: If username format is invalid
    """
    if len(username) < 3:
        msg = "Username must be at least 3 characters long"
        raise ValidationError(msg)
    if len(username) > 50:
        msg = "Username must be at most 50 characters long"
        raise ValidationError(msg)
    if not re.match(r"^[a-zA-Z0-9_-]+$", username):
        msg = "Username can only contain letters, numbers, underscores, and hyphens"
        raise ValidationError(msg)


def validate_password(password: str) -> None:
    """Validate password strength.

    Args:
        password: Password to validate

    Raises:
        ValidationError: If password doesn't meet requirements
    """
    if len(password) < 8:
        msg = "Password must be at least 8 characters long"
        raise ValidationError(msg)
    if not re.search(r"[A-Z]", password):
        msg = "Password must contain at least one uppercase letter"
        raise ValidationError(msg)
    if not re.search(r"[a-z]", password):
        msg = "Password must contain at least one lowercase letter"
        raise ValidationError(msg)
    if not re.search(r"[0-9]", password):
        msg = "Password must contain at least one digit"
        raise ValidationError(msg)


@dataclass
class CreateUserCommand:
    """Command to create a new user."""

    username: str
    email: str
    password: str
    roles: set[UserRole]
    metadata: dict | None = None


@dataclass
class UpdateUserCommand:
    """Command to update a user."""

    user_id: UUID
    email: Optional[str] = None
    password: Optional[str] = None
    roles: Optional[set[UserRole]] = None
    is_active: Optional[bool] = None
    metadata: dict | None = None


@dataclass
class CreateAPIKeyCommand:
    """Command to create a new API key."""

    name: str
    user_id: UUID
    roles: set[UserRole]
    expires_at: Optional[datetime] = None
    metadata: dict | None = None


@dataclass
class LoginCommand:
    """Command to log in a user."""

    username: str
    password: str


@dataclass
class LoginResult:
    """Result of a login command."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600  # seconds
    refresh_token: Optional[str] = None
    user: Optional[User] = None


class IAuthenticationPort(ABC):
    """Input port for authentication operations.

    This port defines the interface for user authentication,
    authorization, and session management operations.
    """

    @abstractmethod
    async def create_user(self, command: CreateUserCommand) -> User:
        """Create a new user.

        Args:
            command: User creation command

        Returns:
            Created user

        Raises:
            UserAlreadyExistsError: If username or email already exists
            ValidationError: If user data is invalid
        """
        pass

    @abstractmethod
    async def update_user(self, command: UpdateUserCommand) -> User:
        """Update a user.

        Args:
            command: User update command

        Returns:
            Updated user

        Raises:
            UserNotFoundError: If user does not exist
            ValidationError: If update data is invalid
        """
        pass

    @abstractmethod
    async def get_user(self, user_id: UUID) -> User:
        """Get a user by ID.

        Args:
            user_id: User ID

        Returns:
            User

        Raises:
            UserNotFoundError: If user does not exist
        """
        pass

    @abstractmethod
    async def get_user_by_username(self, username: str) -> User:
        """Get a user by username.

        Args:
            username: Username

        Returns:
            User

        Raises:
            UserNotFoundError: If user does not exist
        """
        pass

    @abstractmethod
    async def delete_user(self, user_id: UUID) -> None:
        """Delete a user.

        Args:
            user_id: User ID

        Raises:
            UserNotFoundError: If user does not exist
        """
        pass

    @abstractmethod
    async def login(self, command: LoginCommand) -> LoginResult:
        """Authenticate a user with username and password.

        Args:
            command: Login command with credentials

        Returns:
            Login result with access token

        Raises:
            AuthenticationError: If credentials are invalid
        """
        pass

    @abstractmethod
    async def validate_token(self, token: str) -> AuthContext:
        """Validate a JWT token and return auth context.

        Args:
            token: JWT token

        Returns:
            Authentication context

        Raises:
            AuthenticationError: If token is invalid or expired
        """
        pass

    @abstractmethod
    async def refresh_token(self, refresh_token: str) -> LoginResult:
        """Refresh an access token using a refresh token.

        Args:
            refresh_token: Refresh token

        Returns:
            New login result with new access token

        Raises:
            AuthenticationError: If refresh token is invalid
        """
        pass

    @abstractmethod
    async def create_api_key(self, command: CreateAPIKeyCommand) -> tuple[APIKey, str]:
        """Create a new API key.

        Args:
            command: API key creation command

        Returns:
            Tuple of (API key object, plaintext key string)
            Note: The plaintext key is only returned once and should be stored securely

        Raises:
            UserNotFoundError: If user does not exist
            ValidationError: If API key data is invalid
        """
        pass

    @abstractmethod
    async def validate_api_key(self, key: str) -> AuthContext:
        """Validate an API key and return auth context.

        Args:
            key: API key string

        Returns:
            Authentication context

        Raises:
            AuthenticationError: If API key is invalid or expired
        """
        pass

    @abstractmethod
    async def revoke_api_key(self, key_id: UUID) -> None:
        """Revoke an API key.

        Args:
            key_id: API key ID

        Raises:
            APIKeyNotFoundError: If API key does not exist
        """
        pass

    @abstractmethod
    async def list_api_keys(self, user_id: UUID) -> list[APIKey]:
        """List all API keys for a user.

        Args:
            user_id: User ID

        Returns:
            List of API keys

        Raises:
            UserNotFoundError: If user does not exist
        """
        pass

    @abstractmethod
    async def check_permission(self, auth_context: AuthContext, permission: str) -> bool:
        """Check if auth context has a specific permission.

        Args:
            auth_context: Authentication context
            permission: Permission to check

        Returns:
            True if permission granted, False otherwise
        """
        pass
