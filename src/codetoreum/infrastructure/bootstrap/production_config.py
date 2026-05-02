"""Production adapter selection configuration.

Defines the production AdapterSelectionConfig that explicitly selects
production implementations for all 33 adapter slots with no mock or
in-memory fallbacks.

Used by ProductionApplicationBootstrap to wire the production environment.
"""

from codetoreum.infrastructure.simulation.simulation_config import AdapterSelectionConfig


def create_production_adapter_config() -> AdapterSelectionConfig:
    """
    Create production adapter selection configuration.

    Explicitly selects production implementations for all 33 adapter slots.
    No mock or in-memory fallbacks - all adapters are production-ready.

    Returns:
        AdapterSelectionConfig with production implementations
    """
    return AdapterSelectionConfig(
        # Core system adapters
        event_store="elasticsearch",  # Production event persistence
        config_store="postgres",  # Database-backed configuration
        metrics="prometheus",  # Production metrics collection
        storage="redis",  # Distributed storage via Redis
        encryption="production",  # Real encryption service
        event_emitter="redis_pubsub",  # Production event distribution
        message_broker="redis",  # Redis-based message broker
        identity_service="ldap",  # Real identity service (LDAP or similar)

        # External system integrations
        ticket="github",  # GitHub for ticket/issue management
        llm="claude",  # Claude Code API for LLM operations
        version_control="github",  # GitHub for version control
        container="docker",  # Docker for container management

        # Board and workflow management
        board="github",  # GitHub project board
        discussion_adapter="github",  # GitHub discussions
        workflow_config="postgres",  # Database-backed workflow definitions
        lock_service="redis",  # Redis-backed pipeline locks
        queue_service="redis",  # Redis-backed task queues

        # Review cycles
        review_cycle="production",  # Production review cycle
        pr_review_cycle="production",  # Production PR review cycle
        code_review="github",  # GitHub code review

        # Repair and maintenance
        repair_cycle="production",  # Production repair cycle
        checkpoint_store="redis",  # Redis-backed repair cycle checkpoints
        environment_repair="production",  # Production environment repair
        systemic_analysis="llm",  # LLM-based systemic analysis
        container_recovery="docker",  # Docker-based container recovery
        ci_pipeline="github",  # GitHub Actions for CI/CD

        # Agent and execution management
        agent_repository="postgres",  # Database-backed agent repository
        run_registry="postgres",  # Database-backed workflow run registry
        branch_tracker="postgres",  # Database-backed branch tracking
        work_item_service="production",  # Production work item service

        # Repository access
        repository="git",  # Real Git repository adapter

        # Notifications
        notifier="production",  # Production notification service

        # Project management
        project_manager="production",  # Production project manager
    )
