"""Unit tests for Agent entity."""

import pytest

from codetoreum.domain import (
    Agent,
    AgentCapability,
    AgentType,
    DomainError,
)
from codetoreum.domain.coding_agent_types import AgentInvocationConfig, InvocationMode
from codetoreum.domain.events.agent_events import (
    AgentCapabilityAddedEvent,
    AgentCapabilityRemovedEvent,
    AgentCapabilityUpdatedEvent,
    AgentConstraintsUpdatedEvent,
    AgentCreatedEvent,
    AgentMcpServerAddedEvent,
    AgentMcpServerRemovedEvent,
    AgentModelUpdatedEvent,
    AgentTimeoutUpdatedEvent,
)


def _test_inv(
    model: str = "claude-sonnet-4-5",
    timeout_seconds: int = 300,
    requires_docker: bool = True,
) -> AgentInvocationConfig:
    """Build an AgentInvocationConfig for tests."""
    return AgentInvocationConfig(
        mode=InvocationMode.CONTAINERIZED if requires_docker else InvocationMode.HOST,
        model=model,
        timeout_seconds=timeout_seconds,
        mode_config={"image": "codetoreum-agent:latest"} if requires_docker else {},
    )


class TestAgentCapability:
    """Test AgentCapability value object."""

    def test_create_capability(self):
        """Test creating capability with valid proficiency."""
        capability = AgentCapability("python", 0.9, "Python programming")

        assert capability.skill == "python"
        assert capability.proficiency == 0.9
        assert capability.description == "Python programming"

    def test_create_capability_without_description(self):
        """Test creating capability without description."""
        capability = AgentCapability("python", 0.9)

        assert capability.description is None

    def test_capability_proficiency_too_low_raises_error(self):
        """Test that proficiency < 0.0 raises error."""
        with pytest.raises(DomainError) as exc:
            AgentCapability("python", -0.1)
        assert "between 0.0 and 1.0" in str(exc.value)

    def test_capability_proficiency_too_high_raises_error(self):
        """Test that proficiency > 1.0 raises error."""
        with pytest.raises(DomainError) as exc:
            AgentCapability("python", 1.1)
        assert "between 0.0 and 1.0" in str(exc.value)

    def test_capability_edge_cases(self):
        """Test edge case proficiency values."""
        cap_zero = AgentCapability("skill", 0.0)
        cap_one = AgentCapability("skill", 1.0)

        assert cap_zero.proficiency == 0.0
        assert cap_one.proficiency == 1.0


