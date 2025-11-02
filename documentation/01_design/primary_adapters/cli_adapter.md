# CLI Adapter Design

## Purpose

The CLI Adapter provides a command-line interface for interacting with the Codetoreum system. It enables users to manage workflows, executions, configurations, and agents from the terminal, making it ideal for automation, scripting, and CI/CD pipelines.

## Architecture Position

```
┌──────────────────┐
│   Terminal       │
│   User/Script    │
└────────┬─────────┘
         │
         │ Commands
         ▼
┌──────────────────────────┐
│  CLI Adapter             │ ← Primary Adapter
│  (Typer + Rich)          │
└────┬──────────────────┬──┘
     │                  │
     │ HTTP Client      │
     ▼                  ▼
┌──────────────────────────┐
│    REST API Adapter      │
│  (or Direct Port Access) │
└──────────────────────────┘
```

## Responsibilities

### Primary Responsibilities
1. **Command Parsing**: Parse command-line arguments and options
2. **HTTP Client**: Call REST API endpoints for operations
3. **Authentication**: Manage API tokens and credentials
4. **Output Formatting**: Format responses as tables, JSON, or YAML
5. **Configuration Management**: Load/save CLI configuration files
6. **Interactive Prompts**: Provide interactive input when needed
7. **Error Handling**: Present user-friendly error messages

### Non-Responsibilities
- Business logic (handled by application services)
- Data persistence (handled via REST API)
- Event processing (handled by backend services)

## Command Structure

### Workflow Commands

```bash
# Start a new workflow
codetoreum workflow start --project <project> --work-item <id> --pipeline <name>

# List workflows
codetoreum workflow list [--project <project>] [--status <status>] [--limit <n>]

# Get workflow status
codetoreum workflow status <workflow-id>

# Pause a workflow
codetoreum workflow pause <workflow-id>

# Resume a workflow
codetoreum workflow resume <workflow-id>

# Cancel a workflow
codetoreum workflow cancel <workflow-id>

# Retry a workflow stage
codetoreum workflow retry <workflow-id> --stage <stage-name>

# Get workflow events
codetoreum workflow events <workflow-id> [--follow]
```

### Execution Commands

```bash
# List executions
codetoreum execution list [--workflow-id <id>] [--status <status>] [--limit <n>]

# Get execution status
codetoreum execution status <execution-id>

# Get execution logs
codetoreum execution logs <execution-id> [--follow] [--tail <n>]

# Get execution artifacts
codetoreum execution artifacts <execution-id> [--download <path>]

# Cancel execution
codetoreum execution cancel <execution-id>
```

### Configuration Commands

```bash
# Get configuration
codetoreum config get <key>

# Set configuration
codetoreum config set <key> <value>

# List all configuration
codetoreum config list

# Update project configuration
codetoreum config project <project-name> --file <config.yaml>

# Update agent configuration
codetoreum config agent <agent-type> --file <config.yaml>

# Add environment variable
codetoreum config env add <key> <value> --project <project>

# Remove environment variable
codetoreum config env remove <key> --project <project>

# List environment variables
codetoreum config env list --project <project>
```

### Agent Commands

```bash
# List agents
codetoreum agent list [--type <type>]

# Get agent details
codetoreum agent get <agent-id>

# Get agent executions
codetoreum agent executions <agent-id> [--limit <n>]

# Execute agent directly (for testing)
codetoreum agent execute <agent-id> --context <file>
```

### Authentication Commands

```bash
# Login to get token
codetoreum auth login [--username <user>] [--password <pass>]

# Logout (remove token)
codetoreum auth logout

# Show current user
codetoreum auth whoami

# Refresh token
codetoreum auth refresh
```

## Implementation Design

### Class Structure

