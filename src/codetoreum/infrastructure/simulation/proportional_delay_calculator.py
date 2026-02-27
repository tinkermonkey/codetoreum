"""Centralized calculator for fidelity-aware proportional delays in simulation.

The ProportionalDelayCalculator abstracts delay calculation logic for different
component types (LLM, container, events) based on fidelity level and workload size.

This replaces inline _calculate_delay_seconds() methods in individual adapters,
enabling consistent delay calculation across the simulation framework.

Delay calculation depends on fidelity level:

- LOW: No delays (preconfigured outcomes, fastest execution ~100x)
- MEDIUM: Proportional delays based on workload (causal linking enabled, ~10-50x)
- HIGH: Full delays with realistic jitter (highest fidelity, ~1-5x)

Example:
    config = SimulationConfig.create_realistic_config()
    calculator = ProportionalDelayCalculator(config)

    # Calculate container delay based on command complexity
    delay = calculator.calculate_container_delay("git clone repo && npm install")

    # Calculate LLM delay based on prompt and response size
    delay = calculator.calculate_llm_delay(prompt, response)

    # Calculate event processing delay based on event size
    delay = calculator.calculate_event_delay(event_size_kb=2.5)
"""

import random
import re
from typing import Optional

from codetoreum.infrastructure.simulation.simulation_config import (
    FidelityLevel,
    SimulationConfig,
)


class ProportionalDelayCalculator:
    """Calculate fidelity-aware delays for simulation components.

    Provides consistent delay calculation based on:
    - Fidelity level (LOW/MEDIUM/HIGH)
    - Workload size (tokens, file operations, event size)
    - Configurable proportional timing parameters
    """

    def __init__(self, config: Optional[SimulationConfig] = None) -> None:
        """Initialize the calculator with simulation configuration.

        Args:
            config: SimulationConfig instance. If None, all delays return 0.0
        """
        self._config = config

    def calculate_container_delay(self, command: str) -> float:
        """Calculate delay for container command execution.

        Delay is proportional to estimated file operations in the command.
        Base delay of 100ms plus 10ms per estimated file operation.

        Args:
            command: Shell command being executed

        Returns:
            Delay in seconds
        """
        if not self._config:
            return 0.0

        if self._config.fidelity_level == FidelityLevel.LOW:
            return 0.0

        file_operations = self._estimate_file_operations(command)
        delay_seconds = self._calculate_proportional_delay(
            base_ms=100,
            operation_count=file_operations,
            ms_per_operation=self._config.ms_per_file_operation,
        )

        return delay_seconds

    def calculate_llm_delay(self, prompt: str, response: str) -> float:
        """Calculate delay for LLM execution.

        Delay is proportional to total tokens (prompt + response).
        Uses 4 characters per token as approximation.

        Args:
            prompt: LLM prompt text
            response: LLM response text

        Returns:
            Delay in seconds
        """
        if not self._config:
            return 0.0

        if self._config.fidelity_level == FidelityLevel.LOW:
            return 0.0

        prompt_tokens = len(prompt) / 4.0  # ~4 chars per token
        response_tokens = len(response) / 4.0
        total_tokens = prompt_tokens + response_tokens

        delay_seconds = self._calculate_proportional_delay(
            base_ms=0,
            operation_count=total_tokens,
            ms_per_operation=self._config.ms_per_token,
        )

        return delay_seconds

    def calculate_event_delay(self, event_size_kb: float) -> float:
        """Calculate delay for event processing.

        Delay is proportional to event size in kilobytes.

        Args:
            event_size_kb: Event size in kilobytes

        Returns:
            Delay in seconds
        """
        if not self._config:
            return 0.0

        if self._config.fidelity_level == FidelityLevel.LOW:
            return 0.0

        delay_seconds = self._calculate_proportional_delay(
            base_ms=0,
            operation_count=event_size_kb,
            ms_per_operation=self._config.ms_per_event,
        )

        return delay_seconds

    def _calculate_proportional_delay(
        self,
        base_ms: float,
        operation_count: float,
        ms_per_operation: float,
    ) -> float:
        """Core proportional delay calculation with fidelity support.

        Args:
            base_ms: Base delay in milliseconds
            operation_count: Number of operations to account for
            ms_per_operation: Milliseconds per operation

        Returns:
            Delay in seconds
        """
        if not self._config:
            return 0.0

        if self._config.fidelity_level == FidelityLevel.LOW:
            return 0.0

        # Calculate total delay
        operation_delay_ms = operation_count * ms_per_operation
        total_delay_ms = base_ms + operation_delay_ms
        delay_seconds = total_delay_ms / 1000.0

        # Add jitter for HIGH fidelity
        if self._config.fidelity_level == FidelityLevel.HIGH:
            # ±20% jitter
            jitter_factor = random.uniform(0.8, 1.2)
            delay_seconds = delay_seconds * jitter_factor

        return delay_seconds

    @staticmethod
    def _estimate_file_operations(command: str) -> int:
        """Estimate number of file operations in a shell command.

        Heuristic estimation based on command patterns:
        - git clone/pull/fetch: 50 operations (network + file I/O)
        - npm install: 100 operations (dependency resolution + I/O)
        - cp/mv: 1 operation per file
        - find/grep: 1 operation per match
        - tar/zip: 50 base + 1 per file

        Args:
            command: Shell command string

        Returns:
            Estimated number of file operations
        """
        count = 0

        # Major repo operations
        if re.search(r"git\s+clone", command, re.IGNORECASE):
            count += 50
        elif re.search(r"git\s+(pull|fetch)", command, re.IGNORECASE):
            count += 30
        elif re.search(r"git\s+push", command, re.IGNORECASE):
            count += 20

        # Package managers
        if re.search(r"npm\s+install", command, re.IGNORECASE):
            count += 100
        elif re.search(r"pip\s+install", command, re.IGNORECASE):
            count += 50
        elif re.search(r"apt-get\s+install", command, re.IGNORECASE):
            count += 30

        # File operations
        cp_matches = re.findall(r"cp\s+", command, re.IGNORECASE)
        count += len(cp_matches)

        mv_matches = re.findall(r"mv\s+", command, re.IGNORECASE)
        count += len(mv_matches)

        # Archive operations
        if re.search(r"tar\s+", command, re.IGNORECASE):
            count += 50
        if re.search(r"zip\s+", command, re.IGNORECASE):
            count += 50

        # Directory traversal
        if re.search(r"find\s+", command, re.IGNORECASE):
            count += 20
        if re.search(r"grep\s+", command, re.IGNORECASE):
            count += 10

        # Default minimum for any command
        if count == 0:
            count = 1

        return count
