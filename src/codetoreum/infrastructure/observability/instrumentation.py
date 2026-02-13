"""
Core Instrumentation Utilities for Codetoreum

Provides decorators and utilities for manual instrumentation of functions and methods.
These can be applied to domain layer, application services, and adapters.

ARCHITECTURE NOTE - Cross-Cutting Concern:
Instrumentation decorators are imported directly from this module rather than from
the ITracer port interface because Python decorators are applied at class definition
time, before dependency injection can provide a tracer instance. This is a pragmatic
exception to the port-based architecture and aligns with CLAUDE.md's principle that
"resilience patterns MUST be centralized in infrastructure layer." The decorator
pattern is part of that infrastructure concern and cannot be port-based.

When this module is imported, it uses the global tracer provider. This enables:
- Application services to instrument methods without ITracer injection
- Domain layer to add instrumentation without external dependencies
- Adapters to instrument operations with consistent tracing

The trade-off (direct import from infrastructure) is acceptable because:
1. Instrumentation is infrastructure concern, not domain logic
2. The infrastructure is completely mocked during simulation/testing
3. Time manipulation in SimulationClock automatically works with instrumented functions
4. OpenTelemetry support is optional (OPENTELEMETRY_AVAILABLE flag)
"""

import functools
import logging
from typing import Any, Callable, Dict, Optional

# Try to import OpenTelemetry - it's optional
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode

    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False
    Status = None  # type: ignore
    StatusCode = None  # type: ignore


def _get_tracer():
    """Get tracer lazily to support test provider switching."""
    if not OPENTELEMETRY_AVAILABLE:
        return None
    return trace.get_tracer(__name__)

logger = logging.getLogger(__name__)


def instrument_function(
    name: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
    capture_args: bool = False,
    capture_result: bool = False,
    business_context_fields: Optional[list[str]] = None,
) -> Callable:
    """
    Decorator to instrument synchronous functions with OpenTelemetry spans.

    Creates a span for each function invocation with optional argument and result capture.

    Args:
        name: Span name (defaults to function name)
        attributes: Additional attributes to add to the span
        capture_args: Whether to capture function arguments as span attributes
        capture_result: Whether to capture function result as span attribute
        business_context_fields: List of parameter names that have a '.id' attribute
            to extract as span attributes. E.g., ['work_item', 'agent'] will extract
            work_item.id and agent.id as span attributes.

    Returns:
        Decorated function

    Example:
        @instrument_function(name="create_work_item", capture_args=True)
        def create_work_item(self, title: str, description: str) -> WorkItem:
            ...

        @instrument_function(
            name="agent.schedule",
            business_context_fields=['work_item', 'agent']
        )
        def schedule(self, work_item: WorkItem, agent: Agent):
            ...
    """
    # If OpenTelemetry is not available, return a no-op decorator
    if not OPENTELEMETRY_AVAILABLE:
        def decorator(func: Callable) -> Callable:
            return func
        return decorator

    def decorator(func: Callable) -> Callable:
        span_name = name or f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tracer = _get_tracer()
            if not tracer:
                return func(*args, **kwargs)
            with tracer.start_as_current_span(span_name) as span:
                # Add custom attributes
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)

                # Extract business context from parameters
                if business_context_fields:
                    _extract_business_context(span, func, args, kwargs, business_context_fields)

                # Capture arguments if requested
                if capture_args:
                    _capture_args(span, func, args, kwargs)

                try:
                    result = func(*args, **kwargs)

                    # Capture result if requested
                    if capture_result and result is not None:
                        span.set_attribute("result", str(result))

                    span.set_status(Status(StatusCode.OK))
                    return result

                except Exception as e:
                    # Record exception in span
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

        return wrapper

    return decorator


def instrument_async_function(
    name: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
    capture_args: bool = False,
    capture_result: bool = False,
    business_context_fields: Optional[list[str]] = None,
) -> Callable:
    """
    Decorator to instrument asynchronous functions with OpenTelemetry spans.

    Creates a span for each async function invocation with optional argument and result capture.

    Args:
        name: Span name (defaults to function name)
        attributes: Additional attributes to add to the span
        capture_args: Whether to capture function arguments as span attributes
        capture_result: Whether to capture function result as span attribute
        business_context_fields: List of parameter names that have a '.id' attribute
            to extract as span attributes. E.g., ['work_item', 'agent'] will extract
            work_item.id and agent.id as span attributes.

    Returns:
        Decorated async function

    Example:
        @instrument_async_function(name="execute_agent", capture_args=True)
        async def execute_agent(self, agent_id: str) -> ExecutionResult:
            ...

        @instrument_async_function(
            name="agent.schedule",
            business_context_fields=['work_item', 'agent']
        )
        async def schedule(self, work_item: WorkItem, agent: Agent):
            ...
    """
    # If OpenTelemetry is not available, return a no-op decorator
    if not OPENTELEMETRY_AVAILABLE:
        def decorator(func: Callable) -> Callable:
            return func
        return decorator

    def decorator(func: Callable) -> Callable:
        span_name = name or f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = _get_tracer()
            if not tracer:
                return await func(*args, **kwargs)
            with tracer.start_as_current_span(span_name) as span:
                # Add custom attributes
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)

                # Extract business context from parameters
                if business_context_fields:
                    _extract_business_context(span, func, args, kwargs, business_context_fields)

                # Capture arguments if requested
                if capture_args:
                    _capture_args(span, func, args, kwargs)

                try:
                    result = await func(*args, **kwargs)

                    # Capture result if requested
                    if capture_result and result is not None:
                        span.set_attribute("result", str(result))

                    span.set_status(Status(StatusCode.OK))
                    return result

                except Exception as e:
                    # Record exception in span
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

        return wrapper

    return decorator


