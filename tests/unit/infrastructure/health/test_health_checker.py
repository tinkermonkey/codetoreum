"""Unit tests for health checker implementations."""

import asyncio
from datetime import datetime

import pytest

from codetoreum.infrastructure.health import (
    CircuitBreakerHealthCheck,
    CompositeHealthCheck,
    DatabaseHealthCheck,
    DependencyHealth,
    EventStoreHealthCheck,
    HealthChecker,
    HealthCheckResult,
    HealthStatus,
    RateLimiterHealthCheck,
    RedisHealthCheck,
)
from codetoreum.infrastructure.resilience import (
    CircuitBreaker,
    CircuitState,
    TokenBucketRateLimiter,
)


class TestHealthChecker:
    """Test main health checker."""

    @pytest.mark.asyncio
    async def test_liveness_always_healthy(self):
        """Test that liveness check is always healthy."""
        checker = HealthChecker(app_name="test_app", version="1.0.0")

        result = await checker.check_liveness()

        assert result.status == HealthStatus.HEALTHY
        assert "test_app" in result.message
        assert result.metadata["app_name"] == "test_app"
        assert result.metadata["version"] == "1.0.0"
        assert "uptime_seconds" in result.metadata

    @pytest.mark.asyncio
    async def test_readiness_healthy_with_no_dependencies(self):
        """Test readiness is healthy when no dependencies."""
        checker = HealthChecker()

        result = await checker.check_readiness()

        assert result.status == HealthStatus.HEALTHY
        assert len(result.dependencies) == 0

    @pytest.mark.asyncio
    async def test_readiness_healthy_with_healthy_dependencies(self):
        """Test readiness is healthy when all dependencies are healthy."""
        # Create mock dependency
        class MockHealthyCheck:
            async def check_readiness(self):
                return HealthCheckResult(
                    status=HealthStatus.HEALTHY,
                    message="Mock is healthy"
                )

        checker = HealthChecker()
        checker.register_dependency("mock", MockHealthyCheck())

        result = await checker.check_readiness()

        assert result.status == HealthStatus.HEALTHY
        assert len(result.dependencies) == 1
        assert result.dependencies[0].status == HealthStatus.HEALTHY
        assert result.metadata["total_dependencies"] == 1
        assert result.metadata["healthy_dependencies"] == 1

    @pytest.mark.asyncio
    async def test_readiness_unhealthy_with_unhealthy_dependency(self):
        """Test readiness is unhealthy when a dependency is unhealthy."""
        # Create mock unhealthy dependency
        class MockUnhealthyCheck:
            async def check_readiness(self):
                return HealthCheckResult(
                    status=HealthStatus.UNHEALTHY,
                    message="Mock is unhealthy"
                )

        checker = HealthChecker()
        checker.register_dependency("mock", MockUnhealthyCheck())

        result = await checker.check_readiness()

        assert result.status == HealthStatus.UNHEALTHY
        assert "not ready" in result.message.lower()
        assert len(result.dependencies) == 1
        assert result.dependencies[0].status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_readiness_degraded_with_degraded_dependency(self):
        """Test readiness is degraded when a dependency is degraded."""
        class MockDegradedCheck:
            async def check_readiness(self):
                return HealthCheckResult(
                    status=HealthStatus.DEGRADED,
                    message="Mock is degraded"
                )

        checker = HealthChecker()
        checker.register_dependency("mock", MockDegradedCheck())

        result = await checker.check_readiness()

        assert result.status == HealthStatus.DEGRADED
        assert len(result.dependencies) == 1

    @pytest.mark.asyncio
    async def test_check_dependency_not_found(self):
        """Test checking a non-existent dependency."""
        checker = HealthChecker()

        result = await checker.check_dependency("nonexistent")

        assert result.status == HealthStatus.UNKNOWN
        assert "not found" in result.message

    @pytest.mark.asyncio
    async def test_check_dependency_timeout(self):
        """Test that slow dependency checks timeout."""
        class SlowCheck:
            async def check_readiness(self):
                await asyncio.sleep(10)  # Will timeout at 5 seconds
                return HealthCheckResult(status=HealthStatus.HEALTHY)

        checker = HealthChecker()
        checker.register_dependency("slow", SlowCheck())

        result = await checker.check_dependency("slow")

        assert result.status == HealthStatus.UNHEALTHY
        assert "timed out" in result.message.lower()

    @pytest.mark.asyncio
    async def test_register_and_unregister_dependency(self):
        """Test registering and unregistering dependencies."""
        class MockCheck:
            async def check_readiness(self):
                return HealthCheckResult(status=HealthStatus.HEALTHY)

        checker = HealthChecker()

        # Register
        checker.register_dependency("test", MockCheck())
        assert "test" in checker.dependencies

        # Unregister
        checker.unregister_dependency("test")
        assert "test" not in checker.dependencies


