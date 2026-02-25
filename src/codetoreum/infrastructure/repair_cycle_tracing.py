"""OpenTelemetry tracing for repair cycle observability.

Provides distributed tracing capabilities for repair cycle execution:
- Span creation for cycle lifecycle events
- Automatic span context propagation
- Performance metrics via spans
- Error tracking with span events
- Optional Jaeger/Zipkin exporter integration
"""

import logging
from contextlib import contextmanager
from typing import Any

try:
    from opentelemetry import trace
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

logger = logging.getLogger(__name__)

__all__ = [
    "OTEL_AVAILABLE",
    "NullRepairCycleTracer",
    "RepairCycleTracer",
    "get_repair_cycle_tracer",
]

# Track if instrumentation has been applied to prevent double instrumentation
_INSTRUMENTATION_APPLIED = False


class RepairCycleTracer:
    """OpenTelemetry tracer for repair cycle stages."""

    def __init__(
        self,
        service_name: str = "codetoreum",
        jaeger_host: str | None = None,
        jaeger_port: int = 6831,
        enabled: bool = True,
    ):
        """
        Initialize repair cycle tracer.

        Args:
            service_name: Service name for tracing
            jaeger_host: Optional Jaeger exporter host
            jaeger_port: Jaeger exporter port
            enabled: Whether tracing is enabled
        """
        self.enabled = enabled and OTEL_AVAILABLE
        self.service_name = service_name
        self.tracer_provider = None
        self.tracer = None

        if self.enabled:
            self._init_tracer(service_name, jaeger_host, jaeger_port)
        elif not OTEL_AVAILABLE:
            logger.warning("OpenTelemetry not available - tracing disabled")
        else:
            logger.info("Repair cycle tracing disabled")

    def _init_tracer(
        self,
        service_name: str,
        jaeger_host: str | None = None,
        jaeger_port: int = 6831,
    ) -> None:
        """Initialize OpenTelemetry tracer."""
        global _INSTRUMENTATION_APPLIED
        try:
            if jaeger_host:
                jaeger_exporter = JaegerExporter(
                    agent_host_name=jaeger_host,
                    agent_port=jaeger_port,
                )
                self.tracer_provider = TracerProvider()
                self.tracer_provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
            else:
                self.tracer_provider = TracerProvider()

            trace.set_tracer_provider(self.tracer_provider)
            self.tracer = trace.get_tracer(__name__)

            # Instrument HTTP libraries (guard against double instrumentation)
            if not _INSTRUMENTATION_APPLIED:
                try:
                    RequestsInstrumentor().instrument()
                    URLLib3Instrumentor().instrument()
                    _INSTRUMENTATION_APPLIED = True
                except Exception as e:
                    logger.debug(f"HTTP instrumentation skipped (may already be applied): {e}")

            logger.info(f"OpenTelemetry tracer initialized for {service_name}")

        except Exception as e:
            logger.warning(f"Failed to initialize OpenTelemetry tracer: {e}")
            self.enabled = False

    @contextmanager
    def trace_cycle(
        self,
        cycle_name: str,
        attributes: dict[str, Any] | None = None,
    ):
        """
        Context manager to trace repair cycle execution.

        Args:
            cycle_name: Name of the repair cycle
            attributes: Optional span attributes
        """
        if not self.enabled or not self.tracer:
            yield
            return

        span_name = f"repair_cycle.{cycle_name}"
        span_attributes = {
            "service.name": self.service_name,
            "repair_cycle.name": cycle_name,
            "span.kind": "INTERNAL",
        }

        if attributes:
            span_attributes.update(attributes)

        with self.tracer.start_as_current_span(span_name) as span:
            for key, value in span_attributes.items():
                if value is not None:
                    span.set_attribute(key, self._serialize_attribute(value))

            try:
                yield span
                span.set_attribute("repair_cycle.status", "success")
            except Exception as e:
                span.set_attribute("repair_cycle.status", "failed")
                span.record_exception(e)
                raise

    @contextmanager
    def trace_stage(
        self,
        stage_name: str,
        attributes: dict[str, Any] | None = None,
    ):
        """
        Context manager to trace repair cycle stage.

        Args:
            stage_name: Name of the stage
            attributes: Optional span attributes
        """
        if not self.enabled or not self.tracer:
            yield
            return

        span_name = f"repair_cycle_stage.{stage_name}"
        span_attributes = {
            "repair_cycle.stage.name": stage_name,
        }

        if attributes:
            span_attributes.update(attributes)

        with self.tracer.start_as_current_span(span_name) as span:
            for key, value in span_attributes.items():
                if value is not None:
                    span.set_attribute(key, self._serialize_attribute(value))

            try:
                yield span
                span.set_attribute("stage.status", "success")
            except Exception as e:
                span.set_attribute("stage.status", "failed")
                span.record_exception(e)
                raise

    @contextmanager
    def trace_test_execution(
        self,
        test_type: str,
        iteration: int = 0,
        attributes: dict[str, Any] | None = None,
    ):
        """
        Context manager to trace test execution.

        Args:
            test_type: Type of test (unit, integration, e2e)
            iteration: Iteration number
            attributes: Optional span attributes
        """
        if not self.enabled or not self.tracer:
            yield
            return

        span_name = f"test_execution.{test_type}"
        span_attributes = {
            "test.type": test_type,
            "test.iteration": iteration,
        }

        if attributes:
            span_attributes.update(attributes)

        with self.tracer.start_as_current_span(span_name) as span:
            for key, value in span_attributes.items():
                if value is not None:
                    span.set_attribute(key, self._serialize_attribute(value))

            try:
                yield span
                span.set_attribute("test.status", "passed")
            except Exception as e:
                span.set_attribute("test.status", "failed")
                span.record_exception(e)
                raise

    @contextmanager
    def trace_file_fix(
        self,
        file_path: str,
        attributes: dict[str, Any] | None = None,
    ):
        """
        Context manager to trace file fix operation.

        Args:
            file_path: Path to file being fixed
            attributes: Optional span attributes
        """
        if not self.enabled or not self.tracer:
            yield
            return

        span_name = f"file_fix.{file_path.rsplit('/', maxsplit=1)[-1]}"
        span_attributes = {
            "file.path": file_path,
            "file.extension": file_path.rsplit(".", maxsplit=1)[-1] if "." in file_path else "unknown",
        }

        if attributes:
            span_attributes.update(attributes)

        with self.tracer.start_as_current_span(span_name) as span:
            for key, value in span_attributes.items():
                if value is not None:
                    span.set_attribute(key, self._serialize_attribute(value))

            try:
                yield span
                span.set_attribute("file_fix.status", "success")
            except Exception as e:
                span.set_attribute("file_fix.status", "failed")
                span.record_exception(e)
                raise

    @contextmanager
    def trace_agent_call(
        self,
        agent_name: str,
        attributes: dict[str, Any] | None = None,
    ):
        """
        Context manager to trace LLM agent call.

        Args:
            agent_name: Name of the agent being called
            attributes: Optional span attributes
        """
        if not self.enabled or not self.tracer:
            yield
            return

        span_name = f"agent_call.{agent_name}"
        span_attributes = {
            "agent.name": agent_name,
        }

        if attributes:
            span_attributes.update(attributes)

        with self.tracer.start_as_current_span(span_name) as span:
            for key, value in span_attributes.items():
                if value is not None:
                    span.set_attribute(key, self._serialize_attribute(value))

            try:
                yield span
                span.set_attribute("agent_call.status", "success")
            except Exception as e:
                span.set_attribute("agent_call.status", "failed")
                span.record_exception(e)
                raise

    @staticmethod
    def _serialize_attribute(value: Any) -> Any:
        """Serialize attribute value for OpenTelemetry."""
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (list, tuple)):
            return [RepairCycleTracer._serialize_attribute(v) for v in value]
        return str(value)

    def add_span_event(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """
        Add event to current span.

        Args:
            name: Event name
            attributes: Optional event attributes
        """
        if not self.enabled or not self.tracer:
            return

        try:
            current_span = trace.get_current_span()
            if current_span:
                event_attributes = {}
                if attributes:
                    for key, value in attributes.items():
                        event_attributes[key] = self._serialize_attribute(value)
                current_span.add_event(name, event_attributes)
        except Exception as e:
            logger.debug(f"Error adding span event: {e}")

    def shutdown(self) -> None:
        """Shutdown tracer provider."""
        if self.tracer_provider:
            try:
                self.tracer_provider.force_flush()
            except Exception as e:
                logger.warning(f"Error flushing tracer: {e}")


class NullRepairCycleTracer:
    """Null object pattern tracer for when tracing is disabled."""

    @contextmanager
    def trace_cycle(self, cycle_name: str, attributes: dict[str, Any] | None = None):
        """No-op trace_cycle."""
        yield

    @contextmanager
    def trace_stage(self, stage_name: str, attributes: dict[str, Any] | None = None):
        """No-op trace_stage."""
        yield

    @contextmanager
    def trace_test_execution(
        self,
        test_type: str,
        iteration: int = 0,
        attributes: dict[str, Any] | None = None,
    ):
        """No-op trace_test_execution."""
        yield

    @contextmanager
    def trace_file_fix(self, file_path: str, attributes: dict[str, Any] | None = None):
        """No-op trace_file_fix."""
        yield

    @contextmanager
    def trace_agent_call(self, agent_name: str, attributes: dict[str, Any] | None = None):
        """No-op trace_agent_call."""
        yield

    def add_span_event(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """No-op add_span_event."""

    def shutdown(self) -> None:
        """No-op shutdown."""


def get_repair_cycle_tracer(
    service_name: str = "codetoreum",
    jaeger_host: str | None = None,
    jaeger_port: int = 6831,
    enabled: bool = True,
) -> RepairCycleTracer:
    """
    Factory function to get repair cycle tracer.

    Returns NullRepairCycleTracer if tracing is disabled or OpenTelemetry unavailable.
    """
    try:
        tracer = RepairCycleTracer(service_name, jaeger_host, jaeger_port, enabled)
        if tracer.enabled:
            return tracer
        return NullRepairCycleTracer()
    except Exception as e:
        logger.warning(f"Failed to create repair cycle tracer: {e}")
        return NullRepairCycleTracer()
