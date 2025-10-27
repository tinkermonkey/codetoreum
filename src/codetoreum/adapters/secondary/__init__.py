"""Secondary adapters for Codetoreum.

This package contains production implementations of output port interfaces.
"""

from codetoreum.adapters.secondary.claude_code_adapter import (
    ClaudeCodeAdapter,
    ClaudeCodeConfig,
)
from codetoreum.adapters.secondary.docker_container_adapter import (
    DockerConfig,
    DockerContainerAdapter,
)
from codetoreum.adapters.secondary.git_repository_adapter import (
    GitConfig,
    GitRepositoryAdapter,
)
from codetoreum.adapters.secondary.github_ticket_adapter import (
    GitHubConfig,
    GitHubTicketAdapter,
)

__all__ = [
    # GitHub Ticket System
    "GitHubTicketAdapter",
    "GitHubConfig",
    # Claude Code LLM Provider
    "ClaudeCodeAdapter",
    "ClaudeCodeConfig",
    # Docker Container Runtime
    "DockerContainerAdapter",
    "DockerConfig",
    # Git Repository
    "GitRepositoryAdapter",
    "GitConfig",
]