```python
import typer
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.progress import Progress
import httpx
import yaml
from pathlib import Path

app = typer.Typer(
    name="codetoreum",
    help="Codetoreum AI Agent Orchestration Platform CLI",
    add_completion=True,
)

class CLIAdapter:
    """
    Typer-based CLI adapter for Codetoreum.

    Provides command-line interface for workflow management,
    execution monitoring, and configuration.
    """

    def __init__(
        self,
        config: CLIConfig,
        http_client: httpx.AsyncClient,
        console: Console,
    ):
        """Initialize CLI adapter with dependencies."""
        self.config = config
        self.http = http_client
        self.console = console

    @staticmethod
    def load_config() -> CLIConfig:
        """Load CLI configuration from file."""
        config_path = Path.home() / ".codetoreum" / "config.yaml"

        if not config_path.exists():
            return CLIConfig.default()

        with config_path.open() as f:
            data = yaml.safe_load(f)
            return CLIConfig(**data)

    def save_config(self) -> None:
        """Save CLI configuration to file."""
        config_path = Path.home() / ".codetoreum" / "config.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with config_path.open("w") as f:
            yaml.dump(self.config.dict(), f)

    def get_auth_headers(self) -> dict:
        """Get authentication headers."""
        if not self.config.token:
            raise typer.BadParameter("Not authenticated. Run 'codetoreum auth login'")

        return {"Authorization": f"Bearer {self.config.token}"}

    async def api_request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> dict:
        """Make authenticated API request."""
        url = f"{self.config.api_base_url}{endpoint}"
        headers = self.get_auth_headers()

        response = await self.http.request(
            method,
            url,
            headers=headers,
            **kwargs
        )

        if response.status_code == 401:
            raise typer.BadParameter("Authentication failed. Please login again.")

        response.raise_for_status()
        return response.json()

    def format_table(
        self,
        data: list,
        columns: list[str],
        title: Optional[str] = None
    ) -> None:
        """Format data as a table."""
        table = Table(title=title, show_header=True, header_style="bold magenta")

        for column in columns:
            table.add_column(column)

        for row in data:
            table.add_row(*[str(row.get(col, "")) for col in columns])

        self.console.print(table)

    def format_json(self, data: dict) -> None:
        """Format data as JSON."""
        import json
        self.console.print_json(json.dumps(data, indent=2))

    def format_yaml(self, data: dict) -> None:
        """Format data as YAML."""
        self.console.print(yaml.dump(data, default_flow_style=False))


@dataclass
class CLIConfig:
    """CLI configuration."""

    api_base_url: str = "http://localhost:8000/api/v1"
    token: Optional[str] = None
    output_format: str = "table"  # table, json, yaml
    color: bool = True

    @classmethod
    def default(cls) -> "CLIConfig":
        """Create default configuration."""
        return cls()
```

### Workflow Commands Implementation

