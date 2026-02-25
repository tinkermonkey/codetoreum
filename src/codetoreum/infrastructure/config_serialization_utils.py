"""
Shared serialization/deserialization utilities for configuration storage.

This module provides common serialization logic used by both Elasticsearch
storage and Redis cache implementations, eliminating code duplication.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from codetoreum.domain.models import (
    AgentConfig,
    EnvironmentVariable,
    PipelineConfig,
    ProjectConfig,
    WorkflowConfig,
)


def validate_id(value: str, name: str = "id") -> None:
    """
    Validate that an ID is non-empty and properly formatted.

    Args:
        value: The ID value to validate
        name: The name of the field (for error messages)

    Raises:
        ValueError: If the ID is invalid
    """
    if not value or not isinstance(value, str):
        raise ValueError(f"{name} must be a non-empty string")
    if not value.strip():
        raise ValueError(f"{name} cannot be whitespace only")


def validate_name(value: str) -> None:
    """
    Validate that a name is non-empty and properly formatted.

    Args:
        value: The name value to validate

    Raises:
        ValueError: If the name is invalid
    """
    if not value or not isinstance(value, str):
        raise ValueError("name must be a non-empty string")
    if not value.strip():
        raise ValueError("name cannot be whitespace only")


def serialize_datetime(dt: datetime | None) -> str | None:
    """Serialize datetime to ISO format string."""
    return dt.isoformat() if dt else None


def deserialize_datetime(value: str | None) -> datetime | None:
    """Deserialize ISO format string to datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def serialize_uuid(uuid_obj: UUID | None) -> str | None:
    """Serialize UUID to string."""
    return str(uuid_obj) if uuid_obj else None


def deserialize_uuid(value: str | None) -> UUID | None:
    """Deserialize string to UUID."""
    if not value:
        return None
    try:
        return UUID(value) if isinstance(value, str) else value
    except (ValueError, TypeError):
        return None


def project_config_to_dict(config: ProjectConfig) -> dict[str, Any]:
    """
    Serialize ProjectConfig to dictionary.

    Args:
        config: The ProjectConfig instance

    Returns:
        Dictionary representation suitable for storage
    """
    return {
        "id": config.id,
        "name": config.name,
        "repository_url": config.repository_url,
        "default_branch": config.default_branch,
        "workflow_id": config.workflow_id,
        "environment_variables": {k: v for k, v in config.environment_variables.items()},
        "settings": {k: v for k, v in config.settings.items()},
        "created_at": serialize_datetime(config.created_at),
        "updated_at": serialize_datetime(config.updated_at),
    }


def dict_to_project_config(data: dict[str, Any]) -> ProjectConfig:
    """
    Deserialize dictionary to ProjectConfig.

    Args:
        data: Dictionary representation from storage

    Returns:
        ProjectConfig instance
    """
    return ProjectConfig(
        id=data["id"],
        name=data["name"],
        repository_url=data["repository_url"],
        default_branch=data.get("default_branch", "main"),
        workflow_id=data.get("workflow_id"),
        environment_variables=data.get("environment_variables", {}),
        settings=data.get("settings", {}),
        created_at=deserialize_datetime(data.get("created_at")),
        updated_at=deserialize_datetime(data.get("updated_at")),
    )


def agent_config_to_dict(config: AgentConfig) -> dict[str, Any]:
    """
    Serialize AgentConfig to dictionary.

    Args:
        config: The AgentConfig instance

    Returns:
        Dictionary representation suitable for storage
    """
    return {
        "id": config.id,
        "name": config.name,
        "type": config.type,
        "capabilities": list(config.capabilities),
        "llm_config": {k: v for k, v in config.llm_config.items()},
        "container_config": {k: v for k, v in config.container_config.items()},
        "prompts": {k: v for k, v in config.prompts.items()},
        "created_at": serialize_datetime(config.created_at),
        "updated_at": serialize_datetime(config.updated_at),
    }


def dict_to_agent_config(data: dict[str, Any]) -> AgentConfig:
    """
    Deserialize dictionary to AgentConfig.

    Args:
        data: Dictionary representation from storage

    Returns:
        AgentConfig instance
    """
    return AgentConfig(
        id=data["id"],
        name=data["name"],
        type=data["type"],
        capabilities=set(data.get("capabilities", [])),
        llm_config=data.get("llm_config", {}),
        container_config=data.get("container_config", {}),
        prompts=data.get("prompts", {}),
        created_at=deserialize_datetime(data.get("created_at")),
        updated_at=deserialize_datetime(data.get("updated_at")),
    )