class TestCircuitBreakerHealthCheck:
    """Test circuit breaker health check."""

    @pytest.mark.asyncio
    async def test_circuit_closed_is_healthy(self):
        """Test that closed circuit is healthy."""
        breaker = CircuitBreaker()
        health_check = CircuitBreakerHealthCheck(breaker, name="test_circuit")

        result = await health_check.check_readiness()

        assert result.status == HealthStatus.HEALTHY
        assert "closed" in result.message.lower()
        assert result.metadata["state"] == CircuitState.CLOSED.value

    @pytest.mark.asyncio
    async def test_circuit_open_is_unhealthy(self):
        """Test that open circuit is unhealthy."""
        breaker = CircuitBreaker()
        breaker.force_open()
        health_check = CircuitBreakerHealthCheck(breaker)

        result = await health_check.check_readiness()

        assert result.status == HealthStatus.UNHEALTHY
        assert "open" in result.message.lower()

    @pytest.mark.asyncio
    async def test_circuit_half_open_is_degraded(self):
        """Test that half-open circuit is degraded."""
        breaker = CircuitBreaker()
        breaker.force_open()
        # Manually set to half-open
        breaker._state = CircuitState.HALF_OPEN
        health_check = CircuitBreakerHealthCheck(breaker)

        result = await health_check.check_readiness()

        assert result.status == HealthStatus.DEGRADED
        assert "half-open" in result.message.lower()

    @pytest.mark.asyncio
    async def test_liveness_always_healthy(self):
        """Test liveness is always healthy for circuit breaker."""
        breaker = CircuitBreaker()
        breaker.force_open()
        health_check = CircuitBreakerHealthCheck(breaker)

        result = await health_check.check_liveness()

        assert result.status == HealthStatus.HEALTHY


class TestRateLimiterHealthCheck:
    """Test rate limiter health check."""

    @pytest.mark.asyncio
    async def test_low_utilization_is_healthy(self):
        """Test that low utilization is healthy."""
        limiter = TokenBucketRateLimiter(max_requests=100, window_seconds=60)
        health_check = RateLimiterHealthCheck(limiter, warn_threshold=0.8)

        result = await health_check.check_readiness()

        assert result.status == HealthStatus.HEALTHY
        assert result.metadata["utilization"] < 0.8

    @pytest.mark.asyncio
    async def test_high_utilization_is_degraded(self):
        """Test that high utilization is degraded."""
        limiter = TokenBucketRateLimiter(max_requests=10, window_seconds=60)

        # Fill to 80% capacity
        for _ in range(8):
            await limiter.acquire("test")

        health_check = RateLimiterHealthCheck(limiter, warn_threshold=0.8)

        result = await health_check.check_readiness()

        assert result.status == HealthStatus.DEGRADED
        assert "high load" in result.message.lower()

    @pytest.mark.asyncio
    async def test_full_utilization_is_unhealthy(self):
        """Test that full utilization is unhealthy."""
        limiter = TokenBucketRateLimiter(max_requests=5, window_seconds=60)

        # Fill to capacity
        for _ in range(5):
            await limiter.acquire("test")

        health_check = RateLimiterHealthCheck(limiter)

        result = await health_check.check_readiness()

        assert result.status == HealthStatus.UNHEALTHY
        assert "capacity" in result.message.lower()


