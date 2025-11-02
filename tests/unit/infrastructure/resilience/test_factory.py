"""Tests for resilience factory."""

import pytest

from codetoreum.infrastructure.resilience import (
    CircuitBreaker,
    MockCircuitBreaker,
    MockRateLimiter,
    MockRetryPolicy,
    MockTimeout,
    OperationMode,
    ResilienceFactory,
    ResilientLLMProviderDecorator,
    ResilientTicketSystemDecorator,
    TokenBucketRateLimiter,
)


class MockTicketSystem:
    """Mock ticket system for testing."""

    async def get_work_item(self, item_id):
        return {"id": item_id, "title": "Test Item"}


class MockLLMProvider:
    """Mock LLM provider for testing."""

    async def execute(self, prompt, context=None, stream_callback=None):
        return {"content": "Test response"}


class TestResilienceFactory:
    """Tests for ResilienceFactory."""

    def test_production_mode_creates_production_components(self):
        """Test that production mode creates real resilience components."""
        factory = ResilienceFactory(mode=OperationMode.PRODUCTION)

        ticket_system = MockTicketSystem()
        resilient = factory.create_resilient_ticket_system(ticket_system)

        assert isinstance(resilient, ResilientTicketSystemDecorator)
        # Check that it has production components
        assert isinstance(resilient._rate_limiter, TokenBucketRateLimiter)
        assert isinstance(resilient._circuit_breaker, CircuitBreaker)

    def test_simulation_mode_creates_mock_components(self):
        """Test that simulation mode creates mock components."""
        factory = ResilienceFactory(mode=OperationMode.SIMULATION)

        ticket_system = MockTicketSystem()
        resilient = factory.create_resilient_ticket_system(ticket_system)

        assert isinstance(resilient, ResilientTicketSystemDecorator)
        # Check that it has mock components
        assert isinstance(resilient._rate_limiter, MockRateLimiter)
        assert isinstance(resilient._circuit_breaker, MockCircuitBreaker)
        assert isinstance(resilient._retry_policy, MockRetryPolicy)
        assert isinstance(resilient._timeout, MockTimeout)

    def test_integration_test_mode_creates_hybrid_components(self):
        """Test that integration test mode creates appropriate components."""
        factory = ResilienceFactory(mode=OperationMode.INTEGRATION_TEST)

        ticket_system = MockTicketSystem()
        resilient = factory.create_resilient_ticket_system(ticket_system)

        assert isinstance(resilient, ResilientTicketSystemDecorator)
        # Check that it has a mix: mock rate limiter but real circuit breaker
        assert isinstance(resilient._rate_limiter, MockRateLimiter)
        assert isinstance(resilient._circuit_breaker, CircuitBreaker)

    def test_custom_configuration(self):
        """Test that custom configuration is applied."""
        factory = ResilienceFactory(
            mode=OperationMode.PRODUCTION,
            config={
                "max_requests": 100,
                "window_seconds": 30,
                "max_retries": 5
            }
        )

        ticket_system = MockTicketSystem()
        resilient = factory.create_resilient_ticket_system(ticket_system)

        # Verify custom config was applied
        assert resilient._rate_limiter.max_requests == 100
        assert resilient._rate_limiter.window_seconds == 30
        assert resilient._retry_policy.max_retries == 5

    def test_llm_provider_has_token_based_limiting(self):
        """Test that LLM provider uses token-based rate limiting."""
        factory = ResilienceFactory(mode=OperationMode.PRODUCTION)

        llm_provider = MockLLMProvider()
        resilient = factory.create_resilient_llm_provider(llm_provider)

        assert isinstance(resilient, ResilientLLMProviderDecorator)
        # LLM should have token-based limiting
        assert resilient._rate_limiter.max_tokens is not None

    def test_llm_provider_has_longer_timeout(self):
        """Test that LLM provider has longer default timeout."""
        factory = ResilienceFactory(mode=OperationMode.PRODUCTION)

        llm_provider = MockLLMProvider()
        resilient = factory.create_resilient_llm_provider(llm_provider)

        # LLM timeout should be longer (300s vs 30s for ticket system)
        assert resilient._default_timeout == 300.0

    def test_service_specific_config_override(self):
        """Test that service-specific config overrides factory config."""
        factory = ResilienceFactory(
            mode=OperationMode.PRODUCTION,
            config={"max_requests": 100}
        )

        ticket_system = MockTicketSystem()
        resilient = factory.create_resilient_ticket_system(
            ticket_system,
            service_config={"max_requests": 200}  # Override
        )

        # Service-specific config should win
        assert resilient._rate_limiter.max_requests == 200

    @pytest.mark.asyncio
    async def test_resilient_adapter_wraps_correctly(self):
        """Test that resilient adapter properly wraps underlying adapter."""
        factory = ResilienceFactory(mode=OperationMode.SIMULATION)

        ticket_system = MockTicketSystem()
        resilient = factory.create_resilient_ticket_system(ticket_system)

        # Test that it actually calls through to wrapped adapter
        result = await resilient.get_work_item("123")

        assert result["id"] == "123"
        assert result["title"] == "Test Item"

        # Verify resilience was applied (mock should have recorded it)
        assert len(resilient._rate_limiter.acquire_calls) > 0
