"""
Integration tests for Authentication API Adapter.

These tests verify that the authentication endpoints work correctly
when integrated with the full FastAPI application.
"""

import os
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from codetoreum.adapters.primary.fastapi_app import create_app
from codetoreum.adapters.secondary.in_memory_api_key_repository import (
    InMemoryAPIKeyRepository,
)
from codetoreum.adapters.secondary.in_memory_user_repository import (
    InMemoryUserRepository,
)
from codetoreum.application.authentication_service import AuthenticationService
from codetoreum.domain.user import UserRole
from codetoreum.ports.input.authentication import CreateUserCommand


# ============================================================================
# Mock Dependencies
# ============================================================================


class MockEventBus:
    """Mock event bus for testing."""

    async def publish(self, event) -> None:
        pass


class MockConfigService:
    """Mock configuration service for testing."""

    async def get_webhook_secret(self):
        return "mock-secret"

    async def list_projects(self):
        return []

    async def get_project_config(self, project: str):
        return None

    async def load_github_state(self, project: str):
        return {}

    async def get_workflow_template(self, workflow_name: str):
        return None


class MockLogger:
    """Mock logger for testing."""

    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass

    def debug(self, message: str) -> None:
        pass


class MockWorkflowCommandPort:
    """Mock workflow command port."""

    async def start_workflow(self, command):
        return None

    async def pause_workflow(self, command):
        return None

    async def resume_workflow(self, command):
        return None

    async def cancel_workflow(self, command):
        return None

    async def retry_stage(self, command):
        return None


class MockTaskQueryPort:
    """Mock task query port."""

    async def get_execution_status(self, execution_id: str):
        return None

    async def list_executions(self, **kwargs):
        return None

    async def get_artifacts(self, execution_id: str, artifact_type=None):
        return None

    async def get_execution_history(self, execution_id: str, limit=None):
        return None

    async def get_workflow_executions(self, workflow_run_id: str):
        return None


class MockConfigCommandPort:
    """Mock configuration command port."""

    async def update_project_config(self, command):
        return None

    async def update_agent_config(self, command):
        return None

    async def update_pipeline_config(self, command):
        return None

    async def add_environment_variable(self, command):
        return None

    async def remove_environment_variable(self, command):
        return None

    async def mount_command(self, command):
        return None

    async def unmount_command(self, command):
        return None

    async def mount_subagent(self, command):
        return None

    async def unmount_subagent(self, command):
        return None


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def auth_service():
    """Create authentication service with in-memory repositories."""
    user_repo = InMemoryUserRepository()
    api_key_repo = InMemoryAPIKeyRepository()

    service = AuthenticationService(
        user_repository=user_repo,
        api_key_repository=api_key_repo,
        secret_key="test-secret-key-for-integration-tests",
        access_token_expire_minutes=30,
        refresh_token_expire_days=7,
    )

    return service


@pytest.fixture
def client(auth_service):
    """Create FastAPI test client with authentication service."""
    app = create_app(
        workflow_command_port=MockWorkflowCommandPort(),
        task_query_port=MockTaskQueryPort(),
        config_command_port=MockConfigCommandPort(),
        event_bus=MockEventBus(),
        config_service=MockConfigService(),
        logger=MockLogger(),
        auth_service=auth_service,
        cors_origins=["*"],
    )

    return TestClient(app)


@pytest.fixture
async def test_user(auth_service):
    """Create a test user."""
    command = CreateUserCommand(
        username="testuser",
        email="test@example.com",
        password="TestPass123",
        roles={UserRole.DEVELOPER},
    )

    user = await auth_service.create_user(command)
    return user


@pytest.fixture
async def admin_user(auth_service):
    """Create an admin test user."""
    command = CreateUserCommand(
        username="adminuser",
        email="admin@example.com",
        password="AdminPass123",
        roles={UserRole.ADMIN},
    )

    user = await auth_service.create_user(command)
    return user


# ============================================================================
# Tests: Public Endpoints
# ============================================================================


@pytest.mark.asyncio
async def test_login_success(client, test_user):
    """Test successful login."""
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "TestPass123"},
    )

    assert response.status_code == 200
    data = response.json()

    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


@pytest.mark.asyncio
async def test_login_invalid_username(client, test_user):
    """Test login with invalid username."""
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "wronguser", "password": "TestPass123"},
    )

    assert response.status_code == 401
    assert "Invalid username or password" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_invalid_password(client, test_user):
    """Test login with invalid password."""
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "WrongPass123"},
    )

    assert response.status_code == 401
    assert "Invalid username or password" in response.json()["detail"]


@pytest.mark.asyncio
async def test_refresh_token(client, test_user):
    """Test token refresh."""
    # First, login to get tokens
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "TestPass123"},
    )

    refresh_token = login_response.json()["refresh_token"]

    # Then, refresh the token
    response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )

    assert response.status_code == 200
    data = response.json()

    assert "access_token" in data
    assert "refresh_token" in data


# ============================================================================
# Tests: Authenticated Endpoints
# ============================================================================