class TestAgentCreation:
    """Test agent creation and validation."""

    def test_create_agent(self):
        """Test creating agent with valid data."""
        capabilities = {
            "python": AgentCapability("python", 0.9),
            "testing": AgentCapability("testing", 0.8),
        }

        agent = Agent.create(
            name="senior_engineer",
            display_name="Senior Software Engineer",
            agent_type=AgentType.MAKER,
            role_description="Implements features and fixes bugs",
            capabilities=capabilities,
            invocation=_test_inv(model="claude-sonnet-4-5", timeout_seconds=300, requires_docker=True),
        )

        assert agent.id is not None
        assert agent.name == "senior_engineer"
        assert agent.display_name == "Senior Software Engineer"
        assert agent.agent_type == AgentType.MAKER
        assert agent.invocation.model == "claude-sonnet-4-5"
        assert len(agent.capabilities) == 2
        assert agent.invocation.timeout_seconds == 300
        assert agent.max_retries == 3
        assert agent.invocation.mode == InvocationMode.CONTAINERIZED
        assert agent.mcp_servers == []

    def test_create_agent_with_all_options(self):
        """Test creating agent with all optional parameters."""
        capabilities = {"python": AgentCapability("python", 0.9)}

        agent = Agent.create(
            name="reviewer",
            display_name="Code Reviewer",
            agent_type=AgentType.REVIEWER,
            role_description="Reviews code",
            capabilities=capabilities,
            max_retries=5,
            requires_dev_container=False,
            makes_code_changes=False,
            filesystem_write_allowed=False,
            mcp_servers=["artifacts", "logging"],
            invocation=_test_inv(model="claude-sonnet-4-5", timeout_seconds=600, requires_docker=False),
        )

        assert agent.invocation.timeout_seconds == 600
        assert agent.max_retries == 5
        assert agent.invocation.mode == InvocationMode.HOST
        assert agent.makes_code_changes is False
        assert agent.mcp_servers == ["artifacts", "logging"]

    def test_create_emits_event(self):
        """Test that creation emits AgentCreated event."""
        capabilities = {"python": AgentCapability("python", 0.9)}

        agent = Agent.create(
            name="engineer",
            display_name="Engineer",
            agent_type=AgentType.MAKER,
            role_description="Codes",
            capabilities=capabilities,
            invocation=_test_inv(model="claude-sonnet-4-5", timeout_seconds=300, requires_docker=True),
        )

        events = agent.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], AgentCreatedEvent)
        assert events[0].name == "engineer"

    def test_create_with_empty_name_raises_error(self):
        """Test that empty name raises error."""
        capabilities = {"python": AgentCapability("python", 0.9)}

        with pytest.raises(DomainError) as exc:
            Agent.create(
                name="",
                display_name="Engineer",
                agent_type=AgentType.MAKER,
                role_description="Codes",
                capabilities=capabilities,
                invocation=_test_inv(model="claude-sonnet-4-5", timeout_seconds=300, requires_docker=True),
            )
        assert "non-empty name" in str(exc.value)

    def test_create_with_no_capabilities_raises_error(self):
        """Test that no capabilities raises error."""
        with pytest.raises(DomainError) as exc:
            Agent.create(
                name="engineer",
                display_name="Engineer",
                agent_type=AgentType.MAKER,
                role_description="Codes",
                capabilities={},
                invocation=_test_inv(model="claude-sonnet-4-5", timeout_seconds=300, requires_docker=True),
            )
        assert "at least one capability" in str(exc.value)

    def test_create_with_zero_timeout_raises_error(self):
        """Test that zero timeout raises error.

        Validation now happens at ``AgentInvocationConfig`` construction
        (a value object), so the exception is ``ValueError`` rather than
        ``DomainError`` — the timeout invariant still holds.
        """
        with pytest.raises(ValueError, match="timeout_seconds must be a positive integer"):
            _test_inv(model="claude-sonnet-4-5", timeout_seconds=0, requires_docker=True)

    def test_create_with_negative_retries_raises_error(self):
        """Test that negative retries raises error."""
        capabilities = {"python": AgentCapability("python", 0.9)}

        with pytest.raises(DomainError) as exc:
            Agent.create(
                name="engineer",
                display_name="Engineer",
                agent_type=AgentType.MAKER,
                role_description="Codes",
                capabilities=capabilities,
                max_retries=-1,
                invocation=_test_inv(model="claude-sonnet-4-5", timeout_seconds=300, requires_docker=True),
            )
        assert "non-negative" in str(exc.value)

    def test_create_with_invalid_temperature_below_minimum_raises_error(self):
        """Test that temperature < 0.0 raises error."""
        capabilities = {"python": AgentCapability("python", 0.9)}

        with pytest.raises(DomainError) as exc:
            Agent.create(
                name="engineer",
                display_name="Engineer",
                agent_type=AgentType.MAKER,
                role_description="Codes",
                capabilities=capabilities,
                temperature=-0.1,
                invocation=_test_inv(model="claude-sonnet-4-5", timeout_seconds=300, requires_docker=True),
            )
        assert "between 0.0 and 2.0" in str(exc.value)

    def test_create_with_invalid_temperature_above_maximum_raises_error(self):
        """Test that temperature > 2.0 raises error."""
        capabilities = {"python": AgentCapability("python", 0.9)}

        with pytest.raises(DomainError) as exc:
            Agent.create(
                name="engineer",
                display_name="Engineer",
                agent_type=AgentType.MAKER,
                role_description="Codes",
                capabilities=capabilities,
                temperature=2.1,
                invocation=_test_inv(model="claude-sonnet-4-5", timeout_seconds=300, requires_docker=True),
            )
        assert "between 0.0 and 2.0" in str(exc.value)

    def test_create_with_valid_temperature_boundaries(self):
        """Test that valid temperature boundaries are accepted."""
        capabilities = {"python": AgentCapability("python", 0.9)}

        # Test minimum boundary
        agent_min = Agent.create(
            name="engineer",
            display_name="Engineer",
            agent_type=AgentType.MAKER,
            role_description="Codes",
            capabilities=capabilities,
            temperature=0.0,
            invocation=_test_inv(model="claude-sonnet-4-5", timeout_seconds=300, requires_docker=True),
        )
        assert agent_min.temperature == 0.0

        # Test maximum boundary
        agent_max = Agent.create(
            name="engineer",
            display_name="Engineer",
            agent_type=AgentType.MAKER,
            role_description="Codes",
            capabilities=capabilities,
            temperature=2.0,
            invocation=_test_inv(model="claude-sonnet-4-5", timeout_seconds=300, requires_docker=True),
        )
        assert agent_max.temperature == 2.0

    def test_create_with_zero_max_tokens_raises_error(self):
        """Test that max_tokens <= 0 raises error."""
        capabilities = {"python": AgentCapability("python", 0.9)}

        with pytest.raises(DomainError) as exc:
            Agent.create(
                name="engineer",
                display_name="Engineer",
                agent_type=AgentType.MAKER,
                role_description="Codes",
                capabilities=capabilities,
                max_tokens=0,
                invocation=_test_inv(model="claude-sonnet-4-5", timeout_seconds=300, requires_docker=True),
            )
        assert "Max tokens must be positive" in str(exc.value)

    def test_create_with_negative_max_tokens_raises_error(self):
        """Test that max_tokens < 0 raises error."""
        capabilities = {"python": AgentCapability("python", 0.9)}

        with pytest.raises(DomainError) as exc:
            Agent.create(
                name="engineer",
                display_name="Engineer",
                agent_type=AgentType.MAKER,
                role_description="Codes",
                capabilities=capabilities,
                max_tokens=-1024,
                invocation=_test_inv(model="claude-sonnet-4-5", timeout_seconds=300, requires_docker=True),
            )
        assert "Max tokens must be positive" in str(exc.value)


