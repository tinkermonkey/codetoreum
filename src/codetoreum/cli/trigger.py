"""
Trigger CLI for publishing WorkItemColumnChangedEvent to the event bus.

This command allows manual triggering of work item column changes, exercising
the full execution chain from the event bus through BoardColumnEventHandler.

Usage:
    codetoreum-trigger --work-item-id <id> [--column <name>] [--dry-run]

The trigger publishes a WorkItemColumnChangedEvent directly to the event bus,
bypassing webhook delivery entirely. This is useful for manual testing in development
environments where inbound webhooks may not be available.

The work item must exist on the board, and the column name must be valid in the
board's workflow template. Configuration is read from the database-backed config system.

For MVP, the trigger uses the codetoreum/codetoreum repository's configured board.
Multi-project support is a post-MVP enhancement.
"""

import asyncio
import json
import logging
import sys
from datetime import UTC, datetime

import click

from codetoreum.domain.events.board_events import WorkItemColumnChangedEvent
from codetoreum.infrastructure.bootstrap.cli_bootstrap import CLIBootstrap
from codetoreum.infrastructure.bootstrap.codetoreum_board_setup import (
    CODETOREUM_BOARD_ID,
    CODETOREUM_PROJECT_ID,
)

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """
    Configure logging for the trigger CLI.

    Args:
        verbose: Enable debug-level logging if True
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def trigger_work_item(
    work_item_id: str,
    column: str,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """
    Trigger a work item column change by publishing an event to the event bus.

    This function:
    1. Bootstraps the CLI to access the event bus and services
    2. Reads board configuration from the database (board ID, project ID, column configs)
    3. Validates that the work item exists and the column is valid
    4. Creates a WorkItemColumnChangedEvent
    5. Publishes it to the event bus (or prints it in dry-run mode)

    Args:
        work_item_id: GitHub issue number or ID
        column: Target column name (default: "In Progress")
        dry_run: Print event without publishing if True
        verbose: Enable debug logging if True

    Returns:
        Exit code (0 for success, 1 for error)
    """
    setup_logging(verbose)

    try:
        # Bootstrap minimal CLI infrastructure (event bus + config + board adapters only)
        click.echo("[*] Bootstrapping CLI environment...")
        bootstrap = CLIBootstrap()
        await bootstrap.setup()

        if not bootstrap.infrastructure or not bootstrap.adapters:
            click.echo("[!] Bootstrap failed: infrastructure not initialized", err=True)
            return 1

        event_bus = bootstrap.infrastructure.event_bus
        workflow_config = bootstrap.adapters.workflow_config
        board_service = bootstrap.adapters.board

        # For MVP, use the codetoreum board configuration
        click.echo("[*] Reading board configuration for codetoreum repository...")
        board_id = CODETOREUM_BOARD_ID
        project_id = CODETOREUM_PROJECT_ID

        # Get workflow template for the board
        click.echo(f"[*] Loading workflow template for board {board_id}...")
        try:
            workflow_template = await workflow_config.get_board_workflow_template(board_id)
            if not workflow_template:
                click.echo(
                    f"[!] No workflow template found for board '{board_id}'. "
                    f"Please configure the board with a workflow template.",
                    err=True,
                )
                return 1
        except Exception as e:
            click.echo(f"[!] Error loading workflow template: {e}", err=True)
            logger.error("Failed to load workflow template", exc_info=True)
            return 1

        # Validate that the column exists
        column_config = workflow_template.get_column_config(column)
        if not column_config:
            click.echo(f"[!] Column '{column}' not found in board workflow template.", err=True)
            click.echo(f"[*] Available columns: {', '.join(c.name for c in workflow_template.columns)}", err=True)
            return 1

        # Verify the work item exists
        click.echo(f"[*] Verifying work item {work_item_id} exists...")
        from_column = "Backlog"  # Default to Backlog for new items
        try:
            # Try to get item position (if board service supports it)
            item_position = await board_service.get_item_position(work_item_id)
            from_column = item_position.column_name
            click.echo(f"[*] Work item found in column: {from_column}")
        except NotImplementedError:
            # Board service doesn't support position lookup; assume Backlog
            click.echo(f"[*] Assuming work item is in column: {from_column} (no position lookup available)")
        except Exception as e:
            click.echo(
                f"[!] Error verifying work item {work_item_id}: {e}",
                err=True,
            )
            logger.error("Failed to verify work item", exc_info=True)
            return 1

        # Create the WorkItemColumnChangedEvent
        click.echo("[*] Creating WorkItemColumnChangedEvent...")
        try:
            event = WorkItemColumnChangedEvent(
                type="workitem.column_changed",
                timestamp=datetime.now(UTC).isoformat(),
                source="trigger_cli",
                work_item_id=work_item_id,
                project_id=project_id,
                board_id=board_id,
                from_column=from_column,
                to_column=column,
                moved_by="orchestrator",
            )
        except Exception as e:
            click.echo(f"[!] Failed to create event: {e}", err=True)
            logger.error("Failed to create WorkItemColumnChangedEvent", exc_info=True)
            return 1

        # Handle dry-run mode
        if dry_run:
            click.echo("[*] Dry-run mode: printing event without publishing")
            try:
                event_dict = event.to_dict()
                click.echo("\n" + json.dumps(event_dict, indent=2))
                click.echo("\n[✓] Event would be published (dry-run mode)")
                click.echo(f"[*] Event ID: {event_dict['event_id']}")
                return 0
            except Exception as e:
                click.echo(f"[!] Failed to serialize event: {e}", err=True)
                return 1

        # Publish the event to the event bus and persist to shared event store
        click.echo("[*] Publishing event to event store...")
        try:
            # Persist to shared event store (Elasticsearch) for cross-process distribution
            # This ensures the event reaches the application server via the shared event store
            await bootstrap.adapters.event_store.append(work_item_id, [event])

            # Also publish to local event bus for any local handlers (CLI has none, but good practice)
            await event_bus.publish(event)

            click.echo("[✓] Event published successfully")
            click.echo(f"[*] Event ID: {getattr(event, 'event_id', 'N/A')}")
            logger.info(
                "WorkItemColumnChangedEvent published",
                extra={
                    "work_item_id": work_item_id,
                    "board_id": board_id,
                    "from_column": from_column,
                    "to_column": column,
                },
            )
            return 0
        except Exception as e:
            click.echo(f"[!] Failed to publish event: {e}", err=True)
            logger.error("Failed to publish event", exc_info=True)
            return 1

    except Exception as e:
        click.echo(f"[!] Unexpected error: {e}", err=True)
        logger.error("Unexpected error during trigger execution", exc_info=True)
        return 1


@click.command(name="trigger")
@click.option(
    "--work-item-id",
    required=True,
    help="GitHub issue number or ID to trigger (required)",
)
@click.option(
    "--column",
    default="In Progress",
    help='Target column name [default: "In Progress"]',
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the event payload without publishing",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable debug-level logging",
)
def main(work_item_id: str, column: str, dry_run: bool, verbose: bool) -> None:
    """
    Manually trigger a work item column change by publishing a WorkItemColumnChangedEvent.

    This command exercises the full execution chain from the event bus through
    BoardColumnEventHandler, enabling manual testing without requiring inbound webhooks.

    For MVP, the trigger uses the codetoreum/codetoreum repository's configured board.
    Multi-project support is planned for a future release.

    Examples:

        # Trigger work item #123 to "In Progress"
        codetoreum-trigger --work-item-id 123

        # Trigger to a different column
        codetoreum-trigger --work-item-id 123 --column "In Review"

        # Preview the event without publishing (dry-run)
        codetoreum-trigger --work-item-id 123 --dry-run

        # Enable debug logging
        codetoreum-trigger --work-item-id 123 --verbose
    """
    exit_code = asyncio.run(trigger_work_item(work_item_id, column, dry_run, verbose))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