class TestDatabaseHealthCheck:
    """Test database health check."""

    @pytest.mark.asyncio
    async def test_database_healthy(self):
        """Test database health check when healthy."""
        async def check_func():
            return True

        health_check = DatabaseHealthCheck(check_func, db_name="test_db")

        result = await health_check.check_readiness()

        assert result.status == HealthStatus.HEALTHY
        assert "reachable" in result.message.lower()
        assert "response_time_ms" in result.metadata

    @pytest.mark.asyncio
    async def test_database_unhealthy(self):
        """Test database health check when unhealthy."""
        async def check_func():
            return False

        health_check = DatabaseHealthCheck(check_func, db_name="test_db")

        result = await health_check.check_readiness()

        assert result.status == HealthStatus.UNHEALTHY
        assert "not healthy" in result.message.lower()

    @pytest.mark.asyncio
    async def test_database_error(self):
        """Test database health check when error occurs."""
        async def check_func():
            raise Exception("Connection failed")

        health_check = DatabaseHealthCheck(check_func, db_name="test_db")

        result = await health_check.check_readiness()

        assert result.status == HealthStatus.UNHEALTHY
        assert "failed" in result.message.lower()

    @pytest.mark.asyncio
    async def test_liveness_always_healthy(self):
        """Test liveness is always healthy for database check."""
        async def check_func():
            return False

        health_check = DatabaseHealthCheck(check_func)

        result = await health_check.check_liveness()

        assert result.status == HealthStatus.HEALTHY


class TestRedisHealthCheck:
    """Test Redis health check."""

    @pytest.mark.asyncio
    async def test_redis_healthy(self):
        """Test Redis health check when healthy."""
        async def check_func():
            return True

        health_check = RedisHealthCheck(check_func, redis_name="test_redis")

        result = await health_check.check_readiness()

        assert result.status == HealthStatus.HEALTHY
        assert "reachable" in result.message.lower()

    @pytest.mark.asyncio
    async def test_redis_unhealthy(self):
        """Test Redis health check when unhealthy."""
        async def check_func():
            return False

        health_check = RedisHealthCheck(check_func)

        result = await health_check.check_readiness()

        assert result.status == HealthStatus.UNHEALTHY


class TestEventStoreHealthCheck:
    """Test event store health check."""

    @pytest.mark.asyncio
    async def test_event_store_healthy(self):
        """Test event store health check when healthy."""
        async def check_func():
            return True

        health_check = EventStoreHealthCheck(check_func, store_name="test_store")

        result = await health_check.check_readiness()

        assert result.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_event_store_unhealthy(self):
        """Test event store health check when unhealthy."""
        async def check_func():
            return False

        health_check = EventStoreHealthCheck(check_func)

        result = await health_check.check_readiness()

        assert result.status == HealthStatus.UNHEALTHY


class TestCompositeHealthCheck:
    """Test composite health check."""

    @pytest.mark.asyncio
    async def test_all_healthy(self):
        """Test composite check when all sub-checks are healthy."""
        class MockHealthyCheck:
            async def check_readiness(self):
                return HealthCheckResult(status=HealthStatus.HEALTHY)

            async def check_liveness(self):
                return HealthCheckResult(status=HealthStatus.HEALTHY)

        composite = CompositeHealthCheck([
            MockHealthyCheck(),
            MockHealthyCheck(),
        ])

        result = await composite.check_readiness()

        assert result.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_one_unhealthy(self):
        """Test composite check when one sub-check is unhealthy."""
        class MockHealthyCheck:
            async def check_readiness(self):
                return HealthCheckResult(status=HealthStatus.HEALTHY)

            async def check_liveness(self):
                return HealthCheckResult(status=HealthStatus.HEALTHY)

        class MockUnhealthyCheck:
            async def check_readiness(self):
                return HealthCheckResult(status=HealthStatus.UNHEALTHY)

            async def check_liveness(self):
                return HealthCheckResult(status=HealthStatus.UNHEALTHY)

        composite = CompositeHealthCheck([
            MockHealthyCheck(),
            MockUnhealthyCheck(),
        ])

        result = await composite.check_readiness()

        assert result.status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_one_degraded(self):
        """Test composite check when one sub-check is degraded."""
        class MockHealthyCheck:
            async def check_readiness(self):
                return HealthCheckResult(status=HealthStatus.HEALTHY)

            async def check_liveness(self):
                return HealthCheckResult(status=HealthStatus.HEALTHY)

        class MockDegradedCheck:
            async def check_readiness(self):
                return HealthCheckResult(status=HealthStatus.DEGRADED)

            async def check_liveness(self):
                return HealthCheckResult(status=HealthStatus.HEALTHY)

        composite = CompositeHealthCheck([
            MockHealthyCheck(),
            MockDegradedCheck(),
        ])

        result = await composite.check_readiness()

        assert result.status == HealthStatus.DEGRADED
