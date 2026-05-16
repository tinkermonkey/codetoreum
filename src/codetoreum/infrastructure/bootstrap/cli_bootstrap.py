"""
Minimal CLI Bootstrap for Trigger Command

Wires only the essential components needed for the trigger CLI:
- Shared Event Store (Elasticsearch) for cross-process event distribution
- Event Bus (for publishing WorkItemColumnChangedEvent)
- Workflow Config Adapter (for reading board configuration)
- Board Adapter (for validating work item existence)

This is intentionally lightweight compared to ProductionApplicationBootstrap,
requiring only GitHub credentials (no Docker, Claude API, etc.).

The shared event store ensures that events published via CLI reach the application
server, enabling cross-process event propagation.
"""

import logging
from dataclasses import dataclass
from typing import Any

from codetoreum.adapters.secondary.event_store_factory import initialize_event_store
from codetoreum.infrastructure.adapters.factory import AdapterFactory
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.simulation.simulation_config import AdapterSelectionConfig
from codetoreum.ports.output.event_store import IEventStore

logger = logging.getLogger(__name__)


@dataclass
class CLIBootstrapAdapters:
    """Essential adapters for CLI trigger."""

    workflow_config: Any  # IWorkflowConfigService
    board: Any  # IBoardService
    event_store: IEventStore


@dataclass
class CLIBootstrapInfrastructure:
    """Essential infrastructure for CLI trigger."""

    event_bus: EventBus


class CLIBootstrap:
    """Minimal bootstrap for CLI trigger command.

    Only initializes components strictly necessary for publishing events:
    - Shared event store for cross-process event distribution
    - Event bus for event distribution
    - Workflow config adapter for reading board configuration
    - Board adapter for validating work item existence

    Does not initialize:
    - Docker adapter (no containers needed)
    - Claude LLM adapter (no AI execution needed)
    - FastAPI application (no web server needed)
    - Full application service stack (only 4 adapters needed, not 33)

    This bootstrap requires only GitHub credentials (GITHUB_TOKEN, GITHUB_ORG)
    and Elasticsearch URL (ELASTICSEARCH_URL, optional).

    The shared event store ensures that events published via trigger CLI
    reach the application server, enabling cross-process event propagation.
    """

    def __init__(self) -> None:
        """Initialize CLI bootstrap."""
        self.infrastructure: CLIBootstrapInfrastructure | None = None
        self.adapters: CLIBootstrapAdapters | None = None

    async def setup(self) -> None:
        """Set up minimal infrastructure for CLI.

        Creates an event store, event bus, and resolves GitHub adapters for board and config access.
        Requires GitHub credentials (GITHUB_TOKEN, GITHUB_ORG).
        Optionally uses ELASTICSEARCH_URL for shared event store (default: http://localhost:9200).

        Raises:
            ValueError: If required adapters cannot be created (missing credentials)
            Exception: If event bus, event store, or adapter initialization fails.
        """
        logger.info("Setting up CLI bootstrap (event store + event bus + GitHub adapters)")

        try:
            # Phase 1: Create event bus
            logger.debug("Creating event bus")
            event_bus = EventBus()

            # Phase 2: Create adapter factory
            logger.debug("Creating adapter factory")
            factory = AdapterFactory()

            # Phase 3: Create shared event store (Elasticsearch)
            logger.debug("Creating shared event store for cross-process event distribution")
            try:
                # Use elasticsearch by default for CLI to match production
                adapter_config = AdapterSelectionConfig(
                    event_store="elasticsearch",
                    # Other slots don't matter for CLI, use defaults
                )
                event_store = factory.create_event_store(adapter_name=adapter_config.event_store)
                await initialize_event_store(event_store)
                logger.info("Shared event store initialized")
            except Exception as e:
                msg = f"Failed to create event store (Elasticsearch required): {e}"
                logger.error(msg, exc_info=True)
                raise ValueError(msg) from e

            # Phase 4: Create GitHub board adapter
            logger.debug("Creating GitHub board adapter (requires GITHUB_TOKEN, GITHUB_ORG)")
            try:
                board_adapter = factory.create_board_service(adapter_name="github")
                if not board_adapter:
                    msg = "Failed to create GitHub board adapter"
                    raise ValueError(msg)
            except ValueError:
                # Re-raise ValueError without wrapping (our explicit check above)
                raise
            except Exception as e:
                msg = f"Failed to create board adapter (GitHub credentials required): {e}"
                logger.error(msg, exc_info=True)
                raise ValueError(msg) from e

            # Phase 5: Create workflow config adapter
            logger.debug("Creating workflow config adapter")
            try:
                workflow_config_adapter = factory.create_workflow_config_service()
                if not workflow_config_adapter:
                    msg = "Failed to create workflow config adapter"
                    raise ValueError(msg)
            except ValueError:
                # Re-raise ValueError without wrapping (our explicit check above)
                raise
            except Exception as e:
                msg = f"Failed to create workflow config adapter: {e}"
                logger.error(msg, exc_info=True)
                raise ValueError(msg) from e

            # Phase 5b: Initialize codetoreum board template
            logger.debug("Initializing codetoreum board workflow template")
            try:
                from codetoreum.infrastructure.bootstrap.codetoreum_board_setup import (
                    create_codetoreum_board_template,
                )

                template = create_codetoreum_board_template()
                await workflow_config_adapter.save_board_workflow_template(template)
                logger.debug(
                    "Initialized codetoreum board workflow template",
                    extra={
                        "board_id": template.board_id,
                        "project_id": template.project_id,
                        "column_count": len(template.columns),
                    },
                )
            except Exception as e:
                logger.warning(
                    f"Failed to initialize codetoreum board template: {e}",
                    exc_info=True,
                )
                # Don't fail the entire bootstrap if board init fails

            # Phase 6: Store initialized components
            self.infrastructure = CLIBootstrapInfrastructure(event_bus=event_bus)
            self.adapters = CLIBootstrapAdapters(
                workflow_config=workflow_config_adapter,
                board=board_adapter,
                event_store=event_store,
            )

            logger.info("CLI bootstrap complete (4 adapters, shared event store ready)")

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error during CLI bootstrap: {e}", exc_info=True)
            raise

    async def teardown(self) -> None:
        """Clean up resources.

        Closes the event store and clears references to adapters.
        """
        logger.info("CLI bootstrap teardown starting")
        try:
            if self.adapters and self.adapters.event_store:
                from codetoreum.adapters.secondary.event_store_factory import close_event_store

                await close_event_store(self.adapters.event_store)
            logger.debug("CLI bootstrap teardown complete")
        except Exception as e:
            logger.error(f"Error during CLI bootstrap teardown: {e}", exc_info=True)
            raise
