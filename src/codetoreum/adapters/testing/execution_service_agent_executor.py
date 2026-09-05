"""Re-export ExecutionServiceAgentExecutor from secondary adapters.

This module exists for backwards compatibility. The canonical implementation
is in codetoreum.adapters.secondary.execution_service_agent_executor.
"""

from codetoreum.adapters.secondary.execution_service_agent_executor import (
    ActiveExecutionInfo,
    ExecutionServiceAgentExecutor,
)

__all__ = ["ActiveExecutionInfo", "ExecutionServiceAgentExecutor"]