class TestAgentCapabilityManagement:
    """Test capability management methods."""

    def test_add_capability(self):
        """Test adding capability to agent."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )
        agent.clear_events()

        new_capability = AgentCapability("javascript", 0.7)
        agent.add_capability(new_capability)

        assert "javascript" in agent.capabilities
        assert agent.capabilities["javascript"].proficiency == 0.7

        events = agent.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], AgentCapabilityAddedEvent)
        assert events[0].skill == "javascript"

    def test_add_duplicate_capability_raises_error(self):
        """Test that adding duplicate capability raises error."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )

        with pytest.raises(DomainError) as exc:
            agent.add_capability(AgentCapability("python", 0.95))
        assert "already has capability" in str(exc.value)

    def test_remove_capability(self):
        """Test removing capability from agent."""
        capabilities = {
            "python": AgentCapability("python", 0.9),
            "testing": AgentCapability("testing", 0.8),
        }
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )
        agent.clear_events()

        agent.remove_capability("testing")

        assert "testing" not in agent.capabilities
        assert "python" in agent.capabilities

        events = agent.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], AgentCapabilityRemovedEvent)
        assert events[0].skill == "testing"

    def test_remove_nonexistent_capability_raises_error(self):
        """Test that removing nonexistent capability raises error."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )

        with pytest.raises(DomainError) as exc:
            agent.remove_capability("javascript")
        assert "does not have capability" in str(exc.value)

    def test_remove_last_capability_raises_error(self):
        """Test that removing last capability raises error."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )

        with pytest.raises(DomainError) as exc:
            agent.remove_capability("python")
        assert "Cannot remove last capability" in str(exc.value)

    def test_update_capability_proficiency(self):
        """Test updating capability proficiency."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )
        agent.clear_events()

        agent.update_capability_proficiency("python", 0.95)

        assert agent.capabilities["python"].proficiency == 0.95

        events = agent.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], AgentCapabilityUpdatedEvent)
        assert events[0].old_proficiency == 0.9
        assert events[0].new_proficiency == 0.95

    def test_update_proficiency_for_nonexistent_capability_raises_error(self):
        """Test that updating nonexistent capability raises error."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )

        with pytest.raises(DomainError) as exc:
            agent.update_capability_proficiency("javascript", 0.8)
        assert "does not have capability" in str(exc.value)

    def test_update_proficiency_with_invalid_value_raises_error(self):
        """Test that invalid proficiency value raises error."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )

        with pytest.raises(DomainError) as exc:
            agent.update_capability_proficiency("python", 1.5)
        assert "between 0.0 and 1.0" in str(exc.value)


class TestAgentConfigurationManagement:
    """Test configuration management methods."""

    def test_update_model(self):
        """Test updating agent model."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="claude-sonnet-4-5", timeout_seconds=300, requires_docker=True),
        )
        agent.clear_events()

        agent.update_model("claude-opus-4")

        assert agent.invocation.model == "claude-opus-4"

        events = agent.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], AgentModelUpdatedEvent)
        assert events[0].old_model == "claude-sonnet-4-5"
        assert events[0].new_model == "claude-opus-4"

    def test_update_model_to_empty_raises_error(self):
        """Test that updating to empty model raises error."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )

        with pytest.raises(DomainError) as exc:
            agent.update_model("")
        assert "cannot be empty" in str(exc.value)

    def test_update_timeout(self):
        """Test updating agent timeout."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )
        agent.clear_events()

        agent.update_timeout(600)

        assert agent.invocation.timeout_seconds == 600

        events = agent.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], AgentTimeoutUpdatedEvent)
        assert events[0].old_timeout == 300
        assert events[0].new_timeout == 600

    def test_update_timeout_to_zero_raises_error(self):
        """Test that zero timeout raises error."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )

        with pytest.raises(DomainError) as exc:
            agent.update_timeout(0)
        assert "must be positive" in str(exc.value)

    def test_update_constraints(self):
        """Test updating agent constraints.

        ``requires_docker`` is no longer a separate field — to change the
        execution mode, rebuild the invocation block directly. ``update_constraints``
        only handles dev_container / code_changes / fs_writes now.
        """
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )
        agent.clear_events()

        # Mode switch is now done by rebuilding the invocation block.
        agent.invocation = AgentInvocationConfig(
            mode=InvocationMode.HOST,
            model=agent.invocation.model,
            timeout_seconds=agent.invocation.timeout_seconds,
            mode_config={},
        )
        agent.update_constraints(makes_code_changes=True, filesystem_write_allowed=False)

        assert agent.invocation.mode == InvocationMode.HOST
        assert agent.makes_code_changes is True
        assert agent.filesystem_write_allowed is False
        assert agent.requires_dev_container is False  # Unchanged (default is False)

        events = agent.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], AgentConstraintsUpdatedEvent)

    def test_update_constraints_partial(self):
        """Test updating only some constraints."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )
        agent.clear_events()

        agent.update_constraints(makes_code_changes=True)

        assert agent.makes_code_changes is True
        assert agent.invocation.mode == InvocationMode.CONTAINERIZED  # Unchanged