```python
workflow_app = typer.Typer(help="Workflow management commands")
app.add_typer(workflow_app, name="workflow")

@workflow_app.command("start")
def start_workflow(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    work_item: str = typer.Option(..., "--work-item", "-w", help="Work item ID"),
    pipeline: str = typer.Option(..., "--pipeline", "-P", help="Pipeline name"),
    output_format: Optional[str] = typer.Option(None, "--format", "-f", help="Output format"),
):
    """Start a new workflow."""
    cli = CLIAdapter.from_config()

    try:
        response = asyncio.run(cli.api_request(
            "POST",
            "/workflows",
            json={
                "project_name": project,
                "work_item_id": work_item,
                "pipeline_name": pipeline,
            }
        ))

        if output_format == "json" or cli.config.output_format == "json":
            cli.format_json(response)
        else:
            cli.console.print(f"[green]✓[/green] Workflow started: {response['id']}")
            cli.console.print(f"Status: {response['status']}")
            cli.console.print(f"URL: {response['links']['self']}")

    except httpx.HTTPError as e:
        cli.console.print(f"[red]✗[/red] Failed to start workflow: {e}")
        raise typer.Exit(1)


@workflow_app.command("list")
def list_workflows(
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Filter by project"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of results"),
    output_format: Optional[str] = typer.Option(None, "--format", "-f", help="Output format"),
):
    """List workflows."""
    cli = CLIAdapter.from_config()

    params = {"limit": limit}
    if project:
        params["project"] = project
    if status:
        params["status"] = status

    try:
        response = asyncio.run(cli.api_request("GET", "/workflows", params=params))

        if output_format == "json" or cli.config.output_format == "json":
            cli.format_json(response)
        else:
            workflows = response["data"]
            cli.format_table(
                workflows,
                columns=["id", "project", "work_item", "status", "created_at"],
                title="Workflows"
            )

    except httpx.HTTPError as e:
        cli.console.print(f"[red]✗[/red] Failed to list workflows: {e}")
        raise typer.Exit(1)


@workflow_app.command("status")
def get_workflow_status(
    workflow_id: str = typer.Argument(..., help="Workflow ID"),
    output_format: Optional[str] = typer.Option(None, "--format", "-f", help="Output format"),
):
    """Get workflow status."""
    cli = CLIAdapter.from_config()

    try:
        response = asyncio.run(cli.api_request("GET", f"/workflows/{workflow_id}"))

        if output_format == "json" or cli.config.output_format == "json":
            cli.format_json(response)
        else:
            cli.console.print(f"Workflow: {response['id']}")
            cli.console.print(f"Status: {response['status']}")
            cli.console.print(f"Project: {response['project']}")
            cli.console.print(f"Work Item: {response['work_item_id']}")
            cli.console.print(f"Current Stage: {response.get('current_stage', 'N/A')}")
            cli.console.print(f"Created: {response['created_at']}")

    except httpx.HTTPError as e:
        cli.console.print(f"[red]✗[/red] Failed to get workflow status: {e}")
        raise typer.Exit(1)


@workflow_app.command("cancel")
def cancel_workflow(
    workflow_id: str = typer.Argument(..., help="Workflow ID"),
):
    """Cancel a workflow."""
    cli = CLIAdapter.from_config()

    # Confirm cancellation
    if not typer.confirm(f"Cancel workflow {workflow_id}?"):
        raise typer.Abort()

    try:
        response = asyncio.run(cli.api_request("POST", f"/workflows/{workflow_id}/cancel"))
        cli.console.print(f"[green]✓[/green] Workflow cancelled: {workflow_id}")

    except httpx.HTTPError as e:
        cli.console.print(f"[red]✗[/red] Failed to cancel workflow: {e}")
        raise typer.Exit(1)


@workflow_app.command("events")
def get_workflow_events(
    workflow_id: str = typer.Argument(..., help="Workflow ID"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow event stream"),
    output_format: Optional[str] = typer.Option(None, "--format", "-o", help="Output format"),
):
    """Get workflow events."""
    cli = CLIAdapter.from_config()

    if follow:
        # Use WebSocket for streaming
        cli.console.print(f"Following events for workflow {workflow_id}...")
        cli.console.print("Press Ctrl+C to stop")

        # TODO: Implement WebSocket streaming
        cli.console.print("[yellow]![/yellow] Streaming not yet implemented")
    else:
        # Get historical events
        try:
            response = asyncio.run(cli.api_request(
                "GET",
                f"/workflows/{workflow_id}/events"
            ))

            if output_format == "json" or cli.config.output_format == "json":
                cli.format_json(response)
            else:
                events = response["data"]
                cli.format_table(
                    events,
                    columns=["timestamp", "event_type", "message"],
                    title=f"Events for Workflow {workflow_id}"
                )

        except httpx.HTTPError as e:
            cli.console.print(f"[red]✗[/red] Failed to get events: {e}")
            raise typer.Exit(1)
```

### Execution Commands Implementation

```python
execution_app = typer.Typer(help="Execution management commands")
app.add_typer(execution_app, name="execution")

@execution_app.command("list")
def list_executions(
    workflow_id: Optional[str] = typer.Option(None, "--workflow", "-w", help="Filter by workflow"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of results"),
    output_format: Optional[str] = typer.Option(None, "--format", "-f", help="Output format"),
):
    """List executions."""
    cli = CLIAdapter.from_config()

    params = {"limit": limit}
    if workflow_id:
        params["workflow_id"] = workflow_id
    if status:
        params["status"] = status

    try:
        response = asyncio.run(cli.api_request("GET", "/executions", params=params))

        if output_format == "json" or cli.config.output_format == "json":
            cli.format_json(response)
        else:
            executions = response["data"]
            cli.format_table(
                executions,
                columns=["id", "workflow_id", "agent_type", "status", "created_at"],
                title="Executions"
            )

    except httpx.HTTPError as e:
        cli.console.print(f"[red]✗[/red] Failed to list executions: {e}")
        raise typer.Exit(1)


@execution_app.command("logs")
def get_execution_logs(
    execution_id: str = typer.Argument(..., help="Execution ID"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log stream"),
    tail: Optional[int] = typer.Option(None, "--tail", "-n", help="Number of recent lines"),
):
    """Get execution logs."""
    cli = CLIAdapter.from_config()

    if follow:
        # Stream logs via WebSocket
        cli.console.print(f"Following logs for execution {execution_id}...")
        cli.console.print("Press Ctrl+C to stop")

        # TODO: Implement WebSocket streaming
        cli.console.print("[yellow]![/yellow] Streaming not yet implemented")
    else:
        # Get historical logs
        params = {}
        if tail:
            params["tail"] = tail

        try:
            response = asyncio.run(cli.api_request(
                "GET",
                f"/executions/{execution_id}/logs",
                params=params
            ))

            logs = response["logs"]
            for log_line in logs:
                cli.console.print(log_line)

        except httpx.HTTPError as e:
            cli.console.print(f"[red]✗[/red] Failed to get logs: {e}")
            raise typer.Exit(1)


@execution_app.command("artifacts")
def get_execution_artifacts(
    execution_id: str = typer.Argument(..., help="Execution ID"),
    download: Optional[Path] = typer.Option(None, "--download", "-d", help="Download directory"),
    output_format: Optional[str] = typer.Option(None, "--format", "-f", help="Output format"),
):
    """Get execution artifacts."""
    cli = CLIAdapter.from_config()

    try:
        response = asyncio.run(cli.api_request(
            "GET",
            f"/executions/{execution_id}/artifacts"
        ))

        if download:
            # Download artifacts
            artifacts = response["artifacts"]
            download.mkdir(parents=True, exist_ok=True)

            with Progress() as progress:
                task = progress.add_task(
                    f"Downloading {len(artifacts)} artifacts...",
                    total=len(artifacts)
                )

                for artifact in artifacts:
                    # Download each artifact
                    artifact_url = artifact["download_url"]
                    artifact_name = artifact["name"]

                    # TODO: Implement artifact download
                    progress.update(task, advance=1)

            cli.console.print(f"[green]✓[/green] Downloaded {len(artifacts)} artifacts to {download}")

        elif output_format == "json" or cli.config.output_format == "json":
            cli.format_json(response)
        else:
            artifacts = response["artifacts"]
            cli.format_table(
                artifacts,
                columns=["name", "type", "size", "created_at"],
                title=f"Artifacts for Execution {execution_id}"
            )

    except httpx.HTTPError as e:
        cli.console.print(f"[red]✗[/red] Failed to get artifacts: {e}")
        raise typer.Exit(1)
```

