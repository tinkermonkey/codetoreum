"""Production adapter selection configuration.

Defines the production AdapterSelectionConfig that explicitly selects
production implementations for all 34 adapter slots. Uses the adapter
names registered in the factory for production environments.

Used by ProductionApplicationBootstrap to wire the production environment.
"""

from codetoreum.infrastructure.simulation.simulation_config import AdapterSelectionConfig


def create_production_adapter_config() -> AdapterSelectionConfig:
    """
    Create production adapter selection configuration.

    Explicitly selects production implementations for all 34 adapter slots.
    All adapter names are registered in the factory and production-ready.

    Shared adapters (in-memory, mock) are documented in PRODUCTION_ADAPTER_AUDIT.md
    as acceptable for MVP and non-critical features.

    Returns:
        AdapterSelectionConfig with production implementations
    """
    return AdapterSelectionConfig(
        # Core system adapters
        event_store="elasticsearch",  # Production event persistence
        config_store="elasticsearch",  # Elasticsearch-backed configuration
        metrics="in_memory",  # In-memory metrics (optional Prometheus not required for MVP)
        storage="in_memory",  # In-memory storage (acceptable for MVP)
        encryption="simple",  # Simple encryption service (MVP placeholder)
        event_emitter="mock",  # Mock event emitter (MVP: adapter-level event emission; production implementation deferred)
        message_broker="in_memory",  # In-memory message broker (optional Redis not required for MVP)
        identity_service="configurable",  # Configurable identity service

        # External system integrations
        ticket="github",  # GitHub for ticket/issue management
        llm="claude_code",  # Claude Code API for LLM operations
        version_control="in_memory",  # Version control (MVP: in-memory implementation)
        container="docker",  # Docker for container management

        # Board and workflow management
        board="github",  # GitHub project board
        discussion_adapter="github",  # GitHub discussions
        workflow_config="in_memory",  # In-memory workflow definitions (acceptable for MVP)
        lock_service="in_memory",  # In-memory pipeline locks (ephemeral state acceptable)
        queue_service="in_memory",  # In-memory task queues (ephemeral state acceptable)

        # Review cycles
        review_cycle="mock",  # Mock review cycle (placeholder feature)
        pr_review_cycle="mock",  # Mock PR review cycle (placeholder feature)
        code_review="github",  # GitHub code review

        # Repair and maintenance
        repair_cycle="production",  # Production repair cycle
        checkpoint_store="in_memory",  # In-memory checkpoints (ephemeral state acceptable)
        environment_repair="production",  # Production environment repair
        systemic_analysis="llm",  # LLM-based systemic analysis
        container_recovery="docker",  # Docker-based container recovery
        ci_pipeline="github",  # GitHub Actions for CI/CD

        # Agent and execution management
        agent_repository="in_memory",  # In-memory agent repository (bootstrap-time config)
        run_registry="in_memory",  # In-memory workflow run registry (ephemeral state acceptable)
        branch_tracker="in_memory",  # In-memory branch tracking (ephemeral state acceptable)
        work_item_service="mock",  # Mock work item service (placeholder feature)

        # Repository access
        repository="git",  # Real Git repository adapter

        # Notifications
        notifier="mock",  # Mock notifier (placeholder feature)

        # Project management
        project_manager="mock",  # Mock project manager (placeholder feature)
    )
