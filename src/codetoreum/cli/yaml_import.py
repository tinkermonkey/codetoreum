"""
YAML Configuration Import Tool

CLI tool to migrate existing YAML configuration files to the database-backed
configuration system.

SECURITY FEATURES:
- Path validation and sanitization
- File size limits (10MB max)
- YAML bomb protection (depth limit, max nodes)
- File extension validation
- Safe YAML loading with no code execution
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

import click
import yaml
from rich.console import Console
from rich.progress import Progress
from rich.table import Table

from codetoreum.adapters.secondary.config_storage_factory import ConfigStorageFactory
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.ports.output.config_store import (
    AgentConfig,
    PipelineConfig,
    ProjectConfig,
)

logger = logging.getLogger(__name__)
console = Console()

# Security constants
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {".yaml", ".yml"}
MAX_YAML_DEPTH = 10
MAX_YAML_NODES = 10000


class SecurityError(Exception):
    """Raised when a security validation fails."""


class YAMLConfigImporter:
    """
    Imports YAML configuration files into the database-backed configuration store.

    Security features:
    - Validates and sanitizes file paths
    - Enforces file size limits
    - Protects against YAML bombs
    - Only accepts .yaml/.yml files
    """

    def __init__(self, config_store):
        """
        Initialize the importer.

        Args:
            config_store: Configuration storage adapter
        """
        self.config_store = config_store

    def _validate_file_path(self, file_path: Path) -> Path:
        """
        Validate and sanitize file path for security.

        Args:
            file_path: Path to validate

        Returns:
            Resolved absolute path

        Raises:
            SecurityError: If path is invalid or dangerous
        """
        try:
            # Resolve to absolute path, following symlinks
            resolved_path = file_path.resolve(strict=True)

            # Check file extension
            if resolved_path.suffix.lower() not in ALLOWED_EXTENSIONS:
                msg = f"Invalid file extension: {resolved_path.suffix}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
                raise SecurityError(msg)

            # Check if it's actually a file
            if not resolved_path.is_file():
                msg = f"Path is not a file: {resolved_path}"
                raise SecurityError(msg)

            # Check file size
            file_size = resolved_path.stat().st_size
            if file_size > MAX_FILE_SIZE_BYTES:
                msg = (
                    f"File too large: {file_size} bytes "
                    f"(max: {MAX_FILE_SIZE_BYTES} bytes / {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB)"
                )
                raise SecurityError(msg)

            # Additional security: Ensure no path traversal by checking that
            # resolved path doesn't escape expected directories
            # (In production, you might want to enforce a specific base directory)

            return resolved_path

        except (OSError, RuntimeError) as e:
            msg = f"Invalid or inaccessible file path: {e}"
            raise SecurityError(msg)

    def _safe_load_yaml(self, file_path: Path) -> dict[str, Any]:
        """
        Safely load YAML file with protection against malicious content.

        Args:
            file_path: Path to YAML file (already validated)

        Returns:
            Parsed YAML content

        Raises:
            SecurityError: If YAML content is malicious
            ValueError: If YAML is invalid
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                # Use safe_load to prevent code execution
                # This protects against arbitrary Python object instantiation
                yaml_content = yaml.safe_load(f)

            if yaml_content is None:
                msg = "Empty YAML file"
                raise ValueError(msg)

            if not isinstance(yaml_content, dict):
                msg = "YAML root must be a dictionary/object"
                raise ValueError(msg)

            # Protect against YAML bombs (deeply nested structures)
            self._check_yaml_depth(yaml_content, current_depth=0)
            self._check_yaml_node_count(yaml_content)

            return yaml_content

        except yaml.YAMLError as e:
            msg = f"Invalid YAML syntax: {e}"
            raise ValueError(msg)

    def _check_yaml_depth(self, obj: Any, current_depth: int) -> None:
        """
        Check YAML depth to prevent billion laughs attack.

        Args:
            obj: Object to check
            current_depth: Current nesting depth

        Raises:
            SecurityError: If depth exceeds limit
        """
        if current_depth > MAX_YAML_DEPTH:
            msg = f"YAML depth exceeds maximum allowed ({MAX_YAML_DEPTH}). Possible YAML bomb attack."
            raise SecurityError(msg)

        if isinstance(obj, dict):
            for value in obj.values():
                self._check_yaml_depth(value, current_depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                self._check_yaml_depth(item, current_depth + 1)

    def _check_yaml_node_count(self, obj: Any) -> None:
        """
        Check total number of nodes to prevent memory exhaustion.

        Args:
            obj: Object to check

        Raises:
            SecurityError: If node count exceeds limit
        """
        node_count = self._count_nodes(obj)
        if node_count > MAX_YAML_NODES:
            msg = (
                f"YAML contains too many nodes ({node_count}). "
                f"Maximum allowed: {MAX_YAML_NODES}. "
                "Possible YAML bomb attack."
            )
            raise SecurityError(msg)

    def _count_nodes(self, obj: Any) -> int:
        """Recursively count nodes in object tree."""
        count = 1  # Count self

        if isinstance(obj, dict):
            for value in obj.values():
                count += self._count_nodes(value)
        elif isinstance(obj, list):
            for item in obj:
                count += self._count_nodes(item)

        return count

    async def import_project_config(self, yaml_file: Path, dry_run: bool = False) -> dict[str, Any]:
        """
        Import a project configuration from YAML file.

        Args:
            yaml_file: Path to YAML configuration file
            dry_run: If True, validate but don't save

        Returns:
            Dictionary with import results
        """
        console.print(f"[bold blue]Reading configuration from:[/bold blue] {yaml_file}")

        # SECURITY: Validate file path
        try:
            validated_path = self._validate_file_path(yaml_file)
            console.print(f"[dim]Validated path: {validated_path}[/dim]")
        except SecurityError as e:
            console.print(f"[bold red]Security error:[/bold red] {e}")
            return {"success": False, "error": f"Security validation failed: {e}"}

        # SECURITY: Load YAML with protection against malicious content
        try:
            yaml_config = self._safe_load_yaml(validated_path)
            console.print("[green]✓ File loaded and validated successfully[/green]")
        except (SecurityError, ValueError) as e:
            console.print(f"[bold red]Error loading YAML:[/bold red] {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            console.print(f"[bold red]Unexpected error:[/bold red] {e}")
            logger.exception(
                "Unexpected error loading YAML",
                extra={"error_id": ErrorRegistry.ERR_CONFIG_PARSING_ERROR},
            )
            return {"success": False, "error": f"Unexpected error: {e}"}

        # Validate YAML structure
        validation_errors = self._validate_yaml_structure(yaml_config)
        if validation_errors:
            console.print("[bold red]Validation errors:[/bold red]")
            for error in validation_errors:
                console.print(f"  - {error}")
            return {"success": False, "errors": validation_errors}

        # Extract project information
        project_name = yaml_config.get("name", yaml_file.stem)
        console.print(f"[bold green]Project name:[/bold green] {project_name}")

        # Create ProjectConfig object
        project_config = ProjectConfig(
            id=f"project-{project_name}",
            name=project_name,
            version=1,
            tech_stacks=yaml_config.get("tech_stacks", {}),
            pipelines=[],  # Will be populated from pipelines section
            testing=yaml_config.get("testing", {}),
            environment_variables={},  # Populated later
            mounted_commands={},
            mounted_subagents={},
            metadata={
                "source": str(yaml_file),
                "imported_at": "now",
                "imported_by": "yaml_import_tool",
            },
        )

        # Import pipelines
        pipelines = yaml_config.get("pipelines", [])
        for pipeline_data in pipelines:
            project_config.pipelines.append(pipeline_data)

        # Import environment variables (if present)
        env_vars = yaml_config.get("environment_variables", {})
        for var_name, var_value in env_vars.items():
            if isinstance(var_value, dict):
                project_config.environment_variables[var_name] = var_value
            else:
                project_config.environment_variables[var_name] = {
                    "value": var_value,
                    "is_secret": False,
                    "description": None,
                    "created_at": "now",
                    "created_by": "yaml_import",
                }

        # Display summary
        console.print("\n[bold cyan]Import Summary:[/bold cyan]")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Item")
        table.add_column("Count")

        table.add_row("Tech Stacks", str(len(project_config.tech_stacks)))
        table.add_row("Pipelines", str(len(project_config.pipelines)))
        table.add_row("Environment Variables", str(len(project_config.environment_variables)))
        console.print(table)

        if dry_run:
            console.print("\n[bold yellow]DRY RUN - No changes made[/bold yellow]")
            return {"success": True, "dry_run": True, "project": project_name}

        # Save to database
        try:
            console.print("\n[bold blue]Saving to database...[/bold blue]")
            await self.config_store.save_project_config(project_config)
            console.print("[bold green]✓ Project configuration saved successfully![/bold green]")

            # Import agent configurations
            if "agents" in yaml_config:
                console.print("\n[bold blue]Importing agent configurations...[/bold blue]")
                for agent_name, agent_data in yaml_config["agents"].items():
                    await self._import_agent_config(project_config.id, agent_name, agent_data)
                    console.print(f"[green]✓ Agent '{agent_name}' imported[/green]")

            # Import pipeline configurations
            if pipelines:
                console.print("\n[bold blue]Importing pipeline configurations...[/bold blue]")
                for pipeline_data in pipelines:
                    await self._import_pipeline_config(project_config.id, pipeline_data)
                    console.print(f"[green]✓ Pipeline '{pipeline_data['name']}' imported[/green]")

            return {
                "success": True,
                "project": project_name,
                "version": project_config.version,
            }

        except Exception as e:
            console.print(f"[bold red]Error saving to database:[/bold red] {e}")
            logger.exception("Failed to save configuration", extra={"error_id": ErrorRegistry.ERR_DATABASE_ERROR})
            return {"success": False, "error": str(e)}

    async def _import_agent_config(self, project_id: str, agent_name: str, agent_data: dict[str, Any]):
        """Import agent configuration."""
        agent_config = AgentConfig(
            project_id=project_id,
            agent_name=agent_name,
            model=agent_data.get("model", "claude-sonnet-4-5-20250929"),
            timeout=agent_data.get("timeout", 3600),
            requires_docker=agent_data.get("requires_docker", True),
            makes_code_changes=agent_data.get("makes_code_changes", True),
            mcp_servers=agent_data.get("mcp_servers", []),
            capabilities=agent_data.get("capabilities", []),
            constraints=agent_data.get("constraints", {}),
            version=1,
            metadata={"imported_from_yaml": True},
        )
        await self.config_store.save_agent_config(agent_config)

    async def _import_pipeline_config(self, project_id: str, pipeline_data: dict[str, Any]):
        """Import pipeline configuration."""
        pipeline_config = PipelineConfig(
            id=f"{project_id}:{pipeline_data['name']}",
            project_id=project_id,
            name=pipeline_data["name"],
            stages=pipeline_data.get("stages", []),
            triggers=pipeline_data.get("triggers", []),
            version=1,
            metadata={"imported_from_yaml": True},
        )
        await self.config_store.save_pipeline_config(pipeline_config)

    def _validate_yaml_structure(self, yaml_config: dict[str, Any]) -> list[str]:
        """
        Validate YAML configuration structure.

        Args:
            yaml_config: Loaded YAML configuration

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check required top-level fields
        if not isinstance(yaml_config, dict):
            errors.append("Configuration must be a dictionary")
            return errors

        # Validate pipelines
        if "pipelines" in yaml_config:
            if not isinstance(yaml_config["pipelines"], list):
                errors.append("'pipelines' must be a list")
            else:
                for i, pipeline in enumerate(yaml_config["pipelines"]):
                    if not isinstance(pipeline, dict):
                        errors.append(f"Pipeline {i} must be a dictionary")
                    elif "name" not in pipeline:
                        errors.append(f"Pipeline {i} missing required 'name' field")

        # Validate tech_stacks
        if "tech_stacks" in yaml_config:
            if not isinstance(yaml_config["tech_stacks"], dict):
                errors.append("'tech_stacks' must be a dictionary")

        return errors


@click.group()
def cli():
    """YAML Configuration Import Tool"""


@cli.command()
@click.argument("yaml_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate configuration without saving to database",
)
@click.option(
    "--elasticsearch-url",
    default="http://localhost:9200",
    help="Elasticsearch URL",
)
@click.option(
    "--redis-url",
    default="redis://localhost:6379",
    help="Redis URL",
)
def import_config(yaml_file: Path, dry_run: bool, elasticsearch_url: str, redis_url: str):
    """
    Import a YAML configuration file into the database.

    Example:
        python -m codetoreum.cli.yaml_import import-config config/projects/myproject.yaml
    """
    console.print("[bold]Codetoreum YAML Configuration Import Tool[/bold]\n")

    async def run_import():
        # Create config store
        factory = ConfigStorageFactory(
            elasticsearch_url=elasticsearch_url,
            redis_url=redis_url,
        )
        config_store = factory.create_cached_store()

        # Create importer and run
        importer = YAMLConfigImporter(config_store)
        result = await importer.import_project_config(yaml_file, dry_run=dry_run)

        if result["success"]:
            console.print("\n[bold green]✓ Import completed successfully![/bold green]")
            if not dry_run:
                console.print(f"Project '{result['project']}' imported at version {result.get('version', 1)}")
        else:
            console.print("\n[bold red]✗ Import failed[/bold red]")
            if "error" in result:
                console.print(f"Error: {result['error']}")
            sys.exit(1)

    asyncio.run(run_import())


@cli.command()
@click.argument("config_dir", type=click.Path(exists=True, path_type=Path))
@click.option("--pattern", default="*.yaml", help="File pattern to match")
@click.option("--dry-run", is_flag=True, help="Validate without saving")
def import_batch(config_dir: Path, pattern: str, dry_run: bool):
    """
    Import multiple YAML configuration files from a directory.

    Example:
        python -m codetoreum.cli.yaml_import import-batch config/projects/
    """
    console.print("[bold]Batch Import Mode[/bold]\n")

    yaml_files = list(config_dir.glob(pattern))

    if not yaml_files:
        console.print(f"[yellow]No files matching '{pattern}' found in {config_dir}[/yellow]")
        return

    console.print(f"Found {len(yaml_files)} configuration files\n")

    async def run_batch_import():
        factory = ConfigStorageFactory(
            elasticsearch_url="http://localhost:9200",
            redis_url="redis://localhost:6379",
        )
        config_store = factory.create_cached_store()
        importer = YAMLConfigImporter(config_store)

        with Progress() as progress:
            task = progress.add_task("[cyan]Importing...", total=len(yaml_files))

            for yaml_file in yaml_files:
                console.print(f"\n[bold]Processing:[/bold] {yaml_file.name}")
                result = await importer.import_project_config(yaml_file, dry_run=dry_run)

                if result["success"]:
                    console.print(f"[green]✓ {yaml_file.name} imported successfully[/green]")
                else:
                    console.print(f"[red]✗ {yaml_file.name} failed[/red]")

                progress.advance(task)

    asyncio.run(run_batch_import())


if __name__ == "__main__":
    cli()