class TestAgentMcpServerManagement:
    """Test MCP server management methods."""

    def test_add_mcp_server(self):
        """Test adding MCP server to agent."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )
        agent.clear_events()

        agent.add_mcp_server("artifacts")

        assert "artifacts" in agent.mcp_servers

        events = agent.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], AgentMcpServerAddedEvent)
        assert events[0].server_name == "artifacts"

    def test_add_duplicate_mcp_server_raises_error(self):
        """Test that adding duplicate MCP server raises error."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
            mcp_servers=["artifacts"],
        )

        with pytest.raises(DomainError) as exc:
            agent.add_mcp_server("artifacts")
        assert "already configured" in str(exc.value)

    def test_remove_mcp_server(self):
        """Test removing MCP server from agent."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
            mcp_servers=["artifacts", "logging"],
        )
        agent.clear_events()

        agent.remove_mcp_server("artifacts")

        assert "artifacts" not in agent.mcp_servers
        assert "logging" in agent.mcp_servers

        events = agent.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], AgentMcpServerRemovedEvent)

    def test_remove_nonexistent_mcp_server_raises_error(self):
        """Test that removing nonexistent MCP server raises error."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )

        with pytest.raises(DomainError) as exc:
            agent.remove_mcp_server("artifacts")
        assert "not configured" in str(exc.value)


