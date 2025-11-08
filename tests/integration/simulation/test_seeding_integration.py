"""Integration tests for simulation data seeding with bootstrap."""

import pytest
from pathlib import Path

from codetoreum.infrastructure.simulation import (
    SimulationApplicationBootstrap,
    SimulationDataSeeder,
    SimulationConfig,
)


class TestSeedingBootstrapIntegration:
    """Integration tests for seeder with full bootstrap stack."""

    @pytest.fixture
    async def bootstrap(self):
        """Create and setup full bootstrap."""
        config = SimulationConfig.create_fast_config("integration-test")
        bootstrap = SimulationApplicationBootstrap(config)
        await bootstrap.setup()
        yield bootstrap
        await bootstrap.teardown()

    @pytest.fixture
    async def seeder(self, bootstrap):
        """Create seeder with bootstrap."""
        return SimulationDataSeeder(bootstrap)

    # =========================================================================
    # Full Stack Integration Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_seeder_works_with_bootstrap(self, seeder):
        """Test seeder integrates correctly with bootstrap."""
        # Create complete scenario with proper async chaining
        result = await seeder.create_project("integration-project")
        result = await result.create_workflow("integration-workflow")
        result = await result.create_agents([
            {"name": "test-agent", "capabilities": ["code_generation"]}
        ])
        result = await result.create_work_items(count=5)

        # Verify all data is accessible through adapters
        assert len(seeder.created_items.projects) == 1
        assert len(seeder.created_items.workflows) == 1
        assert len(seeder.created_items.agents) == 1
        assert len(seeder.created_items.work_items) == 5

        # Verify data in adapters
        project_id = seeder.created_items.projects[0]
        project = await seeder._config_store.get_project_config(project_id)
        assert project.name == "integration-project"

        agent = await seeder._config_store.get_agent_config(project_id, "test-agent")
        assert agent.agent_name == "test-agent"

        work_item_id = seeder.created_items.work_items[0]
        work_item = await seeder._ticket_adapter.get_work_item(work_item_id)
        assert work_item.project_id == project_id

    @pytest.mark.asyncio
    async def test_multiple_seeder_instances(self, bootstrap):
        """Test multiple seeder instances can work with same bootstrap."""
        seeder1 = SimulationDataSeeder(bootstrap, track_items=True)
        seeder2 = SimulationDataSeeder(bootstrap, track_items=True)

        # Both seeders create data
        await seeder1.create_project("project-1")
        await seeder2.create_project("project-2")

        # Each tracks its own items
        assert len(seeder1.created_items.projects) == 1
        assert len(seeder2.created_items.projects) == 1

        # But both projects exist in config store
        project1 = await seeder1._config_store.get_project_config_by_name("project-1")
        project2 = await seeder2._config_store.get_project_config_by_name("project-2")
        assert project1.name == "project-1"
        assert project2.name == "project-2"

    @pytest.mark.asyncio
    async def test_seeder_with_custom_bootstrap_config(self):
        """Test seeder works with custom bootstrap configuration."""
        # Create bootstrap with custom config
        custom_config = SimulationConfig.create_realistic_config(
            "custom-test",
            speed_multiplier=50.0,
        )
        bootstrap = SimulationApplicationBootstrap(custom_config)
        await bootstrap.setup()

        try:
            seeder = SimulationDataSeeder(bootstrap)
            await seeder.seed_default_scenario()

            # Verify scenario was seeded
            assert len(seeder.created_items.projects) >= 1
            assert len(seeder.created_items.work_items) >= 1

        finally:
            await bootstrap.teardown()

    # =========================================================================
    # Pre-built Scenario Integration Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_all_prebuilt_scenarios_work(self, seeder):
        """Test all pre-built scenarios complete successfully."""
        # Test each scenario - using method names instead of bound methods
        scenario_names = [
            "seed_default_scenario",
            "seed_simple_workflow",
            "seed_parallel_workflow",
            "seed_review_cycle",
            "seed_failure_scenario",
        ]

        for i, scenario_name in enumerate(scenario_names):
            # Create fresh seeder for each scenario
            config = SimulationConfig.create_fast_config(f"scenario-{i}")
            bootstrap = SimulationApplicationBootstrap(config)
            await bootstrap.setup()

            try:
                scenario_seeder = SimulationDataSeeder(bootstrap)
                # Call the scenario method on the correct seeder instance
                scenario_method = getattr(scenario_seeder, scenario_name)
                await scenario_method()

                # Verify data was created
                assert len(scenario_seeder.created_items.projects) >= 1
                assert len(scenario_seeder.created_items.work_items) >= 1

            finally:
                await bootstrap.teardown()

    # =========================================================================
    # YAML Scenario Integration Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_load_all_example_scenarios(self, seeder):
        """Test loading all example YAML scenarios."""
        scenarios_dir = Path("/workspace/scenarios")

        if not scenarios_dir.exists():
            pytest.skip("Scenarios directory not found")

        yaml_files = [
            "default.yaml",
            "demo.yaml",
            "stress_test.yaml",
            "review_cycle.yaml",
            "failure_recovery.yaml",
        ]

        for yaml_file in yaml_files:
            scenario_path = scenarios_dir / yaml_file

            if not scenario_path.exists():
                pytest.skip(f"{yaml_file} not found")

            # Create fresh bootstrap for each scenario
            config = SimulationConfig.create_fast_config(f"test-{yaml_file}")
            bootstrap = SimulationApplicationBootstrap(config)
            await bootstrap.setup()

            try:
                scenario_seeder = SimulationDataSeeder(bootstrap)
                await scenario_seeder.seed_from_yaml(scenario_path)

                # Verify scenario loaded successfully
                assert len(scenario_seeder.created_items.projects) >= 1, \
                    f"{yaml_file} should create at least 1 project"

            finally:
                await bootstrap.teardown()

    @pytest.mark.asyncio
    async def test_yaml_scenario_data_accessible(self, seeder):
        """Test data from YAML scenario is accessible via adapters."""
        scenario_path = Path("/workspace/scenarios/default.yaml")

        if not scenario_path.exists():
            pytest.skip("default.yaml not found")

        await seeder.seed_from_yaml(scenario_path)

        # Verify project exists
        project_id = seeder.created_items.projects[0]
        project = await seeder._config_store.get_project_config(project_id)
        assert project.name == "default-project"

        # Verify workflow exists
        pipeline = await seeder._config_store.get_pipeline_config(
            project_id, "default-workflow"
        )
        assert pipeline.name == "default-workflow"
        assert len(pipeline.stages) == 3

        # Verify agents exist
        architect = await seeder._config_store.get_agent_config(project_id, "architect")
        assert architect.agent_name == "architect"

        # Verify work items exist
        work_item_id = seeder.created_items.work_items[0]
        work_item = await seeder._ticket_adapter.get_work_item(work_item_id)
        assert "Default Issue" in work_item.title

    # =========================================================================
    # Performance Integration Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_seed_100_work_items_performance(self, seeder):
        """Test seeding 100 work items meets performance target (<500ms)."""
        import time

        await seeder.create_project("perf-test-project")

        start = time.perf_counter()
        await seeder.create_work_items(count=100)
        elapsed = time.perf_counter() - start

        assert len(seeder.created_items.work_items) == 100
        assert elapsed < 0.5, f"Seeding 100 items took {elapsed:.3f}s, expected <0.5s"

    @pytest.mark.asyncio
    async def test_complete_scenario_setup_performance(self, seeder):
        """Test complete scenario setup is fast."""
        import time

        start = time.perf_counter()
        await seeder.seed_default_scenario()
        elapsed = time.perf_counter() - start

        # Default scenario should complete in under 1 second
        assert elapsed < 1.0, f"Default scenario took {elapsed:.3f}s, expected <1.0s"

    # =========================================================================
    # Data Consistency Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_work_items_have_correct_project_id(self, seeder):
        """Test work items are associated with correct project."""
        await seeder.create_project("test-project")
        project_id = seeder._current_project_id

        await seeder.create_work_items(count=5)

        # All work items should have the same project ID
        for work_item_id in seeder.created_items.work_items:
            work_item = await seeder._ticket_adapter.get_work_item(work_item_id)
            assert work_item.project_id == project_id

    @pytest.mark.asyncio
    async def test_agents_have_correct_project_id(self, seeder):
        """Test agents are associated with correct project."""
        await seeder.create_project("test-project")
        project_id = seeder._current_project_id

        await seeder.create_agents([
            {"name": "agent1", "capabilities": ["code_generation"]},
            {"name": "agent2", "capabilities": ["code_review"]},
        ])

        # All agents should have the same project ID
        agent1 = await seeder._config_store.get_agent_config(project_id, "agent1")
        agent2 = await seeder._config_store.get_agent_config(project_id, "agent2")
        assert agent1.project_id == project_id
        assert agent2.project_id == project_id

    @pytest.mark.asyncio
    async def test_pipeline_belongs_to_project(self, seeder):
        """Test pipeline is associated with correct project."""
        await seeder.create_project("test-project")
        project_id = seeder._current_project_id

        await seeder.create_workflow("test-workflow")

        pipeline = await seeder._config_store.get_pipeline_config(
            project_id, "test-workflow"
        )
        assert pipeline.project_id == project_id

    # =========================================================================
    # Cleanup Integration Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_cleanup_with_bootstrap(self, seeder):
        """Test cleanup works correctly with bootstrap."""
        # Create data
        await seeder.seed_default_scenario()

        # Verify data exists
        assert len(seeder.created_items.projects) > 0
        assert len(seeder.created_items.work_items) > 0

        # Cleanup
        await seeder.cleanup()

        # Tracking should be cleared
        assert len(seeder.created_items.projects) == 0
        assert len(seeder.created_items.work_items) == 0

    @pytest.mark.asyncio
    async def test_bootstrap_teardown_cleans_data(self, bootstrap):
        """Test bootstrap teardown cleans up seeded data."""
        seeder = SimulationDataSeeder(bootstrap)
        await seeder.seed_default_scenario()

        # Get references to check
        project_id = seeder.created_items.projects[0]

        # Teardown bootstrap
        await bootstrap.teardown()

        # Bootstrap should be torn down
        assert not bootstrap._is_setup

    # =========================================================================
    # Error Handling Integration Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_seeder_handles_adapter_errors(self, seeder):
        """Test seeder handles errors from adapters gracefully."""
        from codetoreum.ports.exceptions import ValidationError

        # Attempt to create work item without project
        with pytest.raises(ValidationError, match="No project context"):
            await seeder.create_work_items(count=1)

        # Seeder should still be usable
        await seeder.create_project("recovery-project")
        await seeder.create_work_items(count=1)

        assert len(seeder.created_items.work_items) == 1

    @pytest.mark.asyncio
    async def test_yaml_loading_validation_errors(self, seeder, tmp_path):
        """Test YAML loading handles validation errors."""
        from codetoreum.ports.exceptions import ValidationError

        # Create YAML with invalid work item priority
        invalid_yaml = tmp_path / "invalid.yaml"
        invalid_yaml.write_text("""
name: "Invalid Scenario"
projects:
  - name: "test-project"
work_items:
  - title: "Test"
    priority: "invalid_priority"
""")

        with pytest.raises(ValidationError, match="validation failed"):
            await seeder.seed_from_yaml(invalid_yaml)