def instrument_class(attributes: Optional[Dict[str, Any]] = None) -> Callable:
    """
    Class decorator to automatically instrument all public methods.

    Applies instrumentation to all public methods (not starting with underscore).

    Args:
        attributes: Additional attributes to add to all method spans

    Returns:
        Decorated class

    Example:
        @instrument_class(attributes={"layer": "domain"})
        class WorkItem:
            def update_status(self, status: str):
                ...
    """
    # If OpenTelemetry is not available, return a no-op decorator
    if not OPENTELEMETRY_AVAILABLE:
        def decorator(cls):
            return cls
        return decorator

    def decorator(cls):
        for attr_name in dir(cls):
            # Skip private methods and special methods
            if attr_name.startswith("_"):
                continue

            attr = getattr(cls, attr_name)

            # Instrument callable methods
            if callable(attr):
                import asyncio

                if asyncio.iscoroutinefunction(attr):
                    decorated = instrument_async_function(attributes=attributes)(attr)
                else:
                    decorated = instrument_function(attributes=attributes)(attr)

                setattr(cls, attr_name, decorated)

        return cls

    return decorator


def add_span_attributes(**attributes: Any) -> None:
    """
    Add custom attributes to the current active span.

    Useful for adding dynamic attributes during function execution.

    Args:
        **attributes: Key-value pairs to add as span attributes

    Example:
        def process_work_item(work_item_id: str):
            add_span_attributes(
                work_item_id=work_item_id,
                work_item_type="issue",
                priority="high"
            )
    """
    # If OpenTelemetry is not available, this is a no-op
    if not OPENTELEMETRY_AVAILABLE:
        return

    span = trace.get_current_span()
    if span.is_recording():
        for key, value in attributes.items():
            span.set_attribute(key, value)


def add_span_event(name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
    """
    Add an event to the current active span.

    Events represent discrete points in time during span execution.

    Args:
        name: Event name
        attributes: Optional event attributes

    Example:
        def execute_workflow():
            add_span_event("workflow_started")
            # ... do work ...
            add_span_event("workflow_completed", {"stages": 5})
    """
    # If OpenTelemetry is not available, this is a no-op
    if not OPENTELEMETRY_AVAILABLE:
        return

    span = trace.get_current_span()
    if span.is_recording():
        span.add_event(name, attributes=attributes or {})


def _extract_business_context(
    span, func: Callable, args: tuple, kwargs: dict, business_context_fields: list[str]
) -> None:
    """
    Internal helper to extract business context from function parameters.

    Extracts the .id attribute from specified parameters and adds them as span attributes.

    Args:
        span: Current span
        func: Function being instrumented
        args: Positional arguments
        kwargs: Keyword arguments
        business_context_fields: List of parameter names to extract .id from
    """
    try:
        import inspect

        # Get function signature
        sig = inspect.signature(func)
        bound_args = sig.bind_partial(*args, **kwargs)
        bound_args.apply_defaults()

        # Extract business context from specified fields
        for field_name in business_context_fields:
            if field_name in bound_args.arguments:
                obj = bound_args.arguments[field_name]
                if obj is not None and hasattr(obj, "id"):
                    try:
                        span.set_attribute(f"{field_name}.id", str(obj.id))
                    except Exception as e:
                        logger.debug(
                            f"Failed to extract {field_name}.id for {func.__name__}: {e}"
                        )

    except Exception as e:
        # Don't fail instrumentation if context extraction fails
        logger.debug(f"Failed to extract business context for {func.__name__}: {e}")


def _capture_args(span, func: Callable, args: tuple, kwargs: dict) -> None:
    """
    Internal helper to capture function arguments as span attributes.

    Args:
        span: Current span
        func: Function being instrumented
        args: Positional arguments
        kwargs: Keyword arguments
    """
    try:
        import inspect

        # Get function signature
        sig = inspect.signature(func)
        bound_args = sig.bind_partial(*args, **kwargs)
        bound_args.apply_defaults()

        # Add each argument as a span attribute
        for param_name, param_value in bound_args.arguments.items():
            # Skip 'self' and 'cls' parameters
            if param_name in ("self", "cls"):
                continue

            # Convert to string for safety (avoid complex object serialization)
            if param_value is not None:
                # Truncate long values
                value_str = str(param_value)
                if len(value_str) > 200:
                    value_str = value_str[:200] + "..."

                span.set_attribute(f"arg.{param_name}", value_str)

    except Exception as e:
        # Don't fail instrumentation if arg capture fails
        logger.debug(f"Failed to capture arguments for {func.__name__}: {e}")
