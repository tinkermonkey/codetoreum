"""Integration tests for Agents REST API endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codetoreum.adapters.primary.routers.agents import create_agents_router
from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.ports.input.agent_command import (
    AddAgentCapabilityCommand,
    AddMcpServerCommand,
    CreateAgentCommand,
    IAgentCommandPort,
    RemoveAgentCapabilityCommand,
    RemoveMcpServerCommand,
    UpdateAgentCapabilityCommand,
    UpdateAgentCommand,
)
from codetoreum.ports.input.agent_query import (
    AgentExecutionStats,
    AgentFilters,
    AgentInfo,
    AgentPaginationParams,
    AgentSortField,
    IAgentQueryPort,
    SortOrder,
)


# ============================================================================
# Mock Implementations
# ============================================================================


class MockAgentCommandPort(IAgentCommandPort):
    """Mock implementation of agent command port for testing."""

    def __init__(self):
        self._create_agent = AsyncMock()
        self._update_agent = AsyncMock()
        self._delete_agent = AsyncMock()
        self._add_capability = AsyncMock()
        self._remove_capability = AsyncMock()
        self._update_capability = AsyncMock()
        self._add_mcp_server = AsyncMock()
        self._remove_mcp_server = AsyncMock()

    async def create_agent(self, command):
        return await self._create_agent(command)

    async def update_agent(self, command):
        return await self._update_agent(command)

    async def delete_agent(self, agent_id):
        return await self._delete_agent(agent_id)

    async def add_capability(self, command):
        return await self._add_capability(command)

    async def remove_capability(self, command):
        return await self._remove_capability(command)

    async def update_capability(self, command):
        return await self._update_capability(command)

    async def add_mcp_server(self, command):
        return await self._add_mcp_server(command)

    async def remove_mcp_server(self, command):
        return await self._remove_mcp_server(command)


class MockAgentQueryPort(IAgentQueryPort):
    """Mock implementation of agent query port for testing."""

    def __init__(self):
        self._get_agent = AsyncMock()
        self._list_agents = AsyncMock()
        self._count_agents = AsyncMock()

    async def get_agent(self, agent_id, include_stats=False):
        return await self._get_agent(agent_id, include_stats)

    async def list_agents(self, filters=None, pagination=None):
        return await self._list_agents(filters, pagination)

    async def count_agents(self, filters=None):
        return await self._count_agents(filters)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_command_port():
    """Fixture providing mock agent command port."""
    return MockAgentCommandPort()


@pytest.fixture
def mock_query_port():
    """Fixture providing mock agent query port."""
    return MockAgentQueryPort()


@pytest.fixture
def app(mock_command_port, mock_query_port):
    """Fixture providing FastAPI test application."""
    app = FastAPI()

    # Create and include agents router (without auth for testing)
    router = create_agents_router(
        command_port=mock_command_port,
        query_port=mock_query_port,
        auth_deps=None,  # Disable auth for testing
    )
    app.include_router(router)

    return app


@pytest.fixture
def client(app):
    """Fixture providing test client."""
    return TestClient(app)


@pytest.fixture
def sample_agent():
    """Fixture providing a sample agent."""
    now = datetime.now(timezone.utc)
    return Agent(
        id="agent-123",
        name="test-agent",
        display_name="Test Agent",
        agent_type=AgentType.MAKER,
        role_description="A test agent for testing",
        model="claude-sonnet-4",
        capabilities={
            "code_review": AgentCapability(
                skill="code_review",
                proficiency=0.9,
                description="Code review skill",
            ),
            "testing": AgentCapability(
                skill="testing",
                proficiency=0.8,
                description="Testing skill",
            ),
        },
        timeout_seconds=300,
        max_retries=3,
        requires_docker=True,
        requires_dev_container=False,
        makes_code_changes=True,
        filesystem_write_allowed=True,
        mcp_servers=["artifacts", "logging"],
        created_at=now,
        updated_at=now,
        version=1,
    )


@pytest.fixture
def sample_agent_info(sample_agent):
    """Fixture providing a sample agent info."""
    now = datetime.now(timezone.utc)
    return AgentInfo(
        id=sample_agent.id,
        name=sample_agent.name,
        display_name=sample_agent.display_name,
        agent_type=sample_agent.agent_type.value,
        role_description=sample_agent.role_description,
        model=sample_agent.model,
        timeout_seconds=sample_agent.timeout_seconds,
        max_retries=sample_agent.max_retries,
        requires_docker=sample_agent.requires_docker,
        requires_dev_container=sample_agent.requires_dev_container,
        makes_code_changes=sample_agent.makes_code_changes,
        filesystem_write_allowed=sample_agent.filesystem_write_allowed,
        mcp_servers=sample_agent.mcp_servers,
        created_at=sample_agent.created_at,
        updated_at=sample_agent.updated_at,
        capabilities={
            "code_review": 0.9,
            "testing": 0.8,
        },
        environment_variables=None,
        execution_stats=AgentExecutionStats(
            total_executions=10,
            successful_executions=8,
            failed_executions=2,
            timeout_executions=0,
            average_duration_seconds=120.5,
            last_execution_at=now,
        ),
    )


# ============================================================================
# Test Cases
# ============================================================================


class TestListAgents:
    """Tests for GET /api/v2/agents endpoint."""

    def test_list_agents_success(self, client, mock_query_port, sample_agent_info):
        """Test successful agents listing."""
        # Arrange
        from codetoreum.ports.input.agent_query import AgentListResult

        mock_query_port._list_agents.return_value = AgentListResult(
            agents=[sample_agent_info],
            total_count=1,
            offset=0,
            limit=20,
            has_next=False,
        )

        # Act
        response = client.get("/api/v2/agents")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1
        assert len(data["agents"]) == 1
        assert data["agents"][0]["id"] == "agent-123"
        assert data["agents"][0]["name"] == "test-agent"
        assert data["has_next"] is False

    def test_list_agents_with_capability_filter(
        self, client, mock_query_port, sample_agent_info
    ):
        """Test agents listing with capability filter."""
        # Arrange
        from codetoreum.ports.input.agent_query import AgentListResult

        mock_query_port._list_agents.return_value = AgentListResult(
            agents=[sample_agent_info],
            total_count=1,
            offset=0,
            limit=20,
            has_next=False,
        )

        # Act
        response = client.get("/api/v2/agents?capability=code_review")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1

        # Verify filters were applied
        mock_query_port._list_agents.assert_called_once()
        call_args = mock_query_port._list_agents.call_args[0]
        filters = call_args[0]
        assert filters.capability == "code_review"

    def test_list_agents_with_type_filter(
        self, client, mock_query_port, sample_agent_info
    ):
        """Test agents listing with agent type filter."""
        # Arrange
        from codetoreum.ports.input.agent_query import AgentListResult

        mock_query_port._list_agents.return_value = AgentListResult(
            agents=[sample_agent_info],
            total_count=1,
            offset=0,
            limit=20,
            has_next=False,
        )

        # Act
        response = client.get("/api/v2/agents?agent_type=maker")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1

        # Verify filters were applied
        mock_query_port._list_agents.assert_called_once()
        call_args = mock_query_port._list_agents.call_args[0]
        filters = call_args[0]
        assert filters.agent_type == AgentType.MAKER

    def test_list_agents_with_invalid_type_filter(self, client):
        """Test agents listing with invalid agent type filter."""
        # Act
        response = client.get("/api/v2/agents?agent_type=invalid_type")

        # Assert
        assert response.status_code == 400
        data = response.json()
        assert "Invalid agent type" in data["detail"]

    def test_list_agents_with_multiple_filters(
        self, client, mock_query_port, sample_agent_info
    ):
        """Test agents listing with multiple filters."""
        # Arrange
        from codetoreum.ports.input.agent_query import AgentListResult

        mock_query_port._list_agents.return_value = AgentListResult(
            agents=[sample_agent_info],
            total_count=1,
            offset=0,
            limit=20,
            has_next=False,
        )

        # Act
        response = client.get(
            "/api/v2/agents?requires_docker=true&makes_code_changes=true&agent_type=maker"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1

        # Verify filters were applied
        mock_query_port._list_agents.assert_called_once()
        call_args = mock_query_port._list_agents.call_args[0]
        filters = call_args[0]
        assert filters.requires_docker is True
        assert filters.makes_code_changes is True
        assert filters.agent_type == AgentType.MAKER

    def test_list_agents_with_pagination(
        self, client, mock_query_port, sample_agent_info
    ):
        """Test agents listing with pagination."""
        # Arrange
        from codetoreum.ports.input.agent_query import AgentListResult

        mock_query_port._list_agents.return_value = AgentListResult(
            agents=[sample_agent_info],
            total_count=100,
            offset=20,
            limit=50,
            has_next=True,
        )

        # Act
        response = client.get("/api/v2/agents?offset=20&limit=50")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 100
        assert data["page"] == 1  # (offset=20 / limit=50) + 1 = 1
        assert data["page_size"] == 50
        assert data["has_next"] is True

    def test_list_agents_with_sorting(self, client, mock_query_port, sample_agent_info):
        """Test agents listing with sorting."""
        # Arrange
        from codetoreum.ports.input.agent_query import AgentListResult

        mock_query_port._list_agents.return_value = AgentListResult(
            agents=[sample_agent_info],
            total_count=1,
            offset=0,
            limit=20,
            has_next=False,
        )

        # Act
        response = client.get("/api/v2/agents?sort_by=name&sort_order=asc")

        # Assert
        assert response.status_code == 200

        # Verify sorting was applied
        mock_query_port._list_agents.assert_called_once()
        call_args = mock_query_port._list_agents.call_args[0]
        pagination = call_args[1]
        assert pagination.sort_by == AgentSortField.NAME
        assert pagination.sort_order == SortOrder.ASC

    def test_list_agents_with_invalid_sort_field(self, client):
        """Test agents listing with invalid sort field."""
        # Act
        response = client.get("/api/v2/agents?sort_by=invalid_field")

        # Assert
        assert response.status_code == 400
        data = response.json()
        assert "Invalid sort field" in data["detail"]

    def test_list_agents_empty_result(self, client, mock_query_port):
        """Test agents listing with no results."""
        # Arrange
        from codetoreum.ports.input.agent_query import AgentListResult

        mock_query_port._list_agents.return_value = AgentListResult(
            agents=[],
            total_count=0,
            offset=0,
            limit=20,
            has_next=False,
        )

        # Act
        response = client.get("/api/v2/agents")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 0
        assert len(data["agents"]) == 0


class TestGetAgent:
    """Tests for GET /api/v2/agents/{id} endpoint."""

    def test_get_agent_success(self, client, mock_query_port, sample_agent_info):
        """Test successful agent retrieval."""
        # Arrange
        mock_query_port._get_agent.return_value = sample_agent_info

        # Act
        response = client.get("/api/v2/agents/agent-123")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "agent-123"
        assert data["name"] == "test-agent"
        assert data["display_name"] == "Test Agent"
        assert data["agent_type"] == "maker"
        assert "code_review" in data["capabilities"]
        assert data["capabilities"]["code_review"]["proficiency"] == 0.9

    def test_get_agent_with_stats(self, client, mock_query_port, sample_agent_info):
        """Test agent retrieval with execution stats."""
        # Arrange
        mock_query_port._get_agent.return_value = sample_agent_info

        # Act
        response = client.get("/api/v2/agents/agent-123?include_stats=true")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "agent-123"
        assert "execution_stats" in data
        assert data["execution_stats"]["total_executions"] == 10
        assert data["execution_stats"]["successful_executions"] == 8

    def test_get_agent_without_stats(self, client, mock_query_port, sample_agent_info):
        """Test agent retrieval without execution stats."""
        # Arrange
        agent_info_no_stats = AgentInfo(
            id=sample_agent_info.id,
            name=sample_agent_info.name,
            display_name=sample_agent_info.display_name,
            agent_type=sample_agent_info.agent_type,
            role_description=sample_agent_info.role_description,
            model=sample_agent_info.model,
            timeout_seconds=sample_agent_info.timeout_seconds,
            max_retries=sample_agent_info.max_retries,
            requires_docker=sample_agent_info.requires_docker,
            requires_dev_container=sample_agent_info.requires_dev_container,
            makes_code_changes=sample_agent_info.makes_code_changes,
            filesystem_write_allowed=sample_agent_info.filesystem_write_allowed,
            mcp_servers=sample_agent_info.mcp_servers,
            created_at=sample_agent_info.created_at,
            updated_at=sample_agent_info.updated_at,
            capabilities=sample_agent_info.capabilities,
            environment_variables=None,
            execution_stats=None,
        )
        mock_query_port._get_agent.return_value = agent_info_no_stats

        # Act
        response = client.get("/api/v2/agents/agent-123?include_stats=false")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "agent-123"
        assert data.get("execution_stats") is None

    def test_get_agent_not_found(self, client, mock_query_port):
        """Test agent retrieval when not found."""
        # Arrange
        mock_query_port._get_agent.side_effect = ValueError(
            "Agent with ID 'agent-nonexistent' not found"
        )

        # Act
        response = client.get("/api/v2/agents/agent-nonexistent")

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert "Agent not found" in data["detail"]


class TestCreateAgent:
    """Tests for POST /api/v2/agents endpoint."""

    def test_create_agent_success(
        self, client, mock_command_port, mock_query_port, sample_agent, sample_agent_info
    ):
        """Test successful agent creation."""
        # Arrange
        mock_command_port._create_agent.return_value = sample_agent
        mock_query_port._get_agent.return_value = sample_agent_info

        request_data = {
            "name": "test-agent",
            "display_name": "Test Agent",
            "agent_type": "maker",
            "role_description": "A test agent for testing",
            "model": "claude-sonnet-4",
            "capabilities": {
                "code_review": {
                    "skill": "code_review",
                    "proficiency": 0.9,
                    "description": "Code review skill",
                },
                "testing": {
                    "skill": "testing",
                    "proficiency": 0.8,
                    "description": "Testing skill",
                },
            },
            "timeout_seconds": 300,
            "max_retries": 3,
            "requires_docker": True,
            "makes_code_changes": True,
            "mcp_servers": ["artifacts", "logging"],
        }

        # Act
        response = client.post("/api/v2/agents", json=request_data)

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "agent-123"
        assert data["name"] == "test-agent"
        assert data["agent_type"] == "maker"

        # Verify command port was called
        mock_command_port._create_agent.assert_called_once()
        call_args = mock_command_port._create_agent.call_args[0][0]
        assert isinstance(call_args, CreateAgentCommand)
        assert call_args.name == "test-agent"

    def test_create_agent_with_defaults(
        self, client, mock_command_port, mock_query_port, sample_agent, sample_agent_info
    ):
        """Test agent creation with default values."""
        # Arrange
        mock_command_port._create_agent.return_value = sample_agent
        mock_query_port._get_agent.return_value = sample_agent_info

        request_data = {
            "name": "test-agent",
            "display_name": "Test Agent",
            "agent_type": "maker",
            "role_description": "A test agent for testing",
            "model": "claude-sonnet-4",
            "capabilities": {
                "code_review": {
                    "skill": "code_review",
                    "proficiency": 0.9,
                },
            },
        }

        # Act
        response = client.post("/api/v2/agents", json=request_data)

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "test-agent"

    def test_create_agent_validation_error_invalid_name(self, client):
        """Test agent creation with invalid name."""
        # Arrange
        request_data = {
            "name": "Test Agent!",  # Invalid: contains spaces and special chars
            "display_name": "Test Agent",
            "agent_type": "maker",
            "role_description": "A test agent for testing",
            "model": "claude-sonnet-4",
            "capabilities": {
                "code_review": {
                    "skill": "code_review",
                    "proficiency": 0.9,
                },
            },
        }

        # Act
        response = client.post("/api/v2/agents", json=request_data)

        # Assert
        assert response.status_code == 422  # Validation error

    def test_create_agent_validation_error_invalid_type(self, client):
        """Test agent creation with invalid agent type."""
        # Arrange
        request_data = {
            "name": "test-agent",
            "display_name": "Test Agent",
            "agent_type": "invalid_type",
            "role_description": "A test agent for testing",
            "model": "claude-sonnet-4",
            "capabilities": {
                "code_review": {
                    "skill": "code_review",
                    "proficiency": 0.9,
                },
            },
        }

        # Act
        response = client.post("/api/v2/agents", json=request_data)

        # Assert
        assert response.status_code == 422  # Validation error

    def test_create_agent_already_exists(
        self, client, mock_command_port, mock_query_port
    ):
        """Test agent creation when name already exists."""
        # Arrange
        mock_command_port._create_agent.side_effect = ValueError(
            "Agent with name 'test-agent' already exists"
        )

        request_data = {
            "name": "test-agent",
            "display_name": "Test Agent",
            "agent_type": "maker",
            "role_description": "A test agent for testing",
            "model": "claude-sonnet-4",
            "capabilities": {
                "code_review": {
                    "skill": "code_review",
                    "proficiency": 0.9,
                },
            },
        }

        # Act
        response = client.post("/api/v2/agents", json=request_data)

        # Assert
        assert response.status_code == 400
        data = response.json()
        assert "already exists" in data["detail"]

    def test_create_agent_invalid_proficiency(self, client):
        """Test agent creation with invalid proficiency level."""
        # Arrange
        request_data = {
            "name": "test-agent",
            "display_name": "Test Agent",
            "agent_type": "maker",
            "role_description": "A test agent for testing",
            "model": "claude-sonnet-4",
            "capabilities": {
                "code_review": {
                    "skill": "code_review",
                    "proficiency": 1.5,  # Invalid: > 1.0
                },
            },
        }

        # Act
        response = client.post("/api/v2/agents", json=request_data)

        # Assert
        assert response.status_code == 422  # Validation error


class TestUpdateAgent:
    """Tests for PUT /api/v2/agents/{id} endpoint."""

    def test_update_agent_success(
        self, client, mock_command_port, mock_query_port, sample_agent, sample_agent_info
    ):
        """Test successful agent update."""
        # Arrange
        mock_command_port._update_agent.return_value = sample_agent
        mock_query_port._get_agent.return_value = sample_agent_info

        request_data = {
            "display_name": "Updated Test Agent",
            "timeout_seconds": 600,
        }

        # Act
        response = client.put("/api/v2/agents/agent-123", json=request_data)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "agent-123"

        # Verify command port was called
        mock_command_port._update_agent.assert_called_once()
        call_args = mock_command_port._update_agent.call_args[0][0]
        assert isinstance(call_args, UpdateAgentCommand)
        assert call_args.agent_id == "agent-123"

    def test_update_agent_not_found(self, client, mock_command_port):
        """Test agent update when not found."""
        # Arrange
        mock_command_port._update_agent.side_effect = ValueError(
            "Agent with ID 'agent-nonexistent' not found"
        )

        request_data = {
            "display_name": "Updated Test Agent",
        }

        # Act
        response = client.put("/api/v2/agents/agent-nonexistent", json=request_data)

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert "Agent not found" in data["detail"]

    def test_update_agent_invalid_timeout(self, client):
        """Test agent update with invalid timeout."""
        # Arrange
        request_data = {
            "timeout_seconds": 10000,  # Invalid: > 7200
        }

        # Act
        response = client.put("/api/v2/agents/agent-123", json=request_data)

        # Assert
        assert response.status_code == 422  # Validation error


class TestAgentCapabilityManagement:
    """Tests for agent capability management endpoints."""

    def test_add_capability_success(
        self, client, mock_command_port, mock_query_port, sample_agent, sample_agent_info
    ):
        """Test successful capability addition."""
        # Arrange
        mock_command_port._add_capability.return_value = sample_agent
        mock_query_port._get_agent.return_value = sample_agent_info

        request_data = {
            "capability": {
                "skill": "debugging",
                "proficiency": 0.85,
                "description": "Debugging skill",
            }
        }

        # Act
        response = client.post("/api/v2/agents/agent-123/capabilities", json=request_data)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "agent-123"

        # Verify command port was called
        mock_command_port._add_capability.assert_called_once()
        call_args = mock_command_port._add_capability.call_args[0][0]
        assert isinstance(call_args, AddAgentCapabilityCommand)
        assert call_args.agent_id == "agent-123"
        assert call_args.capability.skill == "debugging"

    def test_add_capability_already_exists(self, client, mock_command_port):
        """Test capability addition when capability already exists."""
        # Arrange
        mock_command_port._add_capability.side_effect = ValueError(
            "Capability 'debugging' already exists for agent"
        )

        request_data = {
            "capability": {
                "skill": "debugging",
                "proficiency": 0.85,
            }
        }

        # Act
        response = client.post("/api/v2/agents/agent-123/capabilities", json=request_data)

        # Assert
        assert response.status_code == 400
        data = response.json()
        assert "already exists" in data["detail"]

    def test_remove_capability_success(
        self, client, mock_command_port, mock_query_port, sample_agent, sample_agent_info
    ):
        """Test successful capability removal."""
        # Arrange
        mock_command_port._remove_capability.return_value = sample_agent
        mock_query_port._get_agent.return_value = sample_agent_info

        # Act
        response = client.delete("/api/v2/agents/agent-123/capabilities/testing")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "agent-123"

        # Verify command port was called
        mock_command_port._remove_capability.assert_called_once()
        call_args = mock_command_port._remove_capability.call_args[0][0]
        assert isinstance(call_args, RemoveAgentCapabilityCommand)
        assert call_args.agent_id == "agent-123"
        assert call_args.skill == "testing"

    def test_remove_capability_not_found(self, client, mock_command_port):
        """Test capability removal when capability not found."""
        # Arrange
        mock_command_port._remove_capability.side_effect = ValueError(
            "Capability 'nonexistent' not found"
        )

        # Act
        response = client.delete("/api/v2/agents/agent-123/capabilities/nonexistent")

        # Assert
        assert response.status_code == 400
        data = response.json()
        assert "Capability not found" in data["detail"]

    def test_remove_last_capability(self, client, mock_command_port):
        """Test removing the last capability from an agent."""
        # Arrange
        mock_command_port._remove_capability.side_effect = ValueError(
            "Cannot remove last capability from agent"
        )

        # Act
        response = client.delete("/api/v2/agents/agent-123/capabilities/code_review")

        # Assert
        assert response.status_code == 400
        data = response.json()
        assert "Cannot remove last capability" in data["detail"]

    def test_update_capability_success(
        self, client, mock_command_port, mock_query_port, sample_agent, sample_agent_info
    ):
        """Test successful capability proficiency update."""
        # Arrange
        mock_command_port._update_capability.return_value = sample_agent
        mock_query_port._get_agent.return_value = sample_agent_info

        request_data = {
            "proficiency": 0.95,
        }

        # Act
        response = client.patch(
            "/api/v2/agents/agent-123/capabilities/code_review", json=request_data
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "agent-123"

        # Verify command port was called
        mock_command_port._update_capability.assert_called_once()
        call_args = mock_command_port._update_capability.call_args[0][0]
        assert isinstance(call_args, UpdateAgentCapabilityCommand)
        assert call_args.agent_id == "agent-123"
        assert call_args.skill == "code_review"
        assert call_args.proficiency == 0.95

    def test_update_capability_not_found(self, client, mock_command_port):
        """Test capability update when capability not found."""
        # Arrange
        mock_command_port._update_capability.side_effect = ValueError(
            "Capability 'nonexistent' not found"
        )

        request_data = {
            "proficiency": 0.95,
        }

        # Act
        response = client.patch(
            "/api/v2/agents/agent-123/capabilities/nonexistent", json=request_data
        )

        # Assert
        assert response.status_code == 400
        data = response.json()
        assert "Capability not found" in data["detail"]


class TestAgentMcpServerManagement:
    """Tests for agent MCP server management endpoints."""

    def test_add_mcp_server_success(
        self, client, mock_command_port, mock_query_port, sample_agent, sample_agent_info
    ):
        """Test successful MCP server addition."""
        # Arrange
        mock_command_port._add_mcp_server.return_value = sample_agent
        mock_query_port._get_agent.return_value = sample_agent_info

        request_data = {
            "server_name": "new-server",
        }

        # Act
        response = client.post("/api/v2/agents/agent-123/mcp-servers", json=request_data)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "agent-123"

        # Verify command port was called
        mock_command_port._add_mcp_server.assert_called_once()
        call_args = mock_command_port._add_mcp_server.call_args[0][0]
        assert isinstance(call_args, AddMcpServerCommand)
        assert call_args.agent_id == "agent-123"
        assert call_args.server_name == "new-server"

    def test_add_mcp_server_already_exists(self, client, mock_command_port):
        """Test MCP server addition when server already configured."""
        # Arrange
        mock_command_port._add_mcp_server.side_effect = ValueError(
            "MCP server 'artifacts' already configured"
        )

        request_data = {
            "server_name": "artifacts",
        }

        # Act
        response = client.post("/api/v2/agents/agent-123/mcp-servers", json=request_data)

        # Assert
        assert response.status_code == 400
        data = response.json()
        assert "already configured" in data["detail"]

    def test_remove_mcp_server_success(
        self, client, mock_command_port, mock_query_port, sample_agent, sample_agent_info
    ):
        """Test successful MCP server removal."""
        # Arrange
        mock_command_port._remove_mcp_server.return_value = sample_agent
        mock_query_port._get_agent.return_value = sample_agent_info

        # Act
        response = client.delete("/api/v2/agents/agent-123/mcp-servers/logging")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "agent-123"

        # Verify command port was called
        mock_command_port._remove_mcp_server.assert_called_once()
        call_args = mock_command_port._remove_mcp_server.call_args[0][0]
        assert isinstance(call_args, RemoveMcpServerCommand)
        assert call_args.agent_id == "agent-123"
        assert call_args.server_name == "logging"

    def test_remove_mcp_server_not_found(self, client, mock_command_port):
        """Test MCP server removal when server not configured."""
        # Arrange
        mock_command_port._remove_mcp_server.side_effect = ValueError(
            "MCP server 'nonexistent' not configured"
        )

        # Act
        response = client.delete("/api/v2/agents/agent-123/mcp-servers/nonexistent")

        # Assert
        assert response.status_code == 400
        data = response.json()
        assert "not configured" in data["detail"]


class TestDeleteAgent:
    """Tests for DELETE /api/v2/agents/{id} endpoint."""

    def test_delete_agent_success(self, client, mock_command_port):
        """Test successful agent deletion."""
        # Arrange
        from codetoreum.ports.input.agent_command import AgentCommandResult

        mock_command_port._delete_agent.return_value = AgentCommandResult(
            success=True,
            agent_id="agent-123",
            message="Agent deleted successfully",
        )

        # Act
        response = client.delete("/api/v2/agents/agent-123")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["agent_id"] == "agent-123"
        assert data["message"] == "Agent deleted successfully"

    def test_delete_agent_not_found(self, client, mock_command_port):
        """Test agent deletion when not found."""
        # Arrange
        mock_command_port._delete_agent.side_effect = ValueError(
            "Agent with ID 'agent-nonexistent' not found"
        )

        # Act
        response = client.delete("/api/v2/agents/agent-nonexistent")

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert "Agent not found" in data["detail"]