@pytest.mark.asyncio
async def test_get_current_user_with_jwt(client, test_user):
    """Test getting current user info with JWT token."""
    # Login to get access token
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "TestPass123"},
    )

    access_token = login_response.json()["access_token"]

    # Get current user info
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["username"] == "testuser"
    assert UserRole.DEVELOPER.value in data["roles"]
    assert data["auth_method"] == "jwt"


@pytest.mark.asyncio
async def test_get_current_user_no_auth(client):
    """Test getting current user without authentication."""
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_invalid_token(client):
    """Test getting current user with invalid token."""
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer invalid-token"}
    )

    assert response.status_code == 401


# ============================================================================
# Tests: User Management (Admin Only)
# ============================================================================


@pytest.mark.asyncio
async def test_create_user_as_admin(client, admin_user):
    """Test creating a user as admin."""
    # Login as admin
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "adminuser", "password": "AdminPass123"},
    )

    access_token = login_response.json()["access_token"]

    # Create new user
    response = client.post(
        "/api/v1/auth/users",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "NewPass123",
            "roles": [UserRole.VIEWER.value],
        },
    )

    assert response.status_code == 201
    data = response.json()

    assert data["username"] == "newuser"
    assert data["email"] == "newuser@example.com"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_user_as_non_admin(client, test_user):
    """Test creating a user as non-admin (should fail)."""
    # Login as regular user
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "TestPass123"},
    )

    access_token = login_response.json()["access_token"]

    # Attempt to create new user
    response = client.post(
        "/api/v1/auth/users",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "NewPass123",
            "roles": [UserRole.VIEWER.value],
        },
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_user_weak_password(client, admin_user):
    """Test creating a user with weak password (should fail)."""
    # Login as admin
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "adminuser", "password": "AdminPass123"},
    )

    access_token = login_response.json()["access_token"]

    # Attempt to create user with weak password
    response = client.post(
        "/api/v1/auth/users",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "weak",  # Too short, no uppercase, no digit
            "roles": [UserRole.VIEWER.value],
        },
    )

    assert response.status_code == 400
    assert "Password must be at least 8 characters long" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_user_invalid_email(client, admin_user):
    """Test creating a user with invalid email (should fail)."""
    # Login as admin
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "adminuser", "password": "AdminPass123"},
    )

    access_token = login_response.json()["access_token"]

    # Attempt to create user with invalid email
    response = client.post(
        "/api/v1/auth/users",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "username": "newuser",
            "email": "not-an-email",
            "password": "NewPass123",
            "roles": [UserRole.VIEWER.value],
        },
    )

    assert response.status_code == 422  # FastAPI validation error


# ============================================================================
# Tests: API Key Management
# ============================================================================


@pytest.mark.asyncio
async def test_create_api_key(client, test_user):
    """Test creating an API key."""
    # Login to get access token
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "TestPass123"},
    )

    access_token = login_response.json()["access_token"]

    # Create API key
    response = client.post(
        "/api/v1/auth/api-keys",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"name": "Test API Key", "roles": [UserRole.SERVICE_ACCOUNT.value]},
    )

    assert response.status_code == 201
    data = response.json()

    assert data["name"] == "Test API Key"
    assert "key" in data  # Plaintext key returned only on creation
    assert data["key"].startswith("ctk_")  # Our custom prefix
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_list_api_keys(client, test_user):
    """Test listing API keys."""
    # Login to get access token
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "TestPass123"},
    )

    access_token = login_response.json()["access_token"]

    # Create an API key
    create_response = client.post(
        "/api/v1/auth/api-keys",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"name": "Test API Key", "roles": [UserRole.SERVICE_ACCOUNT.value]},
    )

    # List API keys
    response = client.get(
        "/api/v1/auth/api-keys",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["name"] == "Test API Key"
    assert data[0]["key"] is None  # Plaintext key not returned in list


@pytest.mark.asyncio
async def test_authenticate_with_api_key(client, test_user, auth_service):
    """Test authenticating with an API key."""
    # Create an API key directly via service
    from codetoreum.ports.input.authentication import CreateAPIKeyCommand

    command = CreateAPIKeyCommand(
        name="Test API Key",
        user_id=test_user.id,
        roles={UserRole.SERVICE_ACCOUNT},
    )

    api_key_obj, plaintext_key = await auth_service.create_api_key(command)

    # Use API key to authenticate
    response = client.get(
        "/api/v1/auth/me", headers={"X-API-Key": plaintext_key}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["username"] == "testuser"
    assert data["auth_method"] == "api_key"


@pytest.mark.asyncio
async def test_revoke_api_key(client, test_user, auth_service):
    """Test revoking an API key."""
    # Create an API key
    from codetoreum.ports.input.authentication import CreateAPIKeyCommand

    command = CreateAPIKeyCommand(
        name="Test API Key",
        user_id=test_user.id,
        roles={UserRole.SERVICE_ACCOUNT},
    )

    api_key_obj, plaintext_key = await auth_service.create_api_key(command)

    # Login to get access token
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "TestPass123"},
    )

    access_token = login_response.json()["access_token"]

    # Revoke API key
    response = client.delete(
        f"/api/v1/auth/api-keys/{api_key_obj.id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 204

    # Verify API key no longer works
    me_response = client.get(
        "/api/v1/auth/me", headers={"X-API-Key": plaintext_key}
    )

    assert me_response.status_code == 401
