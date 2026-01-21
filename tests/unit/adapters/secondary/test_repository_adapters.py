"""
Unit tests for repository adapters.

Tests cover:
- API key repository async operations
- User repository async operations
- Error handling for missing entities
- CRUD operations
- Index management
"""

import pytest
from uuid import UUID, uuid4

from codetoreum.adapters.secondary.in_memory_api_key_repository import InMemoryAPIKeyRepository
from codetoreum.adapters.secondary.in_memory_user_repository import InMemoryUserRepository
from codetoreum.domain.user import User, APIKey
from codetoreum.ports.input.authentication import APIKeyNotFoundError, UserNotFoundError


class TestApiKeyRepository:
    """Tests for API key repository adapter."""

    @pytest.mark.asyncio
    async def test_save_and_get_api_key(self):
        """Test saving and retrieving an API key."""
        repo = InMemoryAPIKeyRepository()
        user_id = uuid4()
        key_id = uuid4()

        api_key = APIKey(
            id=key_id,
            user_id=user_id,
            name="Test Key",
            key="hashed-secret-123"
        )

        await repo.save(api_key)
        retrieved = await repo.get(key_id)

        assert retrieved.id == key_id
        assert retrieved.user_id == user_id
        assert retrieved.name == "Test Key"

    @pytest.mark.asyncio
    async def test_get_api_key_not_found(self):
        """Test retrieving nonexistent API key raises error."""
        repo = InMemoryAPIKeyRepository()

        with pytest.raises(APIKeyNotFoundError):
            await repo.get(uuid4())

    @pytest.mark.asyncio
    async def test_list_api_keys_by_user(self):
        """Test listing API keys by user."""
        repo = InMemoryAPIKeyRepository()
        user_id_1 = uuid4()
        user_id_2 = uuid4()

        key1 = APIKey(id=uuid4(), user_id=user_id_1, name="Key 1", key="secret-1")
        key2 = APIKey(id=uuid4(), user_id=user_id_1, name="Key 2", key="secret-2")
        key3 = APIKey(id=uuid4(), user_id=user_id_2, name="Key 3", key="secret-3")

        await repo.save(key1)
        await repo.save(key2)
        await repo.save(key3)

        user1_keys = await repo.list_by_user(user_id_1)
        user2_keys = await repo.list_by_user(user_id_2)

        assert len(user1_keys) == 2
        assert len(user2_keys) == 1
        assert user2_keys[0].id == key3.id

    @pytest.mark.asyncio
    async def test_list_api_keys_by_user_empty(self):
        """Test listing API keys for user with no keys."""
        repo = InMemoryAPIKeyRepository()

        keys = await repo.list_by_user(uuid4())

        assert keys == []

    @pytest.mark.asyncio
    async def test_list_all_api_keys(self):
        """Test listing all API keys."""
        repo = InMemoryAPIKeyRepository()
        user_id_1 = uuid4()
        user_id_2 = uuid4()

        await repo.save(APIKey(id=uuid4(), user_id=user_id_1, name="Key 1", key="secret-1"))
        await repo.save(APIKey(id=uuid4(), user_id=user_id_1, name="Key 2", key="secret-2"))
        await repo.save(APIKey(id=uuid4(), user_id=user_id_2, name="Key 3", key="secret-3"))

        all_keys = await repo.list_all()

        assert len(all_keys) == 3

    @pytest.mark.asyncio
    async def test_delete_api_key(self):
        """Test deleting an API key."""
        repo = InMemoryAPIKeyRepository()
        user_id = uuid4()
        key_id = uuid4()

        api_key = APIKey(id=key_id, user_id=user_id, name="Test Key", key="secret")
        await repo.save(api_key)

        await repo.delete(key_id)

        with pytest.raises(APIKeyNotFoundError):
            await repo.get(key_id)

    @pytest.mark.asyncio
    async def test_delete_api_key_not_found(self):
        """Test deleting nonexistent API key raises error."""
        repo = InMemoryAPIKeyRepository()

        with pytest.raises(APIKeyNotFoundError):
            await repo.delete(uuid4())

    @pytest.mark.asyncio
    async def test_delete_updates_user_index(self):
        """Test deleting key removes it from user index."""
        repo = InMemoryAPIKeyRepository()
        user_id = uuid4()

        key1 = APIKey(id=uuid4(), user_id=user_id, name="Key 1", key="secret-1")
        key2 = APIKey(id=uuid4(), user_id=user_id, name="Key 2", key="secret-2")

        await repo.save(key1)
        await repo.save(key2)

        assert len(await repo.list_by_user(user_id)) == 2

        await repo.delete(key1.id)

        user_keys = await repo.list_by_user(user_id)
        assert len(user_keys) == 1
        assert user_keys[0].id == key2.id

    @pytest.mark.asyncio
    async def test_save_multiple_keys_same_user(self):
        """Test saving multiple keys for same user."""
        repo = InMemoryAPIKeyRepository()
        user_id = uuid4()

        for i in range(5):
            key = APIKey(id=uuid4(), user_id=user_id, name=f"Key {i}", key=f"secret-{i}")
            await repo.save(key)

        user_keys = await repo.list_by_user(user_id)
        assert len(user_keys) == 5

    @pytest.mark.asyncio
    async def test_clear_all_keys(self):
        """Test clearing all keys."""
        repo = InMemoryAPIKeyRepository()

        await repo.save(APIKey(id=uuid4(), user_id=uuid4(), name="Key", key="secret"))
        await repo.save(APIKey(id=uuid4(), user_id=uuid4(), name="Key", key="secret"))

        repo.clear()

        all_keys = await repo.list_all()
        assert len(all_keys) == 0


