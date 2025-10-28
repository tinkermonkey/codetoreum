"""Integration tests for PipelineManager."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from codetoreum.application.pipeline_manager import (
    PipelineManager,
    PipelineStatus,
    PipelineCheckpoint,
)
from codetoreum.adapters.testing import InMemoryEventStore
from codetoreum.domain.pipeline_stage import PipelineStage, StageStatus, StageType
from codetoreum.domain.workflow import Workflow, WorkflowStatus
from codetoreum.domain.events import (
    PipelineStageStarted,
    PipelineStageCompleted,
    PipelineStageFailed,
    PipelineCompleted,
    PipelineFailed,
)


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
    """Create PipelineManager instance with mocks."""
    return PipelineManager(
        event_store=mock_event_store,
        checkpoint_store=mock_checkpoint_store,
    )


@pytest.fixture
def simple_workflow():
    """Create simple sequential workflow with 3 stages."""
    workflow = Workflow.create(
        name="simple-workflow",
        project_id="test-project",
        description="Simple 3-stage workflow",
        stages=[],
    )

    # Add stages
    stage1 = PipelineStage.create(
        name="stage1",
        workflow_id=workflow.id,
        agent_config={"agent_id": "developer", "task": "implement"},
        stage_type=StageType.SEQUENTIAL,
        description="First stage",
    )

    stage2 = PipelineStage.create(
        name="stage2",
        workflow_id=workflow.id,
        agent_config={"agent_id": "reviewer", "task": "review"},
        stage_type=StageType.SEQUENTIAL,
        description="Second stage",
        dependencies=["stage1"],
    )

    stage3 = PipelineStage.create(
        name="stage3",
        workflow_id=workflow.id,
        agent_config={"agent_id": "tester", "task": "test"},
        stage_type=StageType.SEQUENTIAL,
        description="Third stage",
        dependencies=["stage2"],
    )

    workflow.stages = [stage1, stage2, stage3]
    return workflow


@pytest.fixture
def parallel_workflow():
    """Create workflow with parallel stages."""
    workflow = Workflow.create(
        name="parallel-workflow",
        project_id="test-project",
        description="Workflow with parallel stages",
        stages=[],
    )

    # Stage 1 - sequential
    stage1 = PipelineStage.create(
        name="stage1",
        workflow_id=workflow.id,
        agent_config={"agent_id": "analyzer", "task": "analyze"},
        stage_type=StageType.SEQUENTIAL,
        description="Analysis stage",
    )

    # Stages 2a and 2b - parallel (both depend on stage1)
    stage2a = PipelineStage.create(
        name="stage2a",
        workflow_id=workflow.id,
        agent_config={"agent_id": "developer-a", "task": "implement"},
        stage_type=StageType.PARALLEL,
        description="Parallel implementation A",
        dependencies=["stage1"],
        is_parallel=True,
    )

    stage2b = PipelineStage.create(
        name="stage2b",
        workflow_id=workflow.id,
        agent_config={"agent_id": "developer-b", "task": "implement"},
        stage_type=StageType.PARALLEL,
        description="Parallel implementation B",
        dependencies=["stage1"],
        is_parallel=True,
    )

    # Stage 3 - depends on both parallel stages
    stage3 = PipelineStage.create(
        name="stage3",
        workflow_id=workflow.id,
        agent_config={"agent_id": "integrator", "task": "integrate"},
        stage_type=StageType.SEQUENTIAL,
        description="Integration stage",
        dependencies=["stage2a", "stage2b"],
    )

    workflow.stages = [stage1, stage2a, stage2b, stage3]
    return workflow


@pytest.fixture
def review_workflow():
    """Create workflow with review stage."""
    workflow = Workflow.create(
        name="review-workflow",
        project_id="test-project",
        description="Workflow with review stage",
        stages=[],
    )

    stage1 = PipelineStage.create(
        name="implementation",
        workflow_id=workflow.id,
        agent_config={"agent_id": "developer", "task": "implement"},
        stage_type=StageType.SEQUENTIAL,
    )

    stage2 = PipelineStage.create(
        name="review",
        workflow_id=workflow.id,
        agent_config={"agent_id": "reviewer", "task": "review"},
        stage_type=StageType.REVIEW,
        dependencies=["implementation"],
        maker_agent_id="developer",
        reviewer_agent_id="reviewer",
        max_review_iterations=3,
    )

    workflow.stages = [stage1, stage2]
    return workflow


# ============================================================================
# Tests: Pipeline Execution
# ============================================================================


@pytest.mark.asyncio
async def test_execute_simple_pipeline(pipeline_manager, simple_workflow, mock_event_store):
    """Test executing simple sequential pipeline."""
    context = {
        "project_id": "test-project",
        "work_item_id": "issue-1",
    }

    result = await pipeline_manager.execute_pipeline(
        workflow=simple_workflow,
        context=context,
    )

    # Assert result
    assert result.success is True
    assert result.status == PipelineStatus.COMPLETED
    assert len(result.completed_stages) == 3
    assert result.completed_stages == ["stage1", "stage2", "stage3"]
    assert len(result.failed_stages) == 0

    # Assert events were emitted
    events = mock_event_store.events
    assert len(events) > 0

    # Check stage started events
    started_events = [e for e in events if isinstance(e, PipelineStageStarted)]
    assert len(started_events) == 3

    # Check stage completed events
    completed_events = [e for e in events if isinstance(e, PipelineStageCompleted)]
    assert len(completed_events) == 3

    # Check pipeline completed event
    pipeline_completed = [e for e in events if isinstance(e, PipelineCompleted)]
    assert len(pipeline_completed) == 1


@pytest.mark.asyncio
async def test_execute_pipeline_with_dependencies(pipeline_manager, simple_workflow):
    """Test that stages execute in correct order based on dependencies."""
    context = {}

    result = await pipeline_manager.execute_pipeline(
        workflow=simple_workflow,
        context=context,
    )

    # Stages should execute in order
    assert result.completed_stages == ["stage1", "stage2", "stage3"]

    # Context should propagate outputs
    assert "stage1_output" in context
    assert "stage2_output" in context


@pytest.mark.asyncio
async def test_execute_stage_successful(pipeline_manager, simple_workflow, mock_event_store):
    """Test executing a single stage successfully."""
    stage = simple_workflow.stages[0]
    context = {"test": "data"}

    result = await pipeline_manager.execute_stage(
        stage=stage,
        context=context,
        workflow_id=simple_workflow.id,
    )

    # Assert result
    assert result.success is True
    assert result.stage_name == "stage1"
    assert result.output is not None
    assert result.error is None

    # Assert stage status
    assert stage.status == StageStatus.COMPLETED
    assert stage.execution_id is not None

    # Assert events
    events = mock_event_store.events
    stage_started = [e for e in events if isinstance(e, PipelineStageStarted)]
    stage_completed = [e for e in events if isinstance(e, PipelineStageCompleted)]
    assert len(stage_started) == 1
    assert len(stage_completed) == 1


@pytest.mark.asyncio
async def test_execute_stage_marks_ready(pipeline_manager, simple_workflow):
    """Test that pending stage is marked ready before execution."""
    stage = simple_workflow.stages[0]
    assert stage.status == StageStatus.PENDING

    result = await pipeline_manager.execute_stage(
        stage=stage,
        context={},
    )

    # Stage should have transitioned through READY to RUNNING to COMPLETED
    assert result.success is True
    assert stage.status == StageStatus.COMPLETED


# ============================================================================
# Tests: Checkpointing & Recovery
# ============================================================================


@pytest.mark.asyncio
async def test_checkpoint_after_each_stage(pipeline_manager, simple_workflow, mock_checkpoint_store):
    """Test that pipeline checkpoints after each stage."""
    context = {}

    await pipeline_manager.execute_pipeline(
        workflow=simple_workflow,
        context=context,
    )

    # Should checkpoint after each stage (3 times)
    assert mock_checkpoint_store.save_checkpoint.call_count == 3


@pytest.mark.asyncio
async def test_recover_from_checkpoint(pipeline_manager, simple_workflow, mock_checkpoint_store):
    """Test recovering pipeline from checkpoint."""
    # Create checkpoint with stage1 completed
    checkpoint = PipelineCheckpoint(
        pipeline_id=simple_workflow.id,
        current_stage="stage1",
        completed_stages=["stage1"],
        failed_stages=[],
        status=PipelineStatus.RUNNING,
        context={"stage1_output": "previous output"},
        timestamp=datetime.now(timezone.utc),
    )

    mock_checkpoint_store.load_checkpoint.return_value = checkpoint

    # Resume from checkpoint
    result = await pipeline_manager.execute_pipeline(
        workflow=simple_workflow,
        context={},
        resume_from_checkpoint=True,
    )

    # Should skip stage1 and execute stage2, stage3
    assert result.success is True
    assert "stage1" in result.completed_stages
    assert "stage2" in result.completed_stages
    assert "stage3" in result.completed_stages


@pytest.mark.asyncio
async def test_checkpoint_save_and_recover(pipeline_manager, mock_checkpoint_store):
    """Test explicit checkpoint save and recovery."""
    checkpoint = PipelineCheckpoint(
        pipeline_id="test-pipeline",
        current_stage="stage2",
        completed_stages=["stage1"],
        failed_stages=[],
        status=PipelineStatus.RUNNING,
        context={"test": "data"},
        timestamp=datetime.now(timezone.utc),
        metadata={"extra": "info"},
    )

    # Save checkpoint
    await pipeline_manager.checkpoint("test-pipeline", checkpoint)
    mock_checkpoint_store.save_checkpoint.assert_called_once_with(
        "test-pipeline", checkpoint
    )

    # Recover checkpoint
    mock_checkpoint_store.load_checkpoint.return_value = checkpoint
    recovered = await pipeline_manager.recover("test-pipeline")

    assert recovered is not None
    assert recovered.pipeline_id == "test-pipeline"
    assert recovered.completed_stages == ["stage1"]


# ============================================================================
# Tests: Parallel Stages
# ============================================================================


@pytest.mark.asyncio
async def test_parallel_stages_after_dependency(pipeline_manager, parallel_workflow):
    """Test that parallel stages can execute after their dependency."""
    context = {}

    result = await pipeline_manager.execute_pipeline(
        workflow=parallel_workflow,
        context=context,
    )

    assert result.success is True
    assert "stage1" in result.completed_stages
    assert "stage2a" in result.completed_stages
    assert "stage2b" in result.completed_stages
    assert "stage3" in result.completed_stages


# ============================================================================
# Tests: Error Handling
# ============================================================================


@pytest.mark.asyncio
async def test_pipeline_failure_emits_event(pipeline_manager, simple_workflow, mock_event_store):
    """Test that pipeline failure emits appropriate event."""
    # Mock a failing stage by setting invalid status
    simple_workflow.stages[1].status = StageStatus.FAILED

    # Force error by having stage2 report as failed but still in workflow
    # This would happen in real execution if agent fails
    # For now we'll just verify the event emission logic

    # The pipeline will still succeed in our mock, but let's test the emission directly
    await pipeline_manager._emit_pipeline_failed(
        simple_workflow.id,
        simple_workflow,
        "Test error",
        ["stage1"],
        ["stage2"],
    )

    # Check failure event was emitted
    events = mock_event_store.events
    failed_events = [e for e in events if isinstance(e, PipelineFailed)]
    assert len(failed_events) == 1
    assert failed_events[0].error == "Test error"
    assert failed_events[0].completed_stages == ["stage1"]
    assert failed_events[0].failed_stages == ["stage2"]


# ============================================================================
# Tests: Stage Types
# ============================================================================


@pytest.mark.asyncio
async def test_review_stage_execution(pipeline_manager, review_workflow):
    """Test that review stages get proper agent configuration."""
    stage = review_workflow.stages[1]
    assert stage.stage_type == StageType.REVIEW

    # Get agent config for execution
    agent_config = stage.get_agent_for_execution()
    assert agent_config["agent_id"] == "developer"
    assert agent_config["stage_type"] == "review_maker"


# ============================================================================
# Tests: Context Propagation
# ============================================================================


@pytest.mark.asyncio
async def test_context_propagates_through_stages(pipeline_manager, simple_workflow):
    """Test that stage outputs propagate to next stages via context."""
    initial_context = {
        "project_id": "test-project",
        "work_item_id": "issue-1",
    }

    result = await pipeline_manager.execute_pipeline(
        workflow=simple_workflow,
        context=initial_context,
    )

    assert result.success is True

    # Each stage output should be added to context
    assert "stage1_output" in initial_context
    assert "stage2_output" in initial_context
    assert "stage3_output" in initial_context

    # Original context should be preserved
    assert initial_context["project_id"] == "test-project"


# ============================================================================
# Tests: Pipeline Duration
# ============================================================================


@pytest.mark.asyncio
async def test_pipeline_tracks_duration(pipeline_manager, simple_workflow):
    """Test that pipeline tracks execution duration."""
    result = await pipeline_manager.execute_pipeline(
        workflow=simple_workflow,
        context={},
    )

    assert result.duration_seconds > 0
    assert isinstance(result.duration_seconds, float)


@pytest.mark.asyncio
async def test_stage_tracks_duration(pipeline_manager, simple_workflow):
    """Test that stage tracks execution duration."""
    stage = simple_workflow.stages[0]

    result = await pipeline_manager.execute_stage(
        stage=stage,
        context={},
    )

    assert result.duration_seconds > 0
    assert stage.get_duration_seconds() is not None


# ============================================================================
# Tests: Edge Cases
# ============================================================================


@pytest.mark.asyncio
async def test_empty_workflow(pipeline_manager):
    """Test executing workflow with no stages."""
    workflow = Workflow.create(
        name="empty-workflow",
        project_id="test-project",
        description="Empty workflow",
        stages=[],
    )

    result = await pipeline_manager.execute_pipeline(
        workflow=workflow,
        context={},
    )

    assert result.success is True
    assert len(result.completed_stages) == 0
    assert result.status == PipelineStatus.COMPLETED


@pytest.mark.asyncio
async def test_checkpoint_without_store(mock_event_store):
    """Test checkpointing without checkpoint store configured."""
    manager = PipelineManager(
        event_store=mock_event_store,
        checkpoint_store=None,
    )

    checkpoint = PipelineCheckpoint(
        pipeline_id="test",
        current_stage="stage1",
        completed_stages=[],
        failed_stages=[],
        status=PipelineStatus.RUNNING,
        context={},
        timestamp=datetime.now(timezone.utc),
    )

    # Should not raise error
    await manager.checkpoint("test", checkpoint)

    # Recovery should return None
    recovered = await manager.recover("test")
    assert recovered is None
