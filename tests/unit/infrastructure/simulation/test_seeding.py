"""Unit tests for simulation data seeding."""

import pytest
from pathlib import Path
from datetime import datetime, timezone

from codetoreum.infrastructure.simulation import (
    SimulationApplicationBootstrap,
    SimulationDataSeeder,
    SimulationConfig,
    CreatedItems,
)
from codetoreum.domain.work_item import WorkItemPriority, WorkItemStatus
from codetoreum.ports.exceptions import ValidationError


class TestSimulationDataSeeder:
    """Test cases for SimulationDataSeeder class."""

    @pytest.fixture
    async def bootstrap(self):
        """Create and setup bootstrap."""
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)
        await bootstrap.setup()
        yield bootstrap
        await bootstrap.teardown()

    @pytest.fixture
    async def seeder(self, bootstrap):
        """Create seeder instance."""
        return SimulationDataSeeder(bootstrap)

    # =========================================================================
    # Initialization Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_seeder_initialization(self, bootstrap):
        """Test seeder initializes correctly."""
        seeder = SimulationDataSeeder(bootstrap)

        assert seeder.bootstrap == bootstrap
        assert seeder.track_items is True
        assert isinstance(seeder.created_items, CreatedItems)
        assert seeder._ticket_adapter is not None
        assert seeder._config_store is not None

    @pytest.mark.asyncio
    async def test_seeder_requires_setup_bootstrap(self):
        """Test seeder raises error if bootstrap not setup."""
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)

        with pytest.raises(ValidationError, match="must be set up"):
            SimulationDataSeeder(bootstrap)

    # =========================================================================
    # Project Creation Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_create_project(self, seeder):
        """Test creating a single project."""
        result = await seeder.create_project(
            name="test-project",
            description="Test project description",
        )

        assert result == seeder  # Returns self for chaining
        assert len(seeder.created_items.projects) == 1
        assert seeder._current_project_id is not None

        # Verify project was saved to config store
        project_id = seeder._current_project_id
        project = await seeder._config_store.get_project_config(project_id)
        assert project.name == "test-project"
        assert project.description == "Test project description"
        assert project.enabled is True

    @pytest.mark.asyncio
    async def test_create_project_with_custom_repo(self, seeder):
        """Test creating project with custom repository URL."""
        await seeder.create_project(
            name="custom-repo-project",
            repository_url="https://github.com/custom/repo.git",
            default_branch="develop",
        )

        project_id = seeder._current_project_id
        project = await seeder._config_store.get_project_config(project_id)
        assert project.repository_url == "https://github.com/custom/repo.git"
        assert project.default_branch == "develop"

    @pytest.mark.asyncio
    async def test_create_project_auto_generates_repo_url(self, seeder):
        """Test project auto-generates repository URL if not provided."""
        await seeder.create_project(name="auto-repo-project")

        project_id = seeder._current_project_id
        project = await seeder._config_store.get_project_config(project_id)
        assert "auto-repo-project" in project.repository_url
        assert project.repository_url.startswith("https://github.com/")

    # =========================================================================
    # Workflow Creation Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_create_workflow_with_default_stages(self, seeder):
        """Test creating workflow with default 3 stages."""
        await seeder.create_project("test-project")
        await seeder.create_workflow(
            name="test-workflow",
            description="Test workflow",
        )

        assert len(seeder.created_items.workflows) == 1
        assert len(seeder.created_items.pipelines) == 1

        # Verify pipeline was saved
        pipeline_id = seeder.created_items.pipelines[0]
        pipeline = await seeder._config_store.get_pipeline_config(
            seeder._current_project_id, "test-workflow"
        )
        assert pipeline.name == "test-workflow"
        assert len(pipeline.stages) == 3
        assert pipeline.stages[0].name == "design"
        assert pipeline.stages[1].name == "implementation"
        assert pipeline.stages[2].name == "testing"

    @pytest.mark.asyncio
    async def test_create_workflow_with_custom_stages(self, seeder):
        """Test creating workflow with custom stages."""
        await seeder.create_project("test-project")

        custom_stages = [
            {
                "name": "analyze",
                "agent_type": "analyzer",
                "description": "Analysis stage",
                "order": 1,
                "max_retries": 5,
                "timeout_seconds": 7200,
            },
            {
                "name": "execute",
                "agent_type": "executor",
                "description": "Execution stage",
                "order": 2,
            },
        ]

        await seeder.create_workflow(
            name="custom-workflow",
            stages=custom_stages,
        )

        pipeline = await seeder._config_store.get_pipeline_config(
            seeder._current_project_id, "custom-workflow"
        )
        assert len(pipeline.stages) == 2
        assert pipeline.stages[0].name == "analyze"
        assert pipeline.stages[0].max_retries == 5
        assert pipeline.stages[0].timeout_seconds == 7200

    @pytest.mark.asyncio
    async def test_create_workflow_requires_project(self, seeder):
        """Test workflow creation requires project context."""
        with pytest.raises(ValidationError, match="No project context"):
            await seeder.create_workflow("test-workflow")

    # =========================================================================
    # Agent Creation Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_create_agents(self, seeder):
        """Test creating multiple agents."""
        await seeder.create_project("test-project")

        agent_defs = [
            {
                "name": "agent1",
                "agent_type": "coder",
                "capabilities": ["code_generation"],
            },
            {
                "name": "agent2",
                "agent_type": "reviewer",
                "capabilities": ["code_review"],
                "temperature": 0.5,
                "max_tokens": 2048,
            },
        ]

        await seeder.create_agents(agent_defs)

        assert len(seeder.created_items.agents) == 2

        # Verify agents were saved
        agent1 = await seeder._config_store.get_agent_config(
            seeder._current_project_id, "agent1"
        )
        assert agent1.agent_name == "agent1"
        assert agent1.agent_type == "coder"

        agent2 = await seeder._config_store.get_agent_config(
            seeder._current_project_id, "agent2"
        )
        assert agent2.temperature == 0.5
        assert agent2.max_tokens == 2048

    @pytest.mark.asyncio
    async def test_create_agents_requires_project(self, seeder):
        """Test agent creation requires project context."""
        with pytest.raises(ValidationError, match="No project context"):
            await seeder.create_agents([{"name": "agent1"}])

    @pytest.mark.asyncio
    async def test_create_agents_requires_name(self, seeder):
        """Test agent definition requires name."""
        await seeder.create_project("test-project")

        with pytest.raises(ValidationError, match="must include 'name'"):
            await seeder.create_agents([{"agent_type": "coder"}])

    # =========================================================================
    # Work Item Creation Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_create_work_items(self, seeder):
        """Test creating multiple work items."""
        await seeder.create_project("test-project")

        await seeder.create_work_items(
            count=5,
            title_prefix="Test Task",
            labels=["test", "automated"],
            priority=WorkItemPriority.HIGH,
        )

        assert len(seeder.created_items.work_items) == 5

        # Verify work items were created
        work_item_id = seeder.created_items.work_items[0]
        work_item = await seeder._ticket_adapter.get_work_item(work_item_id)
        assert work_item.title == "Test Task #1"
        assert "test" in work_item.labels
        assert "automated" in work_item.labels
        assert work_item.priority == WorkItemPriority.HIGH

    @pytest.mark.asyncio
    async def test_create_work_items_default_count(self, seeder):
        """Test creating single work item (default count)."""
        await seeder.create_project("test-project")

        await seeder.create_work_items()

        assert len(seeder.created_items.work_items) == 1

    @pytest.mark.asyncio
    async def test_create_work_items_requires_project(self, seeder):
        """Test work item creation requires project context."""
        with pytest.raises(ValidationError, match="No project context"):
            await seeder.create_work_items()

    @pytest.mark.asyncio
    async def test_create_work_items_performance(self, seeder):
        """Test creating 100 work items in <500ms."""
        await seeder.create_project("test-project")

        start_time = datetime.now()
        await seeder.create_work_items(count=100)
        elapsed = (datetime.now() - start_time).total_seconds()

        assert len(seeder.created_items.work_items) == 100
        assert elapsed < 0.5, f"Creating 100 work items took {elapsed}s, expected <0.5s"

    # =========================================================================
    # Chaining Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fluent_api_chaining(self, seeder):
        """Test fluent API allows method chaining."""
        result = await (
            seeder
            .create_project("chain-test-project")
            .create_workflow("chain-workflow")
            .create_agents([
                {"name": "agent1", "capabilities": ["code_generation"]}
            ])
            .create_work_items(count=3)
        )

        # All operations should succeed
        assert result == seeder
        assert len(seeder.created_items.projects) == 1
        assert len(seeder.created_items.workflows) == 1
        assert len(seeder.created_items.agents) == 1
        assert len(seeder.created_items.work_items) == 3

    # =========================================================================
    # Pre-built Scenario Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_seed_default_scenario(self, seeder):
        """Test default scenario seeding."""
        await seeder.seed_default_scenario()

        assert len(seeder.created_items.projects) == 1
        assert len(seeder.created_items.workflows) == 1
        assert len(seeder.created_items.agents) == 3
        assert len(seeder.created_items.work_items) == 3

    @pytest.mark.asyncio
    async def test_seed_simple_workflow(self, seeder):
        """Test simple workflow scenario."""
        await seeder.seed_simple_workflow()

        assert len(seeder.created_items.projects) == 1
        assert len(seeder.created_items.work_items) == 1

    @pytest.mark.asyncio
    async def test_seed_parallel_workflow(self, seeder):
        """Test parallel workflow scenario."""
        await seeder.seed_parallel_workflow()

        assert len(seeder.created_items.projects) == 1
        assert len(seeder.created_items.work_items) == 10

    @pytest.mark.asyncio
    async def test_seed_review_cycle(self, seeder):
        """Test review cycle scenario."""
        await seeder.seed_review_cycle()

        assert len(seeder.created_items.projects) == 1
        assert len(seeder.created_items.agents) == 2
        assert len(seeder.created_items.work_items) == 5

    @pytest.mark.asyncio
    async def test_seed_failure_scenario(self, seeder):
        """Test failure scenario seeding."""
        await seeder.seed_failure_scenario()

        assert len(seeder.created_items.projects) == 1
        assert len(seeder.created_items.agents) == 2
        assert len(seeder.created_items.work_items) == 3

    # =========================================================================
    # YAML Loading Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_seed_from_yaml_default_scenario(self, seeder):
        """Test loading default.yaml scenario."""
        scenario_path = Path("/workspace/scenarios/default.yaml")

        if not scenario_path.exists():
            pytest.skip("default.yaml not found")

        await seeder.seed_from_yaml(scenario_path)

        # Verify data was seeded
        assert len(seeder.created_items.projects) >= 1
        assert len(seeder.created_items.workflows) >= 1
        assert len(seeder.created_items.agents) >= 1
        assert len(seeder.created_items.work_items) >= 1

    @pytest.mark.asyncio
    async def test_seed_from_yaml_validates_schema(self, seeder, tmp_path):
        """Test YAML validation catches errors."""
        # Create invalid YAML (missing required 'name' field)
        invalid_yaml = tmp_path / "invalid.yaml"
        invalid_yaml.write_text("""
description: "No name field"
projects: []
""")

        with pytest.raises(ValidationError, match="validation failed"):
            await seeder.seed_from_yaml(invalid_yaml)

    @pytest.mark.asyncio
    async def test_seed_from_yaml_file_not_found(self, seeder):
        """Test error when YAML file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            await seeder.seed_from_yaml("/nonexistent/file.yaml")

    @pytest.mark.asyncio
    async def test_seed_from_yaml_empty_file(self, seeder, tmp_path):
        """Test error when YAML file is empty."""
        empty_yaml = tmp_path / "empty.yaml"
        empty_yaml.write_text("")

        with pytest.raises(ValidationError, match="Empty YAML"):
            await seeder.seed_from_yaml(empty_yaml)

    # =========================================================================
    # Cleanup Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_cleanup(self, seeder):
        """Test cleanup clears created items."""
        await seeder.create_project("test-project")
        await seeder.create_work_items(count=5)

        assert len(seeder.created_items.projects) == 1
        assert len(seeder.created_items.work_items) == 5

        await seeder.cleanup()

        assert len(seeder.created_items.projects) == 0
        assert len(seeder.created_items.work_items) == 0

    @pytest.mark.asyncio
    async def test_get_created_items(self, seeder):
        """Test getting created items for inspection."""
        await seeder.create_project("test-project")

        created = seeder.get_created_items()

        assert isinstance(created, CreatedItems)
        assert len(created.projects) == 1


class TestCreatedItems:
    """Test cases for CreatedItems tracking."""

    def test_created_items_initialization(self):
        """Test CreatedItems initializes with empty lists."""
        items = CreatedItems()

        assert items.projects == []
        assert items.workflows == []
        assert items.agents == []
        assert items.work_items == []
        assert items.pipelines == []

    def test_created_items_clear(self):
        """Test clearing all tracked items."""
        items = CreatedItems()
        items.projects.append("proj1")
        items.workflows.append("wf1")
        items.agents.append("agent1")

        items.clear()

        assert items.projects == []
        assert items.workflows == []
        assert items.agents == []


class TestScenarioModels:
    """Test cases for Pydantic scenario models."""

    def test_scenario_model_validation(self):
        """Test ScenarioModel validates correctly."""
        from codetoreum.infrastructure.simulation.scenario_models import ScenarioModel

        # Valid minimal scenario
        data = {
            "name": "Test Scenario",
            "description": "Test description",
        }

        scenario = ScenarioModel(**data)
        assert scenario.name == "Test Scenario"
        assert scenario.speed_multiplier == 10.0  # Default
        assert scenario.projects == []

    def test_scenario_model_validation_errors(self):
        """Test ScenarioModel catches validation errors."""
        from codetoreum.infrastructure.simulation.scenario_models import ScenarioModel
        from pydantic import ValidationError

        # Missing required 'name'
        with pytest.raises(ValidationError):
            ScenarioModel(description="No name")

    def test_project_model_validation(self):
        """Test ScenarioProjectModel validates correctly."""
        from codetoreum.infrastructure.simulation.scenario_models import (
            ScenarioProjectModel,
        )

        data = {
            "name": "test-project",
            "description": "Test project",
        }

        project = ScenarioProjectModel(**data)
        assert project.name == "test-project"
        assert project.default_branch == "main"

    def test_agent_model_capability_validation(self):
        """Test agent capabilities are validated."""
        from codetoreum.infrastructure.simulation.scenario_models import ScenarioAgentModel
        from pydantic import ValidationError

        # Valid capabilities
        data = {
            "name": "test-agent",
            "capabilities": ["code_generation", "code_review"],
        }
        agent = ScenarioAgentModel(**data)
        assert "code_generation" in agent.capabilities

        # Invalid capability
        with pytest.raises(ValidationError, match="Invalid capability"):
            ScenarioAgentModel(
                name="bad-agent",
                capabilities=["invalid_capability"],
            )

    def test_work_item_model_priority_validation(self):
        """Test work item priority validation."""
        from codetoreum.infrastructure.simulation.scenario_models import (
            ScenarioWorkItemModel,
        )
        from pydantic import ValidationError

        # Valid priority
        item = ScenarioWorkItemModel(title="Test", priority="high")
        assert item.priority == "high"

        # Invalid priority
        with pytest.raises(ValidationError, match="Invalid priority"):
            ScenarioWorkItemModel(title="Test", priority="invalid")

    def test_workflow_stage_order_validation(self):
        """Test workflow stages must have sequential order."""
        from codetoreum.infrastructure.simulation.scenario_models import (
            ScenarioWorkflowModel,
            ScenarioStageModel,
        )
        from pydantic import ValidationError

        # Valid sequential order
        stages = [
            ScenarioStageModel(name="stage1", agent_type="agent1", order=1),
            ScenarioStageModel(name="stage2", agent_type="agent2", order=2),
        ]
        workflow = ScenarioWorkflowModel(name="test", stages=stages)
        assert len(workflow.stages) == 2

        # Invalid non-sequential order
        with pytest.raises(ValidationError, match="sequential"):
            ScenarioWorkflowModel(
                name="test",
                stages=[
                    ScenarioStageModel(name="stage1", agent_type="agent1", order=1),
                    ScenarioStageModel(name="stage2", agent_type="agent2", order=3),
                ],
            )


class TestSimulationConfigYAML:
    """Test cases for SimulationConfig YAML loading."""

    def test_from_yaml_loads_config(self, tmp_path):
        """Test loading SimulationConfig from YAML."""
        yaml_content = """
name: "Test Config"
description: "Test description"
speed_multiplier: 20.0
auto_advance: true
"""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content)

        config = SimulationConfig.from_yaml(yaml_file)

        assert config.scenario_name == "Test Config"
        assert config.scenario_description == "Test description"
        assert config.time.speed_multiplier == 20.0
        assert config.time.auto_advance is True

    def test_from_yaml_file_not_found(self):
        """Test error when YAML file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            SimulationConfig.from_yaml("/nonexistent/file.yaml")

    def test_from_yaml_missing_name(self, tmp_path):
        """Test error when name field is missing."""
        yaml_content = """
description: "No name"
"""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content)

        with pytest.raises(ValueError, match="must contain 'name'"):
            SimulationConfig.from_yaml(yaml_file)

    def test_from_yaml_adds_metadata(self, tmp_path):
        """Test YAML file path is added to metadata."""
        yaml_content = """
name: "Test"
"""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content)

        config = SimulationConfig.from_yaml(yaml_file)

        assert "yaml_file" in config.metadata
        assert str(yaml_file) in config.metadata["yaml_file"]
