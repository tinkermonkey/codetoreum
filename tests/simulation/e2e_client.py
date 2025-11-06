"""
Simulation E2E Test Client

High-level test client wrapping FastAPI TestClient for REST and WebSocket operations.
Provides convenience methods for common E2E test scenarios with time manipulation
and observability verification.

Usage:
    client = SimulationE2EClient(app, bootstrap)
    work_item = await client.create_work_item(
        project_id="proj-1",
        title="Test item",
        description="Test description"
    )
    await client.trigger_workflow(work_item.id, "workflow-1")
    await client.wait_for_work_item_status(work_item.id, WorkItemStatus.COMPLETED)
"""

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from codetoreum.domain.work_item import WorkItemStatus, WorkItemPriority
from codetoreum.domain.agent_execution import ExecutionStatus
from codetoreum.infrastructure.simulation.bootstrap import SimulationApplicationBootstrap
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
        self.received_events: List[Dict[str, Any]] = []
        self._event_types: Set[str] = set()

    def collect_event(self, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
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
            data = self.websocket.receive_json()
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

    def collect_events(self, count: int, timeout: float = 5.0) -> List[Dict[str, Any]]:
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
        filter_fn: Optional[callable] = None,
    ) -> Dict[str, Any]:
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
        for event in self.received_events:
            if self._matches_event(event, event_type, filter_fn):
                return event

        # Receive new events until match or timeout
        import time
        start = time.time()
        while (time.time() - start) < timeout:
            event = self.collect_event(timeout=0.1)
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
        filter_fn: Optional[callable] = None,
    ) -> Dict[str, Any]:
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
            f"Event '{event_type}' not found in {len(self.received_events)} received events. "
            f"Event types: {sorted(self._event_types)}"
        )

    def _matches_event(
        self,
        event: Dict[str, Any],
        event_type: str,
        filter_fn: Optional[callable] = None,
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
        self.clock: SimulationClock = bootstrap.infrastructure.clock

    # ========================================================================
    # REST API Methods
    # ========================================================================

    def create_work_item(
        self,
        project_id: str,
        title: str,
        description: str,
        labels: Optional[List[str]] = None,
        priority: str = "MEDIUM",
        external_id: Optional[str] = None,
    ) -> Dict[str, Any]:
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
        return response.json()

    def get_work_item(self, work_item_id: str) -> Dict[str, Any]:
        """
        Get work item by ID.

        Args:
            work_item_id: Work item ID

        Returns:
            Work item data
        """
        response = self.client.get(f"/api/v2/work-items/{work_item_id}")
        response.raise_for_status()
        return response.json()

    def get_work_item_status(self, work_item_id: str) -> str:
        """
        Get work item status.

        Args:
            work_item_id: Work item ID

        Returns:
            Status string
        """
        work_item = self.get_work_item(work_item_id)
        return work_item["status"]

    def list_work_items(
        self,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List work items with filters.

        Args:
            project_id: Optional project filter
            status: Optional status filter
            limit: Maximum items to return

        Returns:
            List of work items
        """
        params = {"limit": limit}
        if project_id:
            params["project_id"] = project_id
        if status:
            params["status"] = status

        response = self.client.get("/api/v2/work-items", params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("items", [])

    def trigger_workflow(
        self,
        work_item_id: str,
        workflow_id: str,
        force: bool = False,
    ) -> Dict[str, Any]:
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
            f"/api/v2/orchestrator/trigger",
            json={
                "work_item_id": work_item_id,
                "workflow_id": workflow_id,
                "force": force,
            },
        )
        response.raise_for_status()
        return response.json()

    def get_executions(
        self,
        work_item_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get agent executions with filters.

        Args:
            work_item_id: Optional work item filter
            workflow_id: Optional workflow filter
            status: Optional status filter

        Returns:
            List of executions
        """
        params = {}
        if work_item_id:
            params["work_item_id"] = work_item_id
        if workflow_id:
            params["workflow_id"] = workflow_id
        if status:
            params["status"] = status

        response = self.client.get("/api/v2/executions", params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("items", [])

    def get_metrics(
        self,
        metric_name: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query metrics.

        Args:
            metric_name: Optional metric name filter
            labels: Optional label filters

        Returns:
            List of metric data points
        """
        params = {}
        if metric_name:
            params["metric_name"] = metric_name
        if labels:
            for key, value in labels.items():
                params[f"label_{key}"] = value

        response = self.client.get("/api/v2/metrics", params=params)
        response.raise_for_status()
        return response.json()

    def get_events(
        self,
        aggregate_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Query events from event store.

        Args:
            aggregate_id: Optional aggregate ID filter
            event_type: Optional event type filter
            limit: Maximum events to return

        Returns:
            List of events
        """
        params = {"limit": limit}
        if aggregate_id:
            params["aggregate_id"] = aggregate_id
        if event_type:
            params["event_type"] = event_type

        response = self.client.get("/api/v2/events", params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("events", [])

    # ========================================================================
    # WebSocket Methods
    # ========================================================================

    def connect_websocket(
        self,
        subscription_type: str = "all_events",
        work_item_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
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
    ) -> Dict[str, Any]:
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
    ) -> Dict[str, Any]:
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
        start = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start) < timeout:
            executions = self.get_executions()
            for execution in executions:
                if execution["id"] == execution_id and execution["status"] == expected_status:
                    return execution
            await asyncio.sleep(poll_interval)

        raise TimeoutError(
            f"Execution {execution_id} did not reach status {expected_status} "
            f"within {timeout}s"
        )

    def assert_metrics_recorded(
        self,
        metric_name: str,
        labels: Optional[Dict[str, str]] = None,
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
        assert len(metrics) >= min_count, (
            f"Expected at least {min_count} data points for metric '{metric_name}', "
            f"but found {len(metrics)}"
        )

    def assert_events_recorded(
        self,
        event_type: str,
        aggregate_id: Optional[str] = None,
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
        assert len(events) >= min_count, (
            f"Expected at least {min_count} events of type '{event_type}', "
            f"but found {len(events)}"
        )