### Configuration Commands Implementation

```python
config_app = typer.Typer(help="Configuration management commands")
app.add_typer(config_app, name="config")

@config_app.command("get")
def get_config(
    key: str = typer.Argument(..., help="Configuration key"),
):
    """Get configuration value."""
    cli = CLIAdapter.from_config()

    value = cli.config.dict().get(key)

    if value is None:
        cli.console.print(f"[red]✗[/red] Configuration key '{key}' not found")
        raise typer.Exit(1)

    cli.console.print(f"{key}: {value}")


@config_app.command("set")
def set_config(
    key: str = typer.Argument(..., help="Configuration key"),
    value: str = typer.Argument(..., help="Configuration value"),
):
    """Set configuration value."""
    cli = CLIAdapter.from_config()

    # Update config
    setattr(cli.config, key, value)
    cli.save_config()

    cli.console.print(f"[green]✓[/green] Set {key} = {value}")


@config_app.command("list")
def list_config():
    """List all configuration."""
    cli = CLIAdapter.from_config()

    cli.format_yaml(cli.config.dict())


@config_app.command("project")
def update_project_config(
    project: str = typer.Argument(..., help="Project name"),
    file: Path = typer.Option(..., "--file", "-f", help="Configuration file"),
):
    """Update project configuration."""
    cli = CLIAdapter.from_config()

    if not file.exists():
        cli.console.print(f"[red]✗[/red] Configuration file not found: {file}")
        raise typer.Exit(1)

    with file.open() as f:
        config_data = yaml.safe_load(f)

    try:
        response = asyncio.run(cli.api_request(
            "PATCH",
            f"/configurations/projects/{project}",
            json=config_data
        ))

        cli.console.print(f"[green]✓[/green] Updated project configuration: {project}")

    except httpx.HTTPError as e:
        cli.console.print(f"[red]✗[/red] Failed to update configuration: {e}")
        raise typer.Exit(1)
```

### Authentication Commands Implementation

