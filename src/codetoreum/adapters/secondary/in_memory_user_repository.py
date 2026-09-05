"""In-memory user repository adapter for testing and development.

This module provides an in-memory implementation of the user repository
for testing and development purposes.
"""

from uuid import UUID

from codetoreum.application.authentication_service import IUserRepository
from codetoreum.domain.user import User
from codetoreum.ports.input.authentication import UserNotFoundError


class InMemoryUserRepository(IUserRepository):
    """In-memory user repository implementation.

    Stores users in memory using a dictionary. Useful for testing
    and development without requiring a database.

    Attributes:
        _users: Dictionary mapping user IDs to users
        _username_index: Dictionary mapping usernames to user IDs
        _email_index: Dictionary mapping emails to user IDs
    """

    def __init__(self) -> None:
        """Initialize empty repository."""
        self._users: dict[UUID, User] = {}
        self._username_index: dict[str, UUID] = {}
        self._email_index: dict[str, UUID] = {}

    async def save(self, user: User) -> None:
        """Save a user."""
        self._users[user.id] = user
        self._username_index[user.username] = user.id
        self._email_index[user.email] = user.id

    async def get(self, user_id: UUID) -> User:
        """Get a user by ID."""
        user = self._users.get(user_id)
        if user is None:
            msg = f"User not found: {user_id}"
            raise UserNotFoundError(msg)
        return user

    async def get_by_username(self, username: str) -> User:
        """Get a user by username."""
        user_id = self._username_index.get(username)
        if user_id is None:
            msg = f"User not found with username: {username}"
            raise UserNotFoundError(msg)
        return await self.get(user_id)

    async def get_by_email(self, email: str) -> User:
        """Get a user by email."""
        user_id = self._email_index.get(email)
        if user_id is None:
            msg = f"User not found with email: {email}"
            raise UserNotFoundError(msg)
        return await self.get(user_id)

    async def delete(self, user_id: UUID) -> None:
        """Delete a user."""
        user = await self.get(user_id)
        del self._users[user_id]
        del self._username_index[user.username]
        del self._email_index[user.email]

    async def list_all(self) -> list[User]:
        """List all users (for testing)."""
        return list(self._users.values())

    def clear(self) -> None:
        """Clear all users (for testing)."""
        self._users.clear()
        self._username_index.clear()
        self._email_index.clear()