def pipeline_config_to_dict(config: PipelineConfig) -> dict[str, Any]:
    """
    Serialize PipelineConfig to dictionary.

    Args:
        config: The PipelineConfig instance

    Returns:
        Dictionary representation suitable for storage
    """
    return {
        "id": config.id,
        "name": config.name,
        "description": config.description,
        "stages": [
            {
                "name": stage.name,
                "agent_id": stage.agent_id,
                "entry_conditions": list(stage.entry_conditions),
                "exit_conditions": list(stage.exit_conditions),
                "timeout_seconds": stage.timeout_seconds,
                "retry_policy": {k: v for k, v in stage.retry_policy.items()},
                "prompts": {k: v for k, v in stage.prompts.items()},
            }
            for stage in config.stages
        ],
        "created_at": serialize_datetime(config.created_at),
        "updated_at": serialize_datetime(config.updated_at),
    }


def dict_to_pipeline_config(data: dict[str, Any]) -> PipelineConfig:
    """
    Deserialize dictionary to PipelineConfig.

    Args:
        data: Dictionary representation from storage

    Returns:
        PipelineConfig instance
    """
    from codetoreum.domain.models import PipelineStageConfig

    return PipelineConfig(
        id=data["id"],
        name=data["name"],
        description=data.get("description", ""),
        stages=[
            PipelineStageConfig(
                name=stage["name"],
                agent_id=stage["agent_id"],
                entry_conditions=set(stage.get("entry_conditions", [])),
                exit_conditions=set(stage.get("exit_conditions", [])),
                timeout_seconds=stage.get("timeout_seconds", 3600),
                retry_policy=stage.get("retry_policy", {}),
                prompts=stage.get("prompts", {}),
            )
            for stage in data.get("stages", [])
        ],
        created_at=deserialize_datetime(data.get("created_at")),
        updated_at=deserialize_datetime(data.get("updated_at")),
    )


def workflow_config_to_dict(config: WorkflowConfig) -> dict[str, Any]:
    """
    Serialize WorkflowConfig to dictionary.

    Args:
        config: The WorkflowConfig instance

    Returns:
        Dictionary representation suitable for storage
    """
    return {
        "id": config.id,
        "name": config.name,
        "description": config.description,
        "pipeline_id": config.pipeline_id,
        "trigger_conditions": list(config.trigger_conditions),
        "settings": {k: v for k, v in config.settings.items()},
        "created_at": serialize_datetime(config.created_at),
        "updated_at": serialize_datetime(config.updated_at),
    }


def dict_to_workflow_config(data: dict[str, Any]) -> WorkflowConfig:
    """
    Deserialize dictionary to WorkflowConfig.

    Args:
        data: Dictionary representation from storage

    Returns:
        WorkflowConfig instance
    """
    return WorkflowConfig(
        id=data["id"],
        name=data["name"],
        description=data.get("description", ""),
        pipeline_id=data["pipeline_id"],
        trigger_conditions=set(data.get("trigger_conditions", [])),
        settings=data.get("settings", {}),
        created_at=deserialize_datetime(data.get("created_at")),
        updated_at=deserialize_datetime(data.get("updated_at")),
    )


def environment_variable_to_dict(env_var: EnvironmentVariable) -> dict[str, Any]:
    """
    Serialize EnvironmentVariable to dictionary.

    Args:
        env_var: The EnvironmentVariable instance

    Returns:
        Dictionary representation suitable for storage
    """
    return {
        "id": env_var.id,
        "project_id": env_var.project_id,
        "name": env_var.name,
        "value": env_var.value,
        "is_secret": env_var.is_secret,
        "description": env_var.description,
        "created_at": serialize_datetime(env_var.created_at),
        "updated_at": serialize_datetime(env_var.updated_at),
    }


def dict_to_environment_variable(data: dict[str, Any]) -> EnvironmentVariable:
    """
    Deserialize dictionary to EnvironmentVariable.

    Args:
        data: Dictionary representation from storage

    Returns:
        EnvironmentVariable instance
    """
    return EnvironmentVariable(
        id=data["id"],
        project_id=data["project_id"],
        name=data["name"],
        value=data["value"],
        is_secret=data.get("is_secret", False),
        description=data.get("description", ""),
        created_at=deserialize_datetime(data.get("created_at")),
        updated_at=deserialize_datetime(data.get("updated_at")),
    )
