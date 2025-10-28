"""Negative test cases for PipelineManager."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from codetoreum.application.pipeline_manager import PipelineManager, PipelineStatus
from codetoreum.adapters.testing import InMemoryEventStore
from codetoreum.domain.pipeline_stage import PipelineStage, StageStatus, StageType
from codetoreum.domain.workflow import Workflow


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_event_store():
    """Create in-memory event store."""
    return InMemoryEventStore()


@pytest.fixture
def mock_checkpoint_store():
    """Create mock checkpoint store."""
    store = AsyncMock()
    store.save_checkpoint = AsyncMock()
    store.load_checkpoint = AsyncMock(return_value=None)
    return store


@pytest.fixture
def pipeline_manager(mock_event_store, mock_checkpoint_store):
    """Create PipelineManager instance."""
    return PipelineManager(
        event_store=mock_event_store,
        checkpoint_store=mock_checkpoint_store,
    )


@pytest.fixture
def failing_workflow():
    """Create workflow with a stage that will fail."""
    workflow = Workflow.create(
        name="failing-workflow",
        project_id="test-project",
        description="Workflow with failing stage",
        stages=[],
    )

    stage1 = PipelineStage.create(
        name="stage1",
        workflow_id=workflow.id,
        agent_config={"agent_id": "agent1"},
        stage_type=StageType.SEQUENTIAL,
    )

    stage2 = PipelineStage.create(
        name="failing_stage",
        workflow_id=workflow.id,
        agent_config={"agent_id": "agent2"},
        stage_type=StageType.SEQUENTIAL,
        dependencies=["stage1"],
    )

    stage3 = PipelineStage.create(
        name="stage3",
        workflow_id=workflow.id,
        agent_config={"agent_id": "agent3"},
        stage_type=StageType.SEQUENTIAL,
        dependencies=["failing_stage"],
    )

    workflow.stages = [stage1, stage2, stage3]
    return workflow


@pytest.fixture
def parallel_failing_workflow():
    """Create workflow with parallel stages where one fails."""
    workflow = Workflow.create(
        name="parallel-failing",
        project_id="test-project",
        description="Workflow with failing parallel stage",
        stages=[],
    )

    stage1 = PipelineStage.create(
        name="stage1",
        workflow_id=workflow.id,
        agent_config={"agent_id": "agent1"},
        stage_type=StageType.SEQUENTIAL,
    )

    stage2a = PipelineStage.create(
        name="stage2a_success",
        workflow_id=workflow.id,
        agent_config={"agent_id": "agent2a"},
        stage_type=StageType.PARALLEL,
        dependencies=["stage1"],
        is_parallel=True,
    )

    stage2b = PipelineStage.create(
        name="stage2b_fail",
        workflow_id=workflow.id,
        agent_config={"agent_id": "agent2b"},
        stage_type=StageType.PARALLEL,
        dependencies=["stage1"],
        is_parallel=True,
    )

    workflow.stages = [stage1, stage2a, stage2b]
    return workflow


# ============================================================================
# Negative Tests: Stage Failures
# ============================================================================


@pytest.mark.asyncio
async def test_pipeline_stops_on_sequential_stage_failure(pipeline_manager, mock_event_store):
    """Test that pipeline stops when sequential stage fails."""
    from codetoreum.domain.events import PipelineFailed

    workflow = Workflow.create(
        name="test-workflow",
        project_id="test-project",
        description="Test workflow",
        stages=[],
    )

    # Create stage that will fail
    stage1 = PipelineStage.create(
        name="failing_stage",
        workflow_id=workflow.id,
        agent_config={"agent_id": "agent1"},
        stage_type=StageType.SEQUENTIAL,
    )

    # Mark stage as failed beforehand
    stage1.status = StageStatus.FAILED

    workflow.stages = [stage1]

    result = await pipeline_manager.execute_pipeline(
        workflow=workflow,
        context={},
    )

    # Pipeline should fail
    assert result.success is False
    assert result.status == PipelineStatus.FAILED

    # Should emit failure event
    events = mock_event_store.events
    failed_events = [e for e in events if isinstance(e, PipelineFailed)]
    assert len(failed_events) >= 1


@pytest.mark.asyncio
async def test_parallel_stage_failure_continues(pipeline_manager, parallel_failing_workflow, mock_event_store):
    """Test that pipeline continues when parallel stage fails."""
    from codetoreum.domain.events import PipelineStageFailed

    # Mock the execute_stage to fail for specific stage
    original_execute_stage = pipeline_manager.execute_stage

    async def mock_execute_stage(stage, context, workflow_id=None):
        if stage.name == "stage2b_fail":
            # Force failure
            stage.start("exec-123")
            stage.fail("Simulated failure")
            return type('obj', (object,), {
                'success': False,
                'stage_name': stage.name,
                'output': None,
                'error': 'Simulated failure',
                'duration_seconds': 0.1,
                'metadata': {},
            })()
        return await original_execute_stage(stage, context, workflow_id)

    pipeline_manager.execute_stage = mock_execute_stage

    result = await pipeline_manager.execute_pipeline(
        workflow=parallel_failing_workflow,
        context={},
    )

    # Pipeline should complete despite parallel failure
    assert result.success is True
    assert "stage1" in result.completed_stages
    assert "stage2a_success" in result.completed_stages
    # stage2b should be in failed stages
    assert "stage2b_fail" in result.failed_stages


# ============================================================================
# Negative Tests: Checkpoint Failures
# ============================================================================


@pytest.mark.asyncio
async def test_checkpoint_save_failure_doesnt_break_pipeline(
    pipeline_manager, mock_checkpoint_store
):
    """Test that checkpoint save failure doesn't break pipeline execution."""
    # Make checkpoint save fail
    mock_checkpoint_store.save_checkpoint.side_effect = Exception("Checkpoint storage error")

    workflow = Workflow.create(
        name="test-workflow",
        project_id="test-project",
        description="Test workflow",
        stages=[],
    )

    stage1 = PipelineStage.create(
        name="stage1",
        workflow_id=workflow.id,
        agent_config={"agent_id": "agent1"},
        stage_type=StageType.SEQUENTIAL,
    )

    workflow.stages = [stage1]

    # Pipeline should still succeed despite checkpoint failures
    result = await pipeline_manager.execute_pipeline(
        workflow=workflow,
        context={},
    )

    assert result.success is True


