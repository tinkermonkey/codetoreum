"""Unit tests for ES config storage legacy-document deserialisation (DEF-020).

The DEF-020 cleanup removed the flat ``model`` / ``timeout`` /
``requires_docker`` fields from ``AgentConfig``. Production ES indexes
may still contain documents written under the old shape. ``_deserialize_agent``
must synthesise an ``AgentInvocationConfig`` from those legacy keys so
old documents continue to load.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from codetoreum.adapters.secondary.elasticsearch_config_storage import ElasticsearchConfigStorage
from codetoreum.domain.coding_agent_types import InvocationMode


def _make_storage() -> ElasticsearchConfigStorage:
    """Construct an ES storage instance with mocked dependencies (no I/O)."""
    storage = ElasticsearchConfigStorage.__new__(ElasticsearchConfigStorage)
    storage._es_client = MagicMock()
    storage._encryption_service = None
    storage._project_index = "codetoreum-projects"
    storage._agent_index = "codetoreum-agents"
    storage._pipeline_index = "codetoreum-pipelines"
    storage._workflow_template_index = "codetoreum-workflow-templates"
    return storage


def test_deserialize_legacy_document_with_requires_docker_true() -> None:
    """A pre-DEF-020 ES document with flat fields and no invocation block
    must deserialize into an ``AgentConfig`` with an invocation block
    synthesised from the legacy flat fields. ``requires_docker=True``
    becomes ``InvocationMode.CONTAINERIZED``."""
    storage = _make_storage()
    legacy_doc: dict[str, Any] = {
        "project_id": "project-1",
        "agent_name": "coder",
        "model": "claude-sonnet-4-5",
        "timeout": 3600,
        "requires_docker": True,
        "makes_code_changes": True,
        "mcp_servers": ["artifacts"],
        "capabilities": ["code_generation"],
        "constraints": {},
        "version": 1,
        "created_at": None,
        "updated_at": None,
        "metadata": {},
    }
    config = storage._deserialize_agent(legacy_doc)
    assert config.project_id == "project-1"
    assert config.agent_name == "coder"
    assert config.makes_code_changes is True
    assert list(config.mcp_servers) == ["artifacts"]
    assert config.invocation.mode == InvocationMode.CONTAINERIZED
    assert config.invocation.model == "claude-sonnet-4-5"
    assert config.invocation.timeout_seconds == 3600
    assert config.invocation.mode_config == {"image": "codetoreum-agent:latest"}


def test_deserialize_legacy_document_with_requires_docker_false() -> None:
    """A pre-DEF-020 ES document with ``requires_docker=False`` maps to
    ``InvocationMode.HOST`` and an empty ``mode_config``."""
    storage = _make_storage()
    legacy_doc: dict[str, Any] = {
        "project_id": "project-1",
        "agent_name": "host-coder",
        "model": "claude-sonnet-4-6",
        "timeout": 1800,
        "requires_docker": False,
        "makes_code_changes": True,
        "mcp_servers": [],
        "capabilities": [],
        "constraints": {},
        "version": 1,
        "created_at": None,
        "updated_at": None,
        "metadata": {},
    }
    config = storage._deserialize_agent(legacy_doc)
    assert config.invocation.mode == InvocationMode.HOST
    assert config.invocation.model == "claude-sonnet-4-6"
    assert config.invocation.timeout_seconds == 1800
    assert config.invocation.mode_config == {}


def test_deserialize_new_document_uses_invocation_block_directly() -> None:
    """A new-style ES document with an ``invocation`` block is deserialised
    straight through — no legacy translation path."""
    storage = _make_storage()
    new_doc: dict[str, Any] = {
        "project_id": "project-1",
        "agent_name": "coder",
        "makes_code_changes": True,
        "mcp_servers": [],
        "capabilities": [],
        "constraints": {},
        "version": 1,
        "created_at": None,
        "updated_at": None,
        "metadata": {},
        "coding_agent": "claude-code",
        "invocation": {
            "mode": "containerized",
            "model": "claude-sonnet-4-6",
            "timeout_seconds": 3600,
            "mode_config": {"image": "codetoreum-agent:latest"},
            "cost_limit_usd": None,
        },
    }
    config = storage._deserialize_agent(new_doc)
    assert config.invocation.mode == InvocationMode.CONTAINERIZED
    assert config.invocation.model == "claude-sonnet-4-6"
    assert config.invocation.timeout_seconds == 3600
    assert config.coding_agent == "claude-code"


def test_serialize_does_not_write_legacy_flat_fields() -> None:
    """After DEF-020, ``_serialize_agent`` must not write the legacy
    ``model`` / ``timeout`` / ``requires_docker`` keys — the
    ``invocation`` block is the sole source of truth on the wire."""
    storage = _make_storage()
    legacy_doc: dict[str, Any] = {
        "project_id": "project-1",
        "agent_name": "coder",
        "model": "claude-sonnet-4-5",
        "timeout": 3600,
        "requires_docker": True,
        "makes_code_changes": True,
        "mcp_servers": [],
        "capabilities": [],
        "constraints": {},
        "version": 1,
        "created_at": None,
        "updated_at": None,
        "metadata": {},
    }
    config = storage._deserialize_agent(legacy_doc)
    rewritten = storage._serialize_agent(config)
    assert "model" not in rewritten
    assert "timeout" not in rewritten
    assert "requires_docker" not in rewritten
    assert "invocation" in rewritten
    assert rewritten["invocation"]["model"] == "claude-sonnet-4-5"
    assert rewritten["invocation"]["timeout_seconds"] == 3600
    assert rewritten["invocation"]["mode"] == "containerized"