class TestUserRepository:
    """Tests for user repository adapter."""

    @pytest.mark.asyncio
    async def test_save_and_get_user(self):
        """Test saving and retrieving a user."""
        repo = InMemoryUserRepository()
        user_id = uuid4()

        user = User(
            id=user_id,
            username="testuser",
            email="test@example.com",
            hashed_password="hashed-password"
        )

        await repo.save(user)
        retrieved = await repo.get(user_id)

        assert retrieved.id == user_id
        assert retrieved.username == "testuser"
        assert retrieved.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_user_not_found(self):
        """Test retrieving nonexistent user raises error."""
        repo = InMemoryUserRepository()

        with pytest.raises(UserNotFoundError):
            await repo.get(uuid4())

    @pytest.mark.asyncio
    async def test_get_user_by_username(self):
        """Test retrieving user by username."""
        repo = InMemoryUserRepository()
        user_id = uuid4()

        user = User(id=user_id, username="testuser", email="test@example.com", hashed_password="hashed")
        await repo.save(user)

        retrieved = await repo.get_by_username("testuser")

        assert retrieved.id == user_id
        assert retrieved.username == "testuser"

    @pytest.mark.asyncio
    async def test_get_user_by_username_not_found(self):
        """Test retrieving nonexistent user by username raises error."""
        repo = InMemoryUserRepository()

        with pytest.raises(UserNotFoundError):
            await repo.get_by_username("nonexistent")

    @pytest.mark.asyncio
    async def test_get_user_by_email(self):
        """Test retrieving user by email."""
        repo = InMemoryUserRepository()
        user_id = uuid4()

        user = User(id=user_id, username="testuser", email="test@example.com", hashed_password="hashed")
        await repo.save(user)

        retrieved = await repo.get_by_email("test@example.com")

        assert retrieved.id == user_id
        assert retrieved.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_user_by_email_not_found(self):
        """Test retrieving nonexistent user by email raises error."""
        repo = InMemoryUserRepository()

        with pytest.raises(UserNotFoundError):
            await repo.get_by_email("nonexistent@example.com")

    @pytest.mark.asyncio
    async def test_list_all_users(self):
        """Test listing all users."""
        repo = InMemoryUserRepository()

        await repo.save(User(id=uuid4(), username="user1", email="user1@example.com", hashed_password="hash"))
        await repo.save(User(id=uuid4(), username="user2", email="user2@example.com", hashed_password="hash"))
        await repo.save(User(id=uuid4(), username="user3", email="user3@example.com", hashed_password="hash"))

        users = await repo.list_all()

        assert len(users) == 3

    @pytest.mark.asyncio
    async def test_list_all_users_empty(self):
        """Test listing users when none exist."""
        repo = InMemoryUserRepository()

        users = await repo.list_all()

        assert users == []

    @pytest.mark.asyncio
    async def test_delete_user(self):
        """Test deleting a user."""
        repo = InMemoryUserRepository()
        user_id = uuid4()

        user = User(id=user_id, username="testuser", email="test@example.com", hashed_password="hashed")
        await repo.save(user)

        await repo.delete(user_id)

        with pytest.raises(UserNotFoundError):
            await repo.get(user_id)

    @pytest.mark.asyncio
    async def test_delete_user_not_found(self):
        """Test deleting nonexistent user raises error."""
        repo = InMemoryUserRepository()

        with pytest.raises(UserNotFoundError):
            await repo.delete(uuid4())

    @pytest.mark.asyncio
    async def test_delete_removes_username_index(self):
        """Test deleting user removes username index."""
        repo = InMemoryUserRepository()
        user_id = uuid4()

        user = User(id=user_id, username="testuser", email="test@example.com", hashed_password="hashed")
        await repo.save(user)

        await repo.delete(user_id)

        with pytest.raises(UserNotFoundError):
            await repo.get_by_username("testuser")

    @pytest.mark.asyncio
    async def test_delete_removes_email_index(self):
        """Test deleting user removes email index."""
        repo = InMemoryUserRepository()
        user_id = uuid4()

        user = User(id=user_id, username="testuser", email="test@example.com", hashed_password="hashed")
        await repo.save(user)

        await repo.delete(user_id)

        with pytest.raises(UserNotFoundError):
            await repo.get_by_email("test@example.com")

    @pytest.mark.asyncio
    async def test_clear_all_users(self):
        """Test clearing all users."""
        repo = InMemoryUserRepository()

        await repo.save(User(id=uuid4(), username="user1", email="user1@example.com", hashed_password="hash"))
        await repo.save(User(id=uuid4(), username="user2", email="user2@example.com", hashed_password="hash"))

        repo.clear()

        users = await repo.list_all()
        assert len(users) == 0


