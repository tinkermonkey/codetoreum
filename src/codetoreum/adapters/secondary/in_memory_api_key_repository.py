"""In-memory API key repository adapter for testing and development.

This module provides an in-memory implementation of the API key repository
for testing and development purposes.
"""

from uuid import UUID

from codetoreum.application.authentication_service import IAPIKeyRepository
from codetoreum.domain.user import APIKey
from codetoreum.ports.input.authentication import APIKeyNotFoundError


class InMemoryAPIKeyRepository(IAPIKeyRepository):
    """In-memory API key repository implementation.

    Stores API keys in memory using a dictionary. Useful for testing
    and development without requiring a database.

    Attributes:
        _api_keys: Dictionary mapping API key IDs to API keys
        _user_index: Dictionary mapping user IDs to lists of API key IDs
    """

    def __init__(self) -> None:
        """Initialize empty repository."""
        self._api_keys: dict[UUID, APIKey] = {}
        self._user_index: dict[UUID, list[UUID]] = {}

    async def save(self, api_key: APIKey) -> None:
        """Save an API key."""
        self._api_keys[api_key.id] = api_key

        # Update user index
        if api_key.user_id not in self._user_index:
            self._user_index[api_key.user_id] = []
        if api_key.id not in self._user_index[api_key.user_id]:
            self._user_index[api_key.user_id].append(api_key.id)

    async def get(self, key_id: UUID) -> APIKey:
        """Get an API key by ID."""
        api_key = self._api_keys.get(key_id)
        if api_key is None:
            msg = f"API key not found: {key_id}"
            raise APIKeyNotFoundError(msg)
        return api_key

    async def list_by_user(self, user_id: UUID) -> list[APIKey]:
        """List all API keys for a user."""
        key_ids = self._user_index.get(user_id, [])
        return [self._api_keys[key_id] for key_id in key_ids if key_id in self._api_keys]

    async def list_all(self) -> list[APIKey]:
        """List all API keys (for validation)."""
        return list(self._api_keys.values())

    async def delete(self, key_id: UUID) -> None:
        """Delete an API key."""
        api_key = await self.get(key_id)

        # Remove from main storage
        del self._api_keys[key_id]

        # Remove from user index
        if api_key.user_id in self._user_index:
            if key_id in self._user_index[api_key.user_id]:
                self._user_index[api_key.user_id].remove(key_id)

    def clear(self) -> None:
        """Clear all API keys (for testing)."""
        self._api_keys.clear()
        self._user_index.clear()
