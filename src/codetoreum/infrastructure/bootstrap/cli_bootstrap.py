"""
Minimal CLI Bootstrap for Trigger Command

Wires only the essential components needed for the trigger CLI:
- Event Bus (for publishing WorkItemColumnChangedEvent)
- Workflow Config Adapter (for reading board configuration)
- Board Adapter (for validating work item existence)

This is intentionally lightweight compared to ProductionApplicationBootstrap,
requiring only GitHub credentials (no Docker, Claude API, etc.).
"""

import logging
from dataclasses import dataclass
from typing import Any

from codetoreum.infrastructure.adapters.factory import AdapterFactory
from codetoreum.infrastructure.event_bus import EventBus

logger = logging.getLogger(__name__)


@dataclass
class CLIBootstrapAdapters:
    """Essential adapters for CLI trigger."""

    workflow_config: Any  # IWorkflowConfigService
    board: Any  # IBoardService


@dataclass
class CLIBootstrapInfrastructure:
    """Essential infrastructure for CLI trigger."""

    event_bus: EventBus


class CLIBootstrap:
    """Minimal bootstrap for CLI trigger command.

    Only initializes components strictly necessary for publishing events:
    - Event bus for event distribution
    - Workflow config adapter for reading board configuration
    - Board adapter for validating work item existence

    Does not initialize:
    - Docker adapter (no containers needed)
    - Claude LLM adapter (no AI execution needed)
    - FastAPI application (no web server needed)
    - Full application service stack (only 3 adapters needed, not 33)

    This bootstrap requires only GitHub credentials (GITHUB_TOKEN, GITHUB_ORG).
    """

    def __init__(self) -> None:
        """Initialize CLI bootstrap."""
        self.infrastructure: CLIBootstrapInfrastructure | None = None
        self.adapters: CLIBootstrapAdapters | None = None

    async def setup(self) -> None:
        """Set up minimal infrastructure for CLI.

        Creates an event bus and resolves GitHub adapters for board and config access.
        Requires GitHub credentials (GITHUB_TOKEN, GITHUB_ORG).

        Raises:
            ValueError: If required adapters cannot be created (missing credentials)
            Exception: If event bus or adapter initialization fails.
        """
        logger.info("Setting up CLI bootstrap (event bus + GitHub board + config adapters)")

        try:
            # Phase 1: Create event bus
            logger.debug("Creating event bus")
            event_bus = EventBus()

            # Phase 2: Create adapter factory
            logger.debug("Creating adapter factory")
            factory = AdapterFactory()

            # Phase 3: Create GitHub board adapter
            logger.debug("Creating GitHub board adapter (requires GITHUB_TOKEN, GITHUB_ORG)")
            try:
                board_adapter = factory.create_board_service(adapter_name="github")
                if not board_adapter:
                    msg = "Failed to create GitHub board adapter"
                    raise ValueError(msg)
            except Exception as e:
                msg = f"Failed to create board adapter (GitHub credentials required): {e}"
                logger.error(msg, exc_info=True)
                raise ValueError(msg) from e

            # Phase 4: Create workflow config adapter
            logger.debug("Creating workflow config adapter")
            try:
                workflow_config_adapter = factory.create_workflow_config_service()
                if not workflow_config_adapter:
                    msg = "Failed to create workflow config adapter"
                    raise ValueError(msg)
            except Exception as e:
                msg = f"Failed to create workflow config adapter: {e}"
                logger.error(msg, exc_info=True)
                raise ValueError(msg) from e

            # Phase 5: Store initialized components
            self.infrastructure = CLIBootstrapInfrastructure(event_bus=event_bus)
            self.adapters = CLIBootstrapAdapters(workflow_config=workflow_config_adapter, board=board_adapter)

            logger.info("CLI bootstrap complete (3 adapters, event bus ready)")

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error during CLI bootstrap: {e}", exc_info=True)
            raise

    async def teardown(self) -> None:
        """Clean up resources (if needed).

        The CLI bootstrap doesn't hold any long-lived resources that require
        cleanup (event bus is ephemeral for CLI use).
        """
        logger.debug("CLI bootstrap teardown complete")
