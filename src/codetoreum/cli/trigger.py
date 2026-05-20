"""CLI command to manually trigger a work item column change via the running server."""

import json
import logging
import sys

import click
import httpx

logger = logging.getLogger(__name__)

DEFAULT_SERVER_URL = "http://localhost:8000"
DEFAULT_COLUMN = "In Progress"
TOKEN_ENV_VAR = "CODETOREUM_TOKEN"


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


@click.command(name="trigger")
@click.option(
    "--work-item-id",
    required=True,
    help="GitHub issue number or work item ID to trigger.",
)
@click.option(
    "--column",
    default=DEFAULT_COLUMN,
    show_default=True,
    help="Target column name to move the work item into.",
)
@click.option(
    "--from-column",
    default=None,
    help="Source column name (omit for initial placement).",
)
@click.option(
    "--project-id",
    default=None,
    help="Project ID (defaults to the codetoreum project configured on the server).",
)
@click.option(
    "--board-id",
    default=None,
    help="Board ID (defaults to the codetoreum board configured on the server).",
)
@click.option(
    "--server-url",
    default=DEFAULT_SERVER_URL,
    show_default=True,
    envvar="CODETOREUM_SERVER_URL",
    help="Base URL of the running Codetoreum server.",
)
@click.option(
    "--token",
    default=None,
    envvar=TOKEN_ENV_VAR,
    help=f"Auth token for the server (or set {TOKEN_ENV_VAR} env var).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the request payload without sending it.",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Enable debug logging.",
)
def main(
    work_item_id: str,
    column: str,
    from_column: str | None,
    project_id: str | None,
    board_id: str | None,
    server_url: str,
    token: str | None,
    dry_run: bool,
    verbose: bool,
) -> None:
    """
    Manually trigger a work item column change via the Codetoreum server.

    Publishes a WorkItemColumnChangedEvent to the server's in-process event bus,
    exercising the same execution path as an inbound GitHub webhook.

    The server must be running (codetoreum-server) before using this command.

    Examples:

        # Trigger work item #123 to "In Progress"
        codetoreum-trigger --work-item-id 123

        # Trigger to a different column
        codetoreum-trigger --work-item-id 123 --column "In Review"

        # Preview the request without sending it
        codetoreum-trigger --work-item-id 123 --dry-run

        # With explicit server URL and token
        codetoreum-trigger --work-item-id 123 --server-url http://localhost:9000 --token abc123
    """
    setup_logging(verbose)
    exit_code = _run(work_item_id, column, from_column, project_id, board_id, server_url, token, dry_run)
    sys.exit(exit_code)


def _run(
    work_item_id: str,
    column: str,
    from_column: str | None,
    project_id: str | None,
    board_id: str | None,
    server_url: str,
    token: str | None,
    dry_run: bool,
) -> int:
    payload: dict = {
        "work_item_id": work_item_id,
        "to_column": column,
    }
    if from_column is not None:
        payload["from_column"] = from_column
    if project_id is not None:
        payload["project_id"] = project_id
    if board_id is not None:
        payload["board_id"] = board_id

    endpoint = f"{server_url.rstrip('/')}/api/v2/trigger/column-change"

    if dry_run:
        click.echo("[*] Dry-run mode: would POST to:")
        click.echo(f"    {endpoint}")
        click.echo("[*] Payload:")
        click.echo(json.dumps(payload, indent=2))
        return 0

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    click.echo(f'[*] Triggering work item {work_item_id} -> "{column}"')
    click.echo(f"[*] Server: {server_url}")

    try:
        response = httpx.post(endpoint, json=payload, headers=headers, timeout=10.0)
    except httpx.ConnectError:
        click.echo(
            f"[!] Could not connect to {server_url}. Is the server running?",
            err=True,
        )
        return 1
    except httpx.TimeoutException:
        click.echo(f"[!] Request timed out connecting to {server_url}.", err=True)
        return 1

    if response.status_code == 202:
        body = response.json()
        click.echo(f"[checkmark] Event published (event_id: {body.get('event_id', 'N/A')})")
        return 0

    if response.status_code == 401:
        click.echo(
            f"[!] Authentication required. Pass --token or set {TOKEN_ENV_VAR}.",
            err=True,
        )
        return 1

    try:
        detail = response.json().get("detail", response.text)
    except Exception:
        detail = response.text

    click.echo(f"[!] Server returned {response.status_code}: {detail}", err=True)
    return 1