```python
auth_app = typer.Typer(help="Authentication commands")
app.add_typer(auth_app, name="auth")

@auth_app.command("login")
def login(
    username: Optional[str] = typer.Option(None, "--username", "-u", help="Username"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Password"),
    api_key: Optional[str] = typer.Option(None, "--api-key", "-k", help="API key"),
):
    """Login to Codetoreum."""
    cli = CLIAdapter.from_config()

    if api_key:
        # Use API key
        cli.config.token = api_key
        cli.save_config()
        cli.console.print("[green]✓[/green] Logged in with API key")
        return

    # Interactive username/password prompt
    if not username:
        username = typer.prompt("Username")
    if not password:
        password = typer.prompt("Password", hide_input=True)

    try:
        response = asyncio.run(cli.http.post(
            f"{cli.config.api_base_url}/auth/token",
            json={"username": username, "password": password}
        ))

        response.raise_for_status()
        data = response.json()

        cli.config.token = data["access_token"]
        cli.save_config()

        cli.console.print("[green]✓[/green] Logged in successfully")

    except httpx.HTTPError as e:
        cli.console.print(f"[red]✗[/red] Login failed: {e}")
        raise typer.Exit(1)


@auth_app.command("logout")
def logout():
    """Logout from Codetoreum."""
    cli = CLIAdapter.from_config()

    cli.config.token = None
    cli.save_config()

    cli.console.print("[green]✓[/green] Logged out")


@auth_app.command("whoami")
def whoami():
    """Show current user."""
    cli = CLIAdapter.from_config()

    try:
        response = asyncio.run(cli.api_request("GET", "/auth/me"))

        cli.console.print(f"Username: {response['username']}")
        cli.console.print(f"Roles: {', '.join(response['roles'])}")

    except httpx.HTTPError as e:
        cli.console.print(f"[red]✗[/red] Failed to get user info: {e}")
        raise typer.Exit(1)
```

## Configuration File Format

### CLI Configuration (~/.codetoreum/config.yaml)

```yaml
# Codetoreum CLI Configuration

# API base URL
api_base_url: http://localhost:8000/api/v1

# Authentication token (JWT or API key)
token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Output format (table, json, yaml)
output_format: table

# Enable color output
color: true
```

## Testing Strategy

### Unit Tests

```python
import pytest
from typer.testing import CliRunner
from codetoreum.adapters.primary.cli_adapter import app

runner = CliRunner()

def test_workflow_list():
    """Test workflow list command."""
    result = runner.invoke(app, ["workflow", "list"])
    assert result.exit_code == 0


def test_workflow_start():
    """Test workflow start command."""
    result = runner.invoke(app, [
        "workflow", "start",
        "--project", "test-project",
        "--work-item", "123",
        "--pipeline", "dev"
    ])
    assert result.exit_code == 0


def test_auth_login():
    """Test authentication login."""
    result = runner.invoke(app, [
        "auth", "login",
        "--username", "test",
        "--password", "test123"
    ])
    assert result.exit_code == 0
```

### Integration Tests

```python
@pytest.mark.integration
async def test_cli_workflow_commands():
    """Test CLI workflow commands with API."""
    # Start workflow
    result = runner.invoke(app, [
        "workflow", "start",
        "--project", "integration-test",
        "--work-item", "IT-1",
        "--pipeline", "test"
    ])
    assert result.exit_code == 0

    # Extract workflow ID from output
    workflow_id = extract_workflow_id(result.stdout)

    # Get workflow status
    result = runner.invoke(app, ["workflow", "status", workflow_id])
    assert result.exit_code == 0
    assert "RUNNING" in result.stdout or "COMPLETED" in result.stdout
```

## Error Handling

### Error Types

1. **Authentication Errors**: Token expired or invalid
2. **API Errors**: HTTP errors from API calls
3. **Configuration Errors**: Missing or invalid configuration
4. **Validation Errors**: Invalid command arguments
5. **Network Errors**: Connection timeouts or failures

### Error Messages

```python
# Authentication error
[red]✗[/red] Not authenticated. Run 'codetoreum auth login'

# API error
[red]✗[/red] Failed to start workflow: 400 Bad Request
  - Invalid work item ID: 'INVALID-123'

# Configuration error
[red]✗[/red] Configuration file not found: config.yaml

# Validation error
[red]✗[/red] Invalid status value: 'INVALID'. Valid values: PENDING, RUNNING, COMPLETED, FAILED

# Network error
[red]✗[/red] Connection failed: Unable to reach API at http://localhost:8000
```

## Dependencies

```toml
[tool.poetry.dependencies]
typer = "^0.12.0"         # CLI framework
rich = "^13.7.0"           # Terminal formatting
httpx = "^0.27.2"          # HTTP client (already present)
pyyaml = "^6.0.2"          # YAML parsing (already present)
```

## Summary

The CLI Adapter provides:
- **Comprehensive command structure** for all operations
- **Authentication** via tokens or API keys
- **Multiple output formats** (table, JSON, YAML)
- **Configuration management** via YAML files
- **Rich terminal output** with colors and tables
- **Interactive prompts** when needed
- **Error handling** with user-friendly messages

This adapter enables terminal-based interaction with Codetoreum, making it ideal for automation, scripting, and CI/CD integration.