@pytest.mark.asyncio
async def test_checkpoint_load_failure_starts_fresh(pipeline_manager, mock_checkpoint_store):
    """Test that checkpoint load failure causes fresh start."""
    # Make checkpoint load fail
    mock_checkpoint_store.load_checkpoint.side_effect = Exception("Load error")

    workflow = Workflow.create(
        name="test-workflow",
        project_id="test-project",
        description="Test workflow",
        stages=[],
    )

    stage1 = PipelineStage.create(
        name="stage1",
        workflow_id=workflow.id,
        agent_config={"agent_id": "agent1"},
        stage_type=StageType.SEQUENTIAL,
    )

    workflow.stages = [stage1]

    # Should start fresh without crashing
    result = await pipeline_manager.execute_pipeline(
        workflow=workflow,
        context={},
        resume_from_checkpoint=True,
    )

    assert result.success is True


# ============================================================================
# Negative Tests: Event Store Failures
# ============================================================================


@pytest.mark.asyncio
async def test_event_emission_failure_doesnt_break_pipeline():
    """Test that event store failures don't break pipeline execution."""
    # Create event store that fails
    failing_event_store = AsyncMock()
    failing_event_store.append.side_effect = Exception("Event store unavailable")

    pipeline_manager = PipelineManager(
        event_store=failing_event_store,
        checkpoint_store=None,
    )

    workflow = Workflow.create(
        name="test-workflow",
        project_id="test-project",
        description="Test workflow",
        stages=[],
    )

    stage1 = PipelineStage.create(
        name="stage1",
        workflow_id=workflow.id,
        agent_config={"agent_id": "agent1"},
        stage_type=StageType.SEQUENTIAL,
    )

    workflow.stages = [stage1]

    # Pipeline should succeed despite event store failures
    result = await pipeline_manager.execute_pipeline(
        workflow=workflow,
        context={},
    )

    assert result.success is True


# ============================================================================
# Negative Tests: Context and Dependencies
# ============================================================================


@pytest.mark.asyncio
async def test_stage_waits_for_unmet_dependencies(pipeline_manager):
    """Test that stages wait when dependencies are not met."""
    workflow = Workflow.create(
        name="test-workflow",
        project_id="test-project",
        description="Test workflow",
        stages=[],
    )

    # Create stage with unmet dependency
    stage1 = PipelineStage.create(
        name="stage1",
        workflow_id=workflow.id,
        agent_config={"agent_id": "agent1"},
        stage_type=StageType.SEQUENTIAL,
        dependencies=["nonexistent_stage"],  # Dependency that will never be met
    )

    workflow.stages = [stage1]

    result = await pipeline_manager.execute_pipeline(
        workflow=workflow,
        context={},
    )

    # Should complete but stage1 never executes
    assert result.success is True
    assert len(result.completed_stages) == 0


@pytest.mark.asyncio
async def test_context_propagation_with_failed_stage(pipeline_manager):
    """Test that context properly tracks failed stage outputs."""
    workflow = Workflow.create(
        name="test-workflow",
        project_id="test-project",
        description="Test workflow",
        stages=[],
    )

    stage1 = PipelineStage.create(
        name="stage1",
        workflow_id=workflow.id,
        agent_config={"agent_id": "agent1"},
        stage_type=StageType.SEQUENTIAL,
    )

    workflow.stages = [stage1]

    # Mock execute_stage to fail
    original_execute_stage = pipeline_manager.execute_stage

    async def mock_execute_stage(stage, context, workflow_id=None):
        if stage.name == "stage1":
            stage.start("exec-123")
            stage.fail("Test failure")
            return type('obj', (object,), {
                'success': False,
                'stage_name': stage.name,
                'output': None,
                'error': 'Test failure',
                'duration_seconds': 0.1,
                'metadata': {},
            })()
        return await original_execute_stage(stage, context, workflow_id)

    pipeline_manager.execute_stage = mock_execute_stage

    context = {}
    result = await pipeline_manager.execute_pipeline(
        workflow=workflow,
        context=context,
    )

    # Context should have failed stage output
    assert "stage1_output" in context
    assert context["stage1_output"]["success"] is False
    assert context["stage1_output"]["error"] == "Test failure"


# ============================================================================
# Negative Tests: Edge Cases
# ============================================================================


@pytest.mark.asyncio
async def test_execute_stage_with_invalid_status(pipeline_manager):
    """Test executing stage that's already completed."""
    workflow = Workflow.create(
        name="test-workflow",
        project_id="test-project",
        description="Test workflow",
        stages=[],
    )

    stage = PipelineStage.create(
        name="stage1",
        workflow_id=workflow.id,
        agent_config={"agent_id": "agent1"},
        stage_type=StageType.SEQUENTIAL,
    )

    # Mark as completed
    stage.status = StageStatus.COMPLETED

    # Should still handle gracefully
    result = await pipeline_manager.execute_stage(
        stage=stage,
        context={},
    )

    # Will re-execute since we call start()
    assert result.success is True