class TestRepositoryErrorHandling:
    """Tests for error handling in repositories."""

    @pytest.mark.asyncio
    async def test_save_duplicate_user_overwrites(self):
        """Test saving duplicate user overwrites existing."""
        repo = InMemoryUserRepository()
        user_id = uuid4()

        user1 = User(id=user_id, username="testuser", email="test@example.com", hashed_password="hash1")
        await repo.save(user1)

        # Overwrite with same ID but different data
        user2 = User(id=user_id, username="testuser", email="newemail@example.com", hashed_password="hash2")
        await repo.save(user2)

        retrieved = await repo.get(user_id)
        assert retrieved.email == "newemail@example.com"

    @pytest.mark.asyncio
    async def test_username_index_consistency(self):
        """Test username index stays consistent."""
        repo = InMemoryUserRepository()

        user1 = User(id=uuid4(), username="testuser", email="user1@example.com", hashed_password="hash")
        await repo.save(user1)

        # Verify can retrieve by username
        retrieved1 = await repo.get_by_username("testuser")
        assert retrieved1.email == "user1@example.com"

    @pytest.mark.asyncio
    async def test_email_index_consistency(self):
        """Test email index stays consistent."""
        repo = InMemoryUserRepository()

        user1 = User(id=uuid4(), username="testuser", email="test@example.com", hashed_password="hash")
        await repo.save(user1)

        # Verify can retrieve by email
        retrieved = await repo.get_by_email("test@example.com")
        assert retrieved.username == "testuser"

    @pytest.mark.asyncio
    async def test_api_key_user_index_consistency(self):
        """Test API key user index stays consistent."""
        repo = InMemoryAPIKeyRepository()
        user_id = uuid4()

        # Save first key
        key1 = APIKey(id=uuid4(), user_id=user_id, name="Key 1", key="secret-1")
        await repo.save(key1)

        # Save second key - index should be updated
        key2 = APIKey(id=uuid4(), user_id=user_id, name="Key 2", key="secret-2")
        await repo.save(key2)

        # Verify both keys are indexed
        keys = await repo.list_by_user(user_id)
        assert len(keys) == 2


