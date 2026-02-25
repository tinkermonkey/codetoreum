"""Unit tests for authentication service."""

from uuid import uuid4

import pytest

from codetoreum.adapters.secondary.in_memory_api_key_repository import (
    InMemoryAPIKeyRepository,
)
from codetoreum.adapters.secondary.in_memory_user_repository import (
    InMemoryUserRepository,
)
from codetoreum.application.authentication_service import AuthenticationService
from codetoreum.domain.user import Permission, UserRole
from codetoreum.ports.input.authentication import (
    AuthenticationError,
    CreateAPIKeyCommand,
    CreateUserCommand,
    LoginCommand,
    UpdateUserCommand,
    UserAlreadyExistsError,
    UserNotFoundError,
)


@pytest.fixture
def user_repo():
    """Create in-memory user repository."""
    return InMemoryUserRepository()


@pytest.fixture
def api_key_repo():
    """Create in-memory API key repository."""
    return InMemoryAPIKeyRepository()


@pytest.fixture
def auth_service(user_repo, api_key_repo):
    """Create authentication service."""
    return AuthenticationService(
        user_repository=user_repo,
        api_key_repository=api_key_repo,
        secret_key="test-secret-key-for-jwt-signing",
        algorithm="HS256",
        access_token_expire_minutes=30,
        refresh_token_expire_days=7,
    )


@pytest.mark.unit
class TestUserManagement:
    """Tests for user management operations."""

    @pytest.mark.asyncio
    async def test_create_user(self, auth_service):
        """Test creating a new user."""
        command = CreateUserCommand(
            username="testuser",
            email="test@example.com",
            password="TestPass123",
            roles={UserRole.DEVELOPER},
        )

        user = await auth_service.create_user(command)

        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.roles == {UserRole.DEVELOPER}
        assert user.is_active is True
        assert user.hashed_password != "TestPass123"  # Should be hashed

    @pytest.mark.asyncio
    async def test_create_user_duplicate_username(self, auth_service):
        """Test creating user with duplicate username fails."""
        command = CreateUserCommand(
            username="testuser",
            email="test1@example.com",
            password="TestPass123",
            roles={UserRole.DEVELOPER},
        )
        await auth_service.create_user(command)

        # Try to create another user with same username
        command2 = CreateUserCommand(
            username="testuser",
            email="test2@example.com",
            password="TestPass456",
            roles={UserRole.DEVELOPER},
        )

        with pytest.raises(UserAlreadyExistsError):
            await auth_service.create_user(command2)

    @pytest.mark.asyncio
    async def test_get_user(self, auth_service):
        """Test getting a user by ID."""
        # Create user
        command = CreateUserCommand(
            username="testuser",
            email="test@example.com",
            password="TestPass123",
            roles={UserRole.DEVELOPER},
        )
        created_user = await auth_service.create_user(command)

        # Get user
        user = await auth_service.get_user(created_user.id)

        assert user.id == created_user.id
        assert user.username == "testuser"

    @pytest.mark.asyncio
    async def test_get_user_by_username(self, auth_service):
        """Test getting a user by username."""
        # Create user
        command = CreateUserCommand(
            username="testuser",
            email="test@example.com",
            password="TestPass123",
            roles={UserRole.DEVELOPER},
        )
        await auth_service.create_user(command)

        # Get user by username
        user = await auth_service.get_user_by_username("testuser")

        assert user.username == "testuser"
        assert user.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_user_not_found(self, auth_service):
        """Test getting non-existent user raises error."""
        with pytest.raises(UserNotFoundError):
            await auth_service.get_user(uuid4())

    @pytest.mark.asyncio
    async def test_update_user(self, auth_service):
        """Test updating a user."""
        # Create user
        command = CreateUserCommand(
            username="testuser",
            email="test@example.com",
            password="TestPass123",
            roles={UserRole.DEVELOPER},
        )
        user = await auth_service.create_user(command)

        # Update user
        update_command = UpdateUserCommand(
            user_id=user.id,
            email="newemail@example.com",
            roles={UserRole.ADMIN},
        )
        updated_user = await auth_service.update_user(update_command)

        assert updated_user.email == "newemail@example.com"
        assert updated_user.roles == {UserRole.ADMIN}

    @pytest.mark.asyncio
    async def test_delete_user(self, auth_service):
        """Test deleting a user."""
        # Create user
        command = CreateUserCommand(
            username="testuser",
            email="test@example.com",
            password="TestPass123",
            roles={UserRole.DEVELOPER},
        )
        user = await auth_service.create_user(command)

        # Delete user
        await auth_service.delete_user(user.id)

        # Verify user is deleted
        with pytest.raises(UserNotFoundError):
            await auth_service.get_user(user.id)


