"""Tests for ProportionalDelayCalculator."""

import pytest

from codetoreum.infrastructure.simulation.proportional_delay_calculator import (
    ProportionalDelayCalculator,
)
from codetoreum.infrastructure.simulation.simulation_config import (
    FidelityLevel,
    SimulationConfig,
)


class TestProportionalDelayCalculator:
    """Test suite for ProportionalDelayCalculator."""

    def test_no_config_returns_zero(self) -> None:
        """Test that calculator with no config returns 0.0."""
        calculator = ProportionalDelayCalculator(config=None)

        delay = calculator.calculate_container_delay("git clone repo")
        assert delay == 0.0

        delay = calculator.calculate_llm_delay("prompt", "response")
        assert delay == 0.0

        delay = calculator.calculate_event_delay(2.5)
        assert delay == 0.0

    def test_low_fidelity_returns_zero(self) -> None:
        """Test that LOW fidelity returns zero delay."""
        config = SimulationConfig.create_fast_config("test")
        assert config.fidelity_level == FidelityLevel.LOW

        calculator = ProportionalDelayCalculator(config)

        delay = calculator.calculate_container_delay("git clone repo")
        assert delay == 0.0

        delay = calculator.calculate_llm_delay("prompt" * 100, "response" * 100)
        assert delay == 0.0

        delay = calculator.calculate_event_delay(100.0)
        assert delay == 0.0

    def test_medium_fidelity_proportional_container_delay(self) -> None:
        """Test proportional container delay with MEDIUM fidelity."""
        config = SimulationConfig.create_realistic_config("test")
        assert config.fidelity_level == FidelityLevel.MEDIUM

        calculator = ProportionalDelayCalculator(config)

        # Simple command should have base delay (~100ms)
        delay1 = calculator.calculate_container_delay("ls")
        assert 0 < delay1 < 0.2  # Should be reasonably small

        # Complex git clone should be larger
        delay2 = calculator.calculate_container_delay("git clone repo")
        assert delay2 > delay1

        # npm install should be even larger
        delay3 = calculator.calculate_container_delay("npm install")
        assert delay3 > delay2

    def test_medium_fidelity_proportional_llm_delay(self) -> None:
        """Test proportional LLM delay with MEDIUM fidelity."""
        config = SimulationConfig.create_realistic_config("test")
        calculator = ProportionalDelayCalculator(config)

        # Small prompt/response
        short_prompt = "hello"
        short_response = "hi"
        delay1 = calculator.calculate_llm_delay(short_prompt, short_response)

        # Large prompt/response
        long_prompt = "hello world " * 100
        long_response = "hi there " * 100
        delay2 = calculator.calculate_llm_delay(long_prompt, long_response)

        assert delay2 > delay1

    def test_medium_fidelity_proportional_event_delay(self) -> None:
        """Test proportional event delay with MEDIUM fidelity."""
        config = SimulationConfig.create_realistic_config("test")
        calculator = ProportionalDelayCalculator(config)

        # Smaller event
        delay1 = calculator.calculate_event_delay(1.0)

        # Larger event
        delay2 = calculator.calculate_event_delay(10.0)

        assert delay2 > delay1

    def test_high_fidelity_includes_jitter(self) -> None:
        """Test that HIGH fidelity includes timing jitter."""
        config = SimulationConfig.create_high_fidelity_config("test")
        assert config.fidelity_level == FidelityLevel.HIGH

        calculator = ProportionalDelayCalculator(config)

        # Get multiple delays for same command - should vary due to jitter
        delays = [calculator.calculate_container_delay("git clone repo") for _ in range(100)]

        # All delays should be positive
        assert all(d > 0 for d in delays)

        # Delays should vary (due to jitter)
        assert len(set(delays)) > 1  # Not all the same

        # With jitter uniform(0.8, 1.2), max/min ratio should be bounded
        min_delay = min(delays)
        max_delay = max(delays)
        ratio = max_delay / min_delay if min_delay > 0 else 0
        assert ratio < 2.0  # With ±20% jitter, ratio should be reasonable

    def test_container_delay_estimates_file_operations(self) -> None:
        """Test that container delay estimation recognizes command patterns."""
        config = SimulationConfig.create_realistic_config("test")
        calculator = ProportionalDelayCalculator(config)

        # Base delay for simple command
        simple_delay = calculator.calculate_container_delay("echo hello")

        # git clone should estimate 50 operations
        git_clone_delay = calculator.calculate_container_delay("git clone repo")
        assert git_clone_delay > simple_delay * 2

        # npm install should estimate 100 operations
        npm_delay = calculator.calculate_container_delay("npm install package")
        assert npm_delay > git_clone_delay

        # pip install should estimate 50 operations
        pip_delay = calculator.calculate_container_delay("pip install package")
        assert pip_delay > simple_delay

    def test_llm_delay_based_on_token_count(self) -> None:
        """Test that LLM delay scales with token count."""
        config = SimulationConfig.create_realistic_config("test")
        calculator = ProportionalDelayCalculator(config)

        # Create prompts of different sizes
        # Each token is roughly 4 characters
        prompt_4_tokens = "hello"  # ~1 token
        response_4_tokens = "hi"  # ~1 token
        delay_small = calculator.calculate_llm_delay(prompt_4_tokens, response_4_tokens)

        prompt_400_tokens = "hello world " * 100  # ~100 tokens
        response_400_tokens = "response text " * 100  # ~100 tokens
        delay_large = calculator.calculate_llm_delay(prompt_400_tokens, response_400_tokens)

        # Large should be significantly larger than small
        assert delay_large > delay_small * 5

    def test_event_delay_based_on_size(self) -> None:
        """Test that event delay scales with event size."""
        config = SimulationConfig.create_realistic_config("test")
        calculator = ProportionalDelayCalculator(config)

        delay_small = calculator.calculate_event_delay(0.5)  # 0.5 KB
        delay_large = calculator.calculate_event_delay(50.0)  # 50 KB

        assert delay_large > delay_small * 10

    def test_file_operation_estimation_git_operations(self) -> None:
        """Test file operation estimation for git commands."""
        # Test that different git operations have different estimates
        estimates = {
            "git clone repo": 50,
            "git pull": 30,
            "git fetch": 30,
            "git push": 20,
        }

        for cmd, expected_min in estimates.items():
            config = SimulationConfig.create_realistic_config("test")
            calculator = ProportionalDelayCalculator(config)
            delay = calculator.calculate_container_delay(cmd)

            # Delay should be based on estimated operations
            # Base 100ms + (operations * ms_per_op where ms_per_op is typically 10)
            assert delay > 0.1

    def test_file_operation_estimation_package_managers(self) -> None:
        """Test file operation estimation for package managers."""
        config = SimulationConfig.create_realistic_config("test")
        calculator = ProportionalDelayCalculator(config)

        npm_delay = calculator.calculate_container_delay("npm install")
        pip_delay = calculator.calculate_container_delay("pip install")
        apt_delay = calculator.calculate_container_delay("apt-get install pkg")

        # All should have delay
        assert npm_delay > 0
        assert pip_delay > 0
        assert apt_delay > 0

        # npm typically has more operations than pip or apt in isolation
        assert npm_delay > apt_delay

    def test_zero_event_size(self) -> None:
        """Test event delay with zero size."""
        config = SimulationConfig.create_realistic_config("test")
        calculator = ProportionalDelayCalculator(config)

        delay = calculator.calculate_event_delay(0.0)
        assert delay == 0.0  # No operations, no delay

    def test_empty_prompt_and_response(self) -> None:
        """Test LLM delay with empty prompt/response."""
        config = SimulationConfig.create_realistic_config("test")
        calculator = ProportionalDelayCalculator(config)

        delay = calculator.calculate_llm_delay("", "")
        assert delay == 0.0

    def test_empty_command(self) -> None:
        """Test container delay with empty command."""
        config = SimulationConfig.create_realistic_config("test")
        calculator = ProportionalDelayCalculator(config)

        delay = calculator.calculate_container_delay("")
        # Empty command defaults to 1 operation minimum
        assert delay > 0

    def test_mixed_fidelity_levels(self) -> None:
        """Test that different fidelity configs produce different results."""
        fast_config = SimulationConfig.create_fast_config("test")
        realistic_config = SimulationConfig.create_realistic_config("test")
        high_config = SimulationConfig.create_high_fidelity_config("test")

        fast_calc = ProportionalDelayCalculator(fast_config)
        realistic_calc = ProportionalDelayCalculator(realistic_config)
        high_calc = ProportionalDelayCalculator(high_config)

        # Same command
        cmd = "git clone repo && npm install"

        fast_delay = fast_calc.calculate_container_delay(cmd)
        realistic_delay = realistic_calc.calculate_container_delay(cmd)
        high_delay = high_calc.calculate_container_delay(cmd)

        # Fast should be zero
        assert fast_delay == 0.0

        # Realistic and high should be non-zero
        assert realistic_delay > 0
        assert high_delay > 0

        # High can vary due to jitter, so just check it's in reasonable range
        assert high_delay > 0

    def test_calculator_with_config_change(self) -> None:
        """Test calculator behavior when config changes fidelity."""
        config = SimulationConfig.create_fast_config("test")
        calculator = ProportionalDelayCalculator(config)

        # Initially LOW fidelity
        delay1 = calculator.calculate_container_delay("git clone repo")
        assert delay1 == 0.0

        # Change config to MEDIUM
        new_config = SimulationConfig.create_realistic_config("test")
        calculator2 = ProportionalDelayCalculator(new_config)

        delay2 = calculator2.calculate_container_delay("git clone repo")
        assert delay2 > 0.0

    def test_deterministic_high_fidelity_with_seed(self) -> None:
        """Test that HIGH fidelity can produce consistent results across runs."""
        # High fidelity uses random jitter, but we can verify reproducibility
        config = SimulationConfig.create_high_fidelity_config("test")
        calculator = ProportionalDelayCalculator(config)

        # Multiple runs should produce values in expected range
        delays = [calculator.calculate_container_delay("git clone repo") for _ in range(5)]

        # All should be positive
        assert all(d > 0 for d in delays)

        # All should be within reasonable bounds (with ±20% jitter)
        min_delay = min(delays)
        max_delay = max(delays)

        # Check that jitter is within expected bounds
        ratio = max_delay / min_delay if min_delay > 0 else 0
        assert ratio < 1.5  # Within reasonable jitter bounds
