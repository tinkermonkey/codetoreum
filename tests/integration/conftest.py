"""Common test fixtures and utilities for integration tests."""

import os

import pytest

from codetoreum.domain.board_workflow_template import BoardWorkflowTemplate
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService

# Set placeholder environment variables for integration tests.
# These match the defaults in Dockerfile.agent (Stage 5b) and allow tests to run
# without requiring manual env setup. Production tests that need real credentials
# should override these via actual environment variables or pytest marks.
# Uses `or` instead of setdefault to also handle vars set to empty string.
_INTEGRATION_TEST_ENV_DEFAULTS = {
    "ANTHROPIC_API_KEY": "sk-ant-test-placeholder",
    "GITHUB_APP_ID": "test-app-id-placeholder",
    "GITHUB_PRIVATE_KEY_PATH": "/dev/null",
    "GITHUB_WEBHOOK_SECRET": "test-webhook-secret-placeholder",
    "CODETOREUM_AUTH_SECRET_KEY": "test-jwt-secret-not-for-production-use",
    "ELASTICSEARCH_URL": "http://localhost:9200",
    "GITHUB_TOKEN": "ghp_test_placeholder",
    "REDIS_URL": "redis://localhost:6379/0",
}
for _var, _default in _INTEGRATION_TEST_ENV_DEFAULTS.items():
    if not os.environ.get(_var):
        os.environ[_var] = _default

# Set default timeout for all integration tests to prevent hanging
pytestmark = pytest.mark.timeout(30)


class MockWorkflowConfigService(IWorkflowConfigService):
    """Mock workflow config service for testing."""

    def __init__(self, template: BoardWorkflowTemplate):
        """Initialize with template."""
        self.template = template

    async def save_board_workflow_template(self, template: BoardWorkflowTemplate) -> None:
        """Save template."""
        self.template = template

    async def get_board_workflow_template(self, board_id: str) -> BoardWorkflowTemplate | None:
        """Get template by board ID."""
        if board_id == self.template.board_id:
            return self.template
        return None

    async def list_board_workflow_templates(self, project_id: str) -> list[BoardWorkflowTemplate]:
        """List templates for project."""
        if project_id == self.template.project_id:
            return [self.template]
        return []

    async def delete_board_workflow_template(self, board_id: str) -> None:
        """Delete template."""
        if board_id == self.template.board_id:
            self.template = None


@pytest.fixture
async def seeded_simulation_bootstrap(simulation_bootstrap, simulation_seeder):
    """
    Provide a simulation bootstrap with pre-seeded repair cycle agents.

    This fixture extends simulation_bootstrap by automatically seeding the
    agents required for repair cycle tests (senior_software_engineer, etc)
    and wiring the systemic analysis service to the repair cycle adapter.

    Yields:
        SimulationApplicationBootstrap instance with agents seeded and services wired
    """
    # Seed default project and agents required for repair cycles
    await simulation_seeder.create_project("repair-cycle-test")
    await simulation_seeder.create_agents(
        [
            {
                "name": "senior_software_engineer",
                "description": "Senior Software Engineer",
                "capabilities": ["code_generation", "testing", "debugging"],
                "agent_type": "maker",
            },
            {
                "name": "code_reviewer",
                "description": "Code Reviewer",
                "capabilities": ["review", "analysis"],
                "agent_type": "reviewer",
            },
        ]
    )

    # Wire systemic analysis service to repair cycle adapter for dispatch logic
    repair_cycle = simulation_bootstrap.adapters.repair_cycle_as_mock()
    repair_cycle.systemic_analysis_service = simulation_bootstrap.adapters.systemic_analysis_service

    return simulation_bootstrap