@pytest.mark.unit
class TestAuthentication:
    """Tests for authentication operations."""

    @pytest.mark.asyncio
    async def test_login_success(self, auth_service):
        """Test successful login."""
        # Create user
        command = CreateUserCommand(
            username="testuser",
            email="test@example.com",
            password="TestPass123",
            roles={UserRole.DEVELOPER},
        )
        await auth_service.create_user(command)

        # Login
        login_command = LoginCommand(username="testuser", password="TestPass123")
        result = await auth_service.login(login_command)

        assert result.access_token is not None
        assert result.token_type == "bearer"
        assert result.refresh_token is not None

    @pytest.mark.asyncio
    async def test_login_invalid_password(self, auth_service):
        """Test login with invalid password fails."""
        # Create user
        command = CreateUserCommand(
            username="testuser",
            email="test@example.com",
            password="TestPass123",
            roles={UserRole.DEVELOPER},
        )
        await auth_service.create_user(command)

        # Try to login with wrong password
        login_command = LoginCommand(username="testuser", password="WrongPass123")

        with pytest.raises(AuthenticationError):
            await auth_service.login(login_command)

    @pytest.mark.asyncio
    async def test_login_inactive_user(self, auth_service):
        """Test login with inactive user fails."""
        # Create user
        command = CreateUserCommand(
            username="testuser",
            email="test@example.com",
            password="TestPass123",
            roles={UserRole.DEVELOPER},
        )
        user = await auth_service.create_user(command)

        # Deactivate user
        update_command = UpdateUserCommand(user_id=user.id, is_active=False)
        await auth_service.update_user(update_command)

        # Try to login
        login_command = LoginCommand(username="testuser", password="TestPass123")

        with pytest.raises(AuthenticationError):
            await auth_service.login(login_command)

    @pytest.mark.asyncio
    async def test_validate_token(self, auth_service):
        """Test token validation."""
        # Create user and login
        command = CreateUserCommand(
            username="testuser",
            email="test@example.com",
            password="TestPass123",
            roles={UserRole.DEVELOPER},
        )
        await auth_service.create_user(command)

        login_command = LoginCommand(username="testuser", password="TestPass123")
        result = await auth_service.login(login_command)

        # Validate token
        auth_context = await auth_service.validate_token(result.access_token)

        assert auth_context.username == "testuser"
        assert UserRole.DEVELOPER in auth_context.roles
        assert auth_context.auth_method == "jwt"

    @pytest.mark.asyncio
    async def test_validate_invalid_token(self, auth_service):
        """Test validating invalid token fails."""
        with pytest.raises(AuthenticationError):
            await auth_service.validate_token("invalid-token")

    @pytest.mark.asyncio
    async def test_refresh_token(self, auth_service):
        """Test token refresh."""
        # Create user and login
        command = CreateUserCommand(
            username="testuser",
            email="test@example.com",
            password="TestPass123",
            roles={UserRole.DEVELOPER},
        )
        await auth_service.create_user(command)

        login_command = LoginCommand(username="testuser", password="TestPass123")
        result = await auth_service.login(login_command)

        # Refresh token
        refreshed = await auth_service.refresh_token(result.refresh_token)

        # Verify we got new tokens
        assert refreshed.access_token is not None
        assert refreshed.refresh_token is not None
        # Verify the new access token is valid
        auth_context = await auth_service.validate_token(refreshed.access_token)
        assert auth_context.username == "testuser"