class TestRepositoryIntegration:
    """Integration tests for repositories."""

    @pytest.mark.asyncio
    async def test_multiple_users_with_separate_keys(self):
        """Test managing multiple users with separate API keys."""
        user_repo = InMemoryUserRepository()
        key_repo = InMemoryAPIKeyRepository()

        # Create users
        user1_id = uuid4()
        user2_id = uuid4()

        user1 = User(id=user1_id, username="alice", email="alice@example.com", hashed_password="hash1")
        user2 = User(id=user2_id, username="bob", email="bob@example.com", hashed_password="hash2")

        await user_repo.save(user1)
        await user_repo.save(user2)

        # Create API keys for each user
        alice_key = APIKey(id=uuid4(), user_id=user1_id, name="Alice Key", key="secret-a")
        bob_key1 = APIKey(id=uuid4(), user_id=user2_id, name="Bob Key 1", key="secret-b1")
        bob_key2 = APIKey(id=uuid4(), user_id=user2_id, name="Bob Key 2", key="secret-b2")

        await key_repo.save(alice_key)
        await key_repo.save(bob_key1)
        await key_repo.save(bob_key2)

        # Verify users
        assert len(await user_repo.list_all()) == 2

        # Verify keys per user
        alice_keys = await key_repo.list_by_user(user1_id)
        bob_keys = await key_repo.list_by_user(user2_id)

        assert len(alice_keys) == 1
        assert len(bob_keys) == 2

    @pytest.mark.asyncio
    async def test_user_deletion_leaves_keys_orphaned(self):
        """Test that deleting user leaves API keys orphaned."""
        user_repo = InMemoryUserRepository()
        key_repo = InMemoryAPIKeyRepository()

        user_id = uuid4()
        key_id = uuid4()

        user = User(id=user_id, username="testuser", email="test@example.com", hashed_password="hash")
        key = APIKey(id=key_id, user_id=user_id, name="Test Key", key="secret")

        await user_repo.save(user)
        await key_repo.save(key)

        # Delete user
        await user_repo.delete(user_id)

        # User should be gone
        with pytest.raises(UserNotFoundError):
            await user_repo.get(user_id)

        # Key still exists (orphaned)
        retrieved_key = await key_repo.get(key_id)
        assert retrieved_key.user_id == user_id

    @pytest.mark.asyncio
    async def test_many_operations_stress_test(self):
        """Test repository handling many operations."""
        repo = InMemoryUserRepository()

        # Create many users
        user_ids = [uuid4() for _ in range(100)]
        for i, user_id in enumerate(user_ids):
            user = User(id=user_id, username=f"user{i}", email=f"user{i}@example.com", hashed_password="hash")
            await repo.save(user)

        # Verify all created
        all_users = await repo.list_all()
        assert len(all_users) == 100

        # Delete half of them
        for i in range(0, 50):
            await repo.delete(user_ids[i])

        # Verify 50 remain
        remaining = await repo.list_all()
        assert len(remaining) == 50
