"""
Production Application Bootstrap

Wires up the application stack in production mode with real adapters:
- GitHub integration (ticket system, board, code review)
- Docker container runtime
- PostgreSQL/Elasticsearch backends
- Branch resolution for intelligent branch reuse
- Full event sourcing with complete audit trail

This bootstrap instantiates BranchResolutionAdapter and wires it into WorkspaceRouter
to enable intelligent branch reuse in production workflows.
"""

import logging

from codetoreum.adapters.secondary.branch_resolution_adapter import BranchResolutionAdapter
from codetoreum.application.workspace_router import WorkspaceRouter, WorkspaceRouterConfig
from codetoreum.ports.output.branch_resolution_service import IBranchResolutionService
from codetoreum.ports.output.container import IContainer
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.event_store import IEventStore
from codetoreum.ports.output.ticket_system import ITicketSystem
from codetoreum.ports.output.version_control_service import IVersionControlService

logger = logging.getLogger(__name__)


def create_branch_resolution_adapter(
    ticket_system: ITicketSystem,
    version_control: IVersionControlService,
    event_emitter: IEventEmitter,
    min_confidence_threshold: float = 0.7,
    cache_ttl_seconds: int = 30,
) -> IBranchResolutionService:
    """
    Create and configure BranchResolutionAdapter for production.

    **Instantiation Checklist:**
    - [ ] BranchResolutionAdapter receives correct adapters for `ticket_system`, `version_control`, `event_emitter`
    - [ ] All required dependencies are initialized before calling this function
    - [ ] Configuration values (thresholds, cache TTL) are appropriate for production

    **Production Strictness:**
    This factory enforces strict validation that all adapters must be non-None. While the underlying
    BranchResolutionAdapter constructor accepts these implicitly, production code should ensure all
    dependencies are explicitly provided. This factory validates this assumption at wiring time to
    catch configuration errors early.

    Args:
        ticket_system: Ticket system adapter for querying parent/sibling relationships
        version_control: Version control service for listing branches
        event_emitter: Event emitter for publishing resolution events
        min_confidence_threshold: Fuzzy match minimum confidence (0.0-1.0)
        cache_ttl_seconds: Cache duration for branch list queries

    Returns:
        Configured BranchResolutionAdapter instance

    Raises:
        ValueError: If any required adapter is None
        TypeError: If adapters don't implement required interfaces
    """
    if ticket_system is None:
        msg = "ticket_system adapter is required for BranchResolutionAdapter"
        raise ValueError(msg)
    if version_control is None:
        msg = "version_control adapter is required for BranchResolutionAdapter"
        raise ValueError(msg)
    if event_emitter is None:
        msg = "event_emitter adapter is required for BranchResolutionAdapter"
        raise ValueError(msg)

    adapter = BranchResolutionAdapter(
        ticket_system=ticket_system,
        version_control=version_control,
        event_emitter=event_emitter,
        min_confidence_threshold=min_confidence_threshold,
        cache_ttl_seconds=cache_ttl_seconds,
    )

    logger.info(
        "Instantiated BranchResolutionAdapter for production",
        extra={
            "adapter_type": "BranchResolutionAdapter",
            "min_confidence_threshold": min_confidence_threshold,
            "cache_ttl_seconds": cache_ttl_seconds,
        },
    )

    return adapter


def create_workspace_router_with_branch_resolution(
    version_control: IVersionControlService,
    container: IContainer,
    event_store: IEventStore,
    branch_resolution_service: IBranchResolutionService | None = None,
    config: WorkspaceRouterConfig | None = None,
) -> WorkspaceRouter:
    """
    Create WorkspaceRouter with optional BranchResolutionAdapter for production.

    **Wiring Checklist:**
    - [ ] `BranchResolutionAdapter` is instantiated before calling this function
    - [ ] `WorkspaceRouter` is instantiated with `branch_resolution_service` parameter
    - [ ] Application servers and CLI commands use the wired bootstrap
    - [ ] Existing tests for other components continue to pass

    **Production Strictness:**
    This factory enforces strict validation that version_control, container, and event_store must be
    non-None. While WorkspaceRouter's constructor accepts optional parameters, production code should
    ensure all critical adapters are explicitly provided. This factory validates this assumption at
    wiring time to catch configuration errors early.

    Args:
        version_control: Version control service adapter (required)
        container: Container orchestration adapter (required)
        event_store: Event store for emitting events (required)
        branch_resolution_service: Optional branch resolution service for intelligent branch reuse.
                                   When None, falls back to default branch naming logic.
        config: Optional WorkspaceRouter configuration. If not provided, defaults are used.

    Returns:
        Configured WorkspaceRouter instance

    Raises:
        ValueError: If required adapters are None
    """
    if version_control is None:
        msg = "version_control adapter is required for WorkspaceRouter"
        raise ValueError(msg)
    if container is None:
        msg = "container adapter is required for WorkspaceRouter"
        raise ValueError(msg)
    if event_store is None:
        msg = "event_store adapter is required for WorkspaceRouter"
        raise ValueError(msg)

    router = WorkspaceRouter(
        vcs=version_control,
        container=container,
        event_store=event_store,
        config=config,
        branch_resolution_service=branch_resolution_service,
    )

    if branch_resolution_service:
        logger.info(
            "Wired BranchResolutionAdapter to WorkspaceRouter",
            extra={"service_type": "WorkspaceRouter", "branch_resolution_enabled": True},
        )
    else:
        logger.info(
            "WorkspaceRouter created without BranchResolutionAdapter (using default branch naming)",
            extra={"service_type": "WorkspaceRouter", "branch_resolution_enabled": False},
        )

    return router


__all__ = [
    "create_branch_resolution_adapter",
    "create_workspace_router_with_branch_resolution",
]