@pytest.mark.unit
class TestAPIKeys:
    """Tests for API key operations."""

    @pytest.mark.asyncio
    async def test_create_api_key(self, auth_service):
        """Test creating an API key."""
        # Create user
        user_command = CreateUserCommand(
            username="testuser",
            email="test@example.com",
            password="TestPass123",
            roles={UserRole.DEVELOPER},
        )
        user = await auth_service.create_user(user_command)

        # Create API key
        command = CreateAPIKeyCommand(
            name="Test API Key",
            user_id=user.id,
            roles={UserRole.SERVICE_ACCOUNT},
        )
        api_key, plaintext_key = await auth_service.create_api_key(command)

        assert api_key.name == "Test API Key"
        assert plaintext_key.startswith("ctk_")
        assert api_key.is_active is True

    @pytest.mark.asyncio
    async def test_validate_api_key(self, auth_service):
        """Test API key validation."""
        # Create user
        user_command = CreateUserCommand(
            username="testuser",
            email="test@example.com",
            password="TestPass123",
            roles={UserRole.DEVELOPER},
        )
        user = await auth_service.create_user(user_command)

        # Create API key
        command = CreateAPIKeyCommand(
            name="Test API Key",
            user_id=user.id,
            roles={UserRole.SERVICE_ACCOUNT},
        )
        api_key, plaintext_key = await auth_service.create_api_key(command)

        # Validate API key
        auth_context = await auth_service.validate_api_key(plaintext_key)

        assert auth_context.username == "testuser"
        assert UserRole.SERVICE_ACCOUNT in auth_context.roles
        assert auth_context.auth_method == "api_key"
        assert auth_context.api_key_id == api_key.id

    @pytest.mark.asyncio
    async def test_validate_invalid_api_key(self, auth_service):
        """Test validating invalid API key fails."""
        with pytest.raises(AuthenticationError):
            await auth_service.validate_api_key("invalid-key")

    @pytest.mark.asyncio
    async def test_revoke_api_key(self, auth_service):
        """Test revoking an API key."""
        # Create user
        user_command = CreateUserCommand(
            username="testuser",
            email="test@example.com",
            password="TestPass123",
            roles={UserRole.DEVELOPER},
        )
        user = await auth_service.create_user(user_command)

        # Create API key
        command = CreateAPIKeyCommand(
            name="Test API Key",
            user_id=user.id,
            roles={UserRole.SERVICE_ACCOUNT},
        )
        api_key, plaintext_key = await auth_service.create_api_key(command)

        # Revoke API key
        await auth_service.revoke_api_key(api_key.id)

        # Try to validate revoked key
        with pytest.raises(AuthenticationError):
            await auth_service.validate_api_key(plaintext_key)

    @pytest.mark.asyncio
    async def test_list_api_keys(self, auth_service):
        """Test listing API keys for a user."""
        # Create user
        user_command = CreateUserCommand(
            username="testuser",
            email="test@example.com",
            password="TestPass123",
            roles={UserRole.DEVELOPER},
        )
        user = await auth_service.create_user(user_command)

        # Create multiple API keys
        command1 = CreateAPIKeyCommand(
            name="Key 1", user_id=user.id, roles={UserRole.SERVICE_ACCOUNT}
        )
        command2 = CreateAPIKeyCommand(
            name="Key 2", user_id=user.id, roles={UserRole.SERVICE_ACCOUNT}
        )

        await auth_service.create_api_key(command1)
        await auth_service.create_api_key(command2)

        # List API keys
        keys = await auth_service.list_api_keys(user.id)

        assert len(keys) == 2
        assert any(key.name == "Key 1" for key in keys)
        assert any(key.name == "Key 2" for key in keys)


@pytest.mark.unit
class TestPermissions:
    """Tests for permission checking."""

    @pytest.mark.asyncio
    async def test_user_has_permission(self, auth_service):
        """Test checking if user has permission."""
        # Create user with developer role
        command = CreateUserCommand(
            username="testuser",
            email="test@example.com",
            password="TestPass123",
            roles={UserRole.DEVELOPER},
        )
        user = await auth_service.create_user(command)

        # Login to get auth context
        login_command = LoginCommand(username="testuser", password="TestPass123")
        result = await auth_service.login(login_command)
        auth_context = await auth_service.validate_token(result.access_token)

        # Check permissions
        assert await auth_service.check_permission(
            auth_context, Permission.WORKFLOW_VIEW.value
        )
        assert await auth_service.check_permission(
            auth_context, Permission.WORKFLOW_CREATE.value
        )
        assert not await auth_service.check_permission(
            auth_context, Permission.USER_DELETE.value
        )  # Developer doesn't have this

    @pytest.mark.asyncio
    async def test_admin_has_all_permissions(self, auth_service):
        """Test that admin has all permissions."""
        # Create admin user
        command = CreateUserCommand(
            username="admin",
            email="admin@example.com",
            password="AdminPass123",
            roles={UserRole.ADMIN},
        )
        await auth_service.create_user(command)

        # Login
        login_command = LoginCommand(username="admin", password="AdminPass123")
        result = await auth_service.login(login_command)
        auth_context = await auth_service.validate_token(result.access_token)

        # Admin should have all permissions
        assert await auth_service.check_permission(
            auth_context, Permission.WORKFLOW_CREATE.value
        )
        assert await auth_service.check_permission(
            auth_context, Permission.USER_DELETE.value
        )
        assert await auth_service.check_permission(
            auth_context, Permission.CONFIG_UPDATE.value
        )
