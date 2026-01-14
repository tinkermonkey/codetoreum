"""Secondary adapters for Codetoreum.

This package contains production implementations of output port interfaces,
plus mock implementations for testing and simulation.
"""

from codetoreum.adapters.secondary.cached_config_store import CachedConfigStore
from codetoreum.adapters.secondary.claude_code_adapter import (
    ClaudeCodeAdapter,
    ClaudeCodeConfig,
)
from codetoreum.adapters.secondary.configurable_identity_service import (
    ConfigurableIdentityService,
)
from codetoreum.adapters.secondary.config_storage_factory import (
    create_cached_config_store,
    create_elasticsearch_config_storage,
    create_redis_config_cache,
)
from codetoreum.adapters.secondary.docker_container_adapter import (
    DockerConfig,
    DockerContainerAdapter,
)
from codetoreum.adapters.secondary.elasticsearch_config_storage import (
    ElasticsearchConfigStorage,
)
from codetoreum.adapters.secondary.git_repository_adapter import (
    GitConfig,
    GitRepositoryAdapter,
)
from codetoreum.adapters.secondary.github_board_adapter import (
    GitHubBoardAdapter,
)
from codetoreum.adapters.secondary.github_code_review_adapter import (
    GitHubCodeReviewAdapter,
)
from codetoreum.adapters.secondary.github_ticket_adapter import (
    GitHubConfig,
    GitHubTicketAdapter,
)
from codetoreum.adapters.secondary.in_memory_pipeline_lock_service import (
    InMemoryPipelineLockService,
)
from codetoreum.adapters.secondary.mock_code_review_adapter import (
    MockCodeReviewAdapter,
)
from codetoreum.adapters.secondary.mock_discussion_adapter import MockDiscussionAdapter
from codetoreum.adapters.secondary.mock_event_emitter import MockEventEmitter
from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter

__all__ = [
    # GitHub Ticket System
    "GitHubTicketAdapter",
    "GitHubConfig",
    # GitHub Board System
    "GitHubBoardAdapter",
    # GitHub Code Review
    "GitHubCodeReviewAdapter",
    # Claude Code LLM Provider
    "ClaudeCodeAdapter",
    "ClaudeCodeConfig",
    # Docker Container Runtime
    "DockerContainerAdapter",
    "DockerConfig",
    # Git Repository
    "GitRepositoryAdapter",
    "GitConfig",
    # Configuration Storage
    "ElasticsearchConfigStorage",
    "CachedConfigStore",
    "create_elasticsearch_config_storage",
    "create_redis_config_cache",
    "create_cached_config_store",
    # Mock Adapters for Testing
    "MockEventEmitter",
    "MockBoardAdapter",
    "MockDiscussionAdapter",
    "MockCodeReviewAdapter",
    "InMemoryPipelineLockService",
    "ConfigurableIdentityService",
]