class TestAgentQueryMethods:
    """Test query methods."""

    def test_has_capability_true(self):
        """Test has_capability returns True when agent has skill."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )

        assert agent.has_capability("python") is True

    def test_has_capability_false(self):
        """Test has_capability returns False when agent lacks skill."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )

        assert agent.has_capability("javascript") is False

    def test_has_capability_with_min_proficiency(self):
        """Test has_capability with minimum proficiency threshold."""
        capabilities = {"python": AgentCapability("python", 0.7)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )

        assert agent.has_capability("python", 0.6) is True
        assert agent.has_capability("python", 0.7) is True
        assert agent.has_capability("python", 0.8) is False

    def test_get_capability_score_existing(self):
        """Test get_capability_score for existing capability."""
        capabilities = {"python": AgentCapability("python", 0.85)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )

        assert agent.get_capability_score("python") == 0.85

    def test_get_capability_score_nonexistent(self):
        """Test get_capability_score for nonexistent capability returns 0.0."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )

        assert agent.get_capability_score("javascript") == 0.0

    def test_can_execute_in_environment_with_docker(self):
        """Test can_execute_in_environment with Docker available."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )

        assert agent.can_execute_in_environment(has_docker=True, has_dev_container=False) is True
        assert agent.can_execute_in_environment(has_docker=False, has_dev_container=False) is False

    def test_can_execute_in_environment_with_dev_container(self):
        """Test can_execute_in_environment with dev container requirement."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
            requires_dev_container=True,
        )

        assert agent.can_execute_in_environment(has_docker=True, has_dev_container=True) is True
        assert agent.can_execute_in_environment(has_docker=True, has_dev_container=False) is False

    def test_is_maker_agent(self):
        """Test is_maker_agent returns True for maker."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )

        assert agent.is_maker_agent() is True
        assert agent.is_reviewer_agent() is False

    def test_is_reviewer_agent(self):
        """Test is_reviewer_agent returns True for reviewer."""
        capabilities = {"code_review": AgentCapability("code_review", 0.9)}
        agent = Agent.create(
            "reviewer",
            "Reviewer",
            AgentType.REVIEWER,
            "Reviews",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )

        assert agent.is_reviewer_agent() is True
        assert agent.is_maker_agent() is False


class TestAgentEventManagement:
    """Test event management."""

    def test_get_pending_events(self):
        """Test getting pending events."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )

        events = agent.get_pending_events()

        assert len(events) == 1
        assert isinstance(events[0], AgentCreatedEvent)

    def test_clear_events(self):
        """Test clearing pending events."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )

        agent.clear_events()

        assert len(agent.get_pending_events()) == 0

    def test_get_pending_events_returns_copy(self):
        """Test that get_pending_events returns a copy."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )

        events = agent.get_pending_events()
        events.clear()

        # Original events should still be there
        assert len(agent.get_pending_events()) == 1

    def test_version_tracking(self):
        """Test that version is tracked correctly."""
        capabilities = {"python": AgentCapability("python", 0.9)}
        agent = Agent.create(
            "engineer",
            "Engineer",
            AgentType.MAKER,
            "Codes",
            capabilities,
            invocation=_test_inv(model="model", timeout_seconds=300, requires_docker=True),
        )
        assert agent._version == 0

        agent.add_capability(AgentCapability("javascript", 0.8))
        assert agent._version == 1

        agent.update_model("new-model")
        assert agent._version == 2

        agent.update_timeout(600)
        assert agent._version == 3
