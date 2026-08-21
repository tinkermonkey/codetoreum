"""
Simulation E2E Test Client

High-level test client wrapping FastAPI TestClient for REST and WebSocket operations.
Provides convenience methods for common E2E test scenarios with time manipulation
and observability verification.

Usage:
    client = SimulationE2EClient(app, bootstrap)
    work_item = client.create_work_item(
        project_id="proj-1",
        title="Test item",
        description="Test description"
    )
    client.trigger_workflow(work_item["id"], "workflow-1")
    await client.wait_for_work_item_status(work_item["id"], "COMPLETED")
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationApplicationBootstrap,
)
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock

logger = logging.getLogger(__name__)


class WebSocketEventCollector:
    """Collects and filters events from WebSocket connection."""

    def __init__(self, websocket):
        """
        Initialize event collector.

        Args:
            websocket: WebSocket connection from TestClient
        """
        self.websocket = websocket
        self.received_events: list[dict[str, Any]] = []
        self._event_types: set[str] = set()

    def collect_event(self, timeout: float = 1.0) -> dict[str, Any] | None:
        """
        Receive and collect a single event from WebSocket.

        Args:
            timeout: Timeout in seconds

        Returns:
            Event data or None if timeout

        Raises:
            ConnectionError: If WebSocket is disconnected
        """
        try:
            # TestClient WebSocket is synchronous
            data = cast("dict[str, Any]", self.websocket.receive_json())
            self.received_events.append(data)

            # Track event type if it's an event message
            if isinstance(data, dict) and "type" in data:
                self._event_types.add(data.get("type", ""))

            return data
        except ConnectionError as e:
            logger.error(f"WebSocket connection lost: {e}")
            raise ConnectionError(f"WebSocket disconnected while collecting events: {e}")
        except Exception as e:
            logger.debug(f"Failed to receive event: {e}")
            return None

    def collect_events(self, count: int, timeout: float = 5.0) -> list[dict[str, Any]]:
        """
        Collect multiple events from WebSocket.

        Args:
            count: Number of events to collect
            timeout: Total timeout in seconds

        Returns:
            List of collected events
        """
        events = []
        for _ in range(count):
            event = self.collect_event(timeout=timeout / count)
            if event:
                events.append(event)
            else:
                break
        return events

    def wait_for_event(
        self,
        event_type: str,
        timeout: float = 10.0,
        filter_fn: Callable | None = None,
    ) -> dict[str, Any]:
        """
        Wait for specific event type with optional filtering.

        Args:
            event_type: Event type to wait for
            timeout: Timeout in seconds
            filter_fn: Optional function to filter events

        Returns:
            Matching event

        Raises:
            TimeoutError: If event not received within timeout
            ConnectionError: If WebSocket disconnects
        """
        # First check already received events
        for existing_event in self.received_events:
            if self._matches_event(existing_event, event_type, filter_fn):
                return existing_event

        # Receive new events until match or timeout
        import time

        start = time.time()
        while (time.time() - start) < timeout:
            event: dict[str, Any] | None = self.collect_event(timeout=0.1)
            if event and self._matches_event(event, event_type, filter_fn):
                return event

        # Timeout - provide clear error message
        raise TimeoutError(
            f"Event '{event_type}' not received within {timeout}s. "
            f"Received {len(self.received_events)} events. "
            f"Event types: {sorted(self._event_types)}"
        )

    def assert_event_received(
        self,
        event_type: str,
        filter_fn: Callable | None = None,
    ) -> dict[str, Any]:
        """
        Assert that an event was received.

        Args:
            event_type: Event type to check for
            filter_fn: Optional function to filter events

        Returns:
            Matching event

        Raises:
            AssertionError: If event not found
        """
        for event in self.received_events:
            if self._matches_event(event, event_type, filter_fn):
                return event

        raise AssertionError(
            f"Event '{event_type}' not found in {len(self.received_events)} "
            f"received events. Event types: {sorted(self._event_types)}"
        )

    def _matches_event(
        self,
        event: dict[str, Any],
        event_type: str,
        filter_fn: Callable | None = None,
    ) -> bool:
        """Check if event matches criteria."""
        if not isinstance(event, dict):
            return False

        # Check event type
        if event.get("type") != event_type:
            return False

        # Apply custom filter
        if filter_fn and not filter_fn(event):
            return False

        return True

    def clear(self):
        """Clear all collected events."""
        self.received_events.clear()
        self._event_types.clear()


class SimulationE2EClient:
    """
    High-level E2E test client for simulation testing.

    Provides:
    - REST API methods (create_work_item, trigger_workflow, etc.)
    - WebSocket methods (connect_websocket, wait_for_event, etc.)
    - Time manipulation integration
    - Observability verification helpers
    """

    def __init__(
        self,
        app: FastAPI,
        bootstrap: SimulationApplicationBootstrap,
    ):
        """
        Initialize E2E test client.

        Args:
            app: FastAPI application
            bootstrap: Simulation bootstrap with clock and adapters
        """
        self.app = app
        self.bootstrap = bootstrap
        self.client = TestClient(app)
        # Get clock from engine (engine encapsulates clock)
        if not bootstrap.engine:
            raise RuntimeError("SimulationEngine not initialized in bootstrap")
        self.clock: SimulationClock = bootstrap.engine.get_clock_for_testing()

    def close(self):
        """Close the test client and release socket resources."""
        if self.client:
            self.client.close()

    # ========================================================================
    # REST API Methods
    # ========================================================================

    def create_work_item(
        self,
        project_id: str,
        title: str,
        description: str,
        labels: list[str] | None = None,
        priority: str = "MEDIUM",
        external_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new work item.

        Args:
            project_id: Project ID
            title: Work item title
            description: Work item description
            labels: Optional labels
            priority: Priority level
            external_id: Optional external system ID

        Returns:
            Created work item data
        """
        response = self.client.post(
            "/api/v2/work-items",
            json={
                "project_id": project_id,
                "title": title,
                "description": description,
                "labels": labels or [],
                "priority": priority,
                "external_id": external_id,
            },
        )
        response.raise_for_status()
        return cast("dict[str, Any]", response.json())

    def get_work_item(self, work_item_id: str) -> dict[str, Any]:
        """
        Get work item by ID.

        Args:
            work_item_id: Work item ID

        Returns:
            Work item data
        """
        response = self.client.get(f"/api/v2/work-items/{work_item_id}")
        response.raise_for_status()
        return cast("dict[str, Any]", response.json())

    def get_work_item_status(self, work_item_id: str) -> str:
        """
        Get work item status.

        Args:
            work_item_id: Work item ID

        Returns:
            Status string
        """
        work_item = self.get_work_item(work_item_id)
        return cast("str", work_item["status"])

    def list_work_items(
        self,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        List work items with filters.

        Args:
            project_id: Optional project filter
            status: Optional status filter
            limit: Maximum items to return

        Returns:
            List of work items
        """
        params: dict[str, Any] = {"limit": limit}
        if project_id:
            params["project_id"] = project_id
        if status:
            params["status"] = status

        response = self.client.get("/api/v2/work-items", params=params)
        response.raise_for_status()
        data = cast("dict[str, Any]", response.json())
        return cast("list[dict[str, Any]]", data.get("items", []))

    def trigger_workflow(
        self,
        work_item_id: str,
        workflow_id: str,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Trigger workflow for a work item.

        Args:
            work_item_id: Work item ID
            workflow_id: Workflow ID to trigger
            force: Force trigger even if conditions not met

        Returns:
            Trigger result
        """
        response = self.client.post(
            "/api/v2/orchestrator/trigger",
            json={
                "work_item_id": work_item_id,
                "workflow_id": workflow_id,
                "force": force,
            },
        )
        response.raise_for_status()
        return cast("dict[str, Any]", response.json())

    def get_executions(
        self,
        work_item_id: str | None = None,
        workflow_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get agent executions with filters.

        Args:
            work_item_id: Optional work item filter
            workflow_id: Optional workflow filter
            status: Optional status filter

        Returns:
            List of executions
        """
        params: dict[str, Any] = {}
        if work_item_id:
            params["work_item_id"] = work_item_id
        if workflow_id:
            params["workflow_id"] = workflow_id
        if status:
            params["status"] = status

        response = self.client.get("/api/v2/executions", params=params)
        response.raise_for_status()
        data = cast("dict[str, Any]", response.json())
        return cast("list[dict[str, Any]]", data.get("items", []))

    def get_metrics(
        self,
        metric_name: str | None = None,
        labels: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query metrics.

        Args:
            metric_name: Optional metric name filter
            labels: Optional label filters

        Returns:
            List of metric data points
        """
        params: dict[str, Any] = {}
        if metric_name:
            params["metric_name"] = metric_name
        if labels:
            for key, value in labels.items():
                params[f"label_{key}"] = value

        response = self.client.get("/api/v2/metrics", params=params)
        response.raise_for_status()
        return cast("list[dict[str, Any]]", response.json())

    def get_events(
        self,
        aggregate_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Query events from event store.

        Args:
            aggregate_id: Optional aggregate ID filter
            event_type: Optional event type filter
            limit: Maximum events to return

        Returns:
            List of events
        """
        params: dict[str, Any] = {"limit": limit}
        if aggregate_id:
            params["aggregate_id"] = aggregate_id
        if event_type:
            params["event_type"] = event_type

        response = self.client.get("/api/v2/events", params=params)
        response.raise_for_status()
        data = cast("dict[str, Any]", response.json())
        return cast("list[dict[str, Any]]", data.get("events", []))

    # ========================================================================
    # WebSocket Methods
    # ========================================================================

    def connect_websocket(
        self,
        subscription_type: str = "all_events",
        work_item_id: str | None = None,
        workflow_id: str | None = None,
    ) -> WebSocketEventCollector:
        """
        Connect to WebSocket and subscribe to events.

        Args:
            subscription_type: Type of subscription
            work_item_id: Optional work item filter
            workflow_id: Optional workflow filter

        Returns:
            WebSocketEventCollector for receiving events
        """
        # Build WebSocket path with query params
        path = "/api/v2/events/stream"

        # Connect WebSocket
        websocket = self.client.websocket_connect(path)

        # Send subscription message
        subscription = {
            "type": "subscribe",
            "subscription_type": subscription_type,
        }
        if work_item_id:
            subscription["work_item_id"] = work_item_id
        if workflow_id:
            subscription["workflow_id"] = workflow_id

        websocket.send_json(subscription)

        # Return collector
        return WebSocketEventCollector(websocket)

    # ========================================================================
    # Time Manipulation Methods
    # ========================================================================

    def advance_time(self, delta: timedelta):
        """
        Advance simulation clock.

        Args:
            delta: Time delta to advance
        """
        self.clock.advance(delta)

    def advance_minutes(self, minutes: int):
        """
        Advance simulation clock by minutes.

        Args:
            minutes: Number of minutes to advance
        """
        self.clock.advance(timedelta(minutes=minutes))

    # ========================================================================
    # Helper Methods for Test Assertions
    # ========================================================================

    async def wait_for_work_item_status(
        self,
        work_item_id: str,
        expected_status: str,
        timeout: float = 30.0,
        poll_interval: float = 0.5,
    ) -> dict[str, Any]:
        """
        Wait for work item to reach expected status.

        Args:
            work_item_id: Work item ID
            expected_status: Expected status
            timeout: Timeout in seconds
            poll_interval: Polling interval in seconds

        Returns:
            Final work item data

        Raises:
            TimeoutError: If status not reached within timeout
        """
        import time

        start = time.time()
        last_status = None
        while (time.time() - start) < timeout:
            try:
                work_item = self.get_work_item(work_item_id)
                last_status = work_item["status"]
                if last_status == expected_status:
                    return work_item
            except Exception as e:
                logger.warning(f"Failed to fetch work item status: {e}")
            await asyncio.sleep(poll_interval)

        # Timeout - get final state for error message
        try:
            work_item = self.get_work_item(work_item_id)
            last_status = work_item["status"]
        except Exception:
            pass

        raise TimeoutError(
            f"Work item {work_item_id} did not reach status '{expected_status}' "
            f"within {timeout}s. Last known status: '{last_status}'"
        )

    async def wait_for_execution_status(
        self,
        execution_id: str,
        expected_status: str,
        timeout: float = 30.0,
        poll_interval: float = 0.5,
    ) -> dict[str, Any]:
        """
        Wait for execution to reach expected status.

        Args:
            execution_id: Execution ID
            expected_status: Expected status
            timeout: Timeout in seconds
            poll_interval: Polling interval in seconds

        Returns:
            Final execution data

        Raises:
            TimeoutError: If status not reached within timeout
        """
        max_iterations = int(timeout / poll_interval) + 1

        async def poll_execution_status() -> dict[str, Any] | None:
            for _ in range(max_iterations):
                executions = self.get_executions()
                for execution in executions:
                    if execution["id"] == execution_id and execution["status"] == expected_status:
                        return execution
                await asyncio.sleep(poll_interval)
            return None

        result = await poll_execution_status()
        if result is not None:
            return result
        raise TimeoutError(f"Execution {execution_id} did not reach status {expected_status} within {timeout}s")

    def assert_metrics_recorded(
        self,
        metric_name: str,
        labels: dict[str, str] | None = None,
        min_count: int = 1,
    ):
        """
        Assert that metrics were recorded.

        Args:
            metric_name: Metric name to check
            labels: Optional label filters
            min_count: Minimum number of data points expected

        Raises:
            AssertionError: If metrics not found
        """
        metrics = self.get_metrics(metric_name=metric_name, labels=labels)
        assert (
            len(metrics) >= min_count
        ), f"Expected at least {min_count} data points for metric '{metric_name}', but found {len(metrics)}"

    def assert_events_recorded(
        self,
        event_type: str,
        aggregate_id: str | None = None,
        min_count: int = 1,
    ):
        """
        Assert that events were recorded.

        Args:
            event_type: Event type to check
            aggregate_id: Optional aggregate ID filter
            min_count: Minimum number of events expected

        Raises:
            AssertionError: If events not found
        """
        events = self.get_events(event_type=event_type, aggregate_id=aggregate_id)
        assert (
            len(events) >= min_count
        ), f"Expected at least {min_count} events of type '{event_type}', but found {len(events)}"
