"""
Example: Real-time event streaming via WebSocket

This example demonstrates how to connect to the WebSocket endpoint
and receive real-time events about workflows, executions, and work items.
"""
import asyncio
import json
from typing import Callable, Optional
import websockets
from datetime import datetime


# Configuration
WS_URL = "ws://localhost:8000/api/v2/events/stream"
API_TOKEN = "your_token_here"  # Get from server startup logs


class CodetoreumEventStream:
    """WebSocket client for Codetoreum event streaming."""

    def __init__(self, token: str, base_url: str = WS_URL):
        """
        Initialize event stream client.

        Args:
            token: Authentication token
            base_url: WebSocket URL (default: ws://localhost:8000/api/v2/events/stream)
        """
        self.token = token
        self.base_url = f"{base_url}?token={token}"
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.handlers = {}

    async def connect(self):
        """Connect to the WebSocket."""
        print(f"Connecting to {self.base_url}...")
        self.websocket = await websockets.connect(self.base_url)
        print("✓ Connected to event stream")

    async def disconnect(self):
        """Disconnect from the WebSocket."""
        if self.websocket:
            await self.websocket.close()
            print("✓ Disconnected from event stream")

    def on(self, event_type: str, handler: Callable):
        """
        Register event handler.

        Args:
            event_type: Event type to handle (e.g., "workflow.started")
            handler: Async function to call when event is received
        """
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)

    def on_all(self, handler: Callable):
        """
        Register handler for all events.

        Args:
            handler: Async function to call for all events
        """
        self.on("*", handler)

    async def listen(self):
        """
        Listen for events and dispatch to handlers.

        This is a blocking call that will run until the connection is closed.
        """
        if not self.websocket:
            raise RuntimeError("Not connected. Call connect() first.")

        try:
            async for message in self.websocket:
                # Parse event
                event = json.loads(message)
                event_type = event.get("type", "unknown")

                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"[{timestamp}] Received: {event_type}")

                # Call specific handlers
                if event_type in self.handlers:
                    for handler in self.handlers[event_type]:
                        await handler(event)

                # Call wildcard handlers
                if "*" in self.handlers:
                    for handler in self.handlers["*"]:
                        await handler(event)

        except websockets.exceptions.ConnectionClosed as e:
            print(f"Connection closed: {e.code} - {e.reason}")
        except websockets.exceptions.WebSocketException as e:
            print(f"WebSocket error: {e}")
            raise
        except json.JSONDecodeError as e:
            print(f"Failed to parse event JSON: {e}")
            raise
        except KeyError as e:
            print(f"Missing expected field in event: {e}")
            raise
        except Exception as e:
            print(f"Unexpected error: {type(e).__name__}: {e}")
            raise


# Example event handlers

async def handle_workflow_started(event):
    """Handle workflow.started events."""
    data = event.get("data", {})
    print(f"  🚀 Workflow started:")
    print(f"     Run ID: {data.get('workflow_run_id')}")
    print(f"     Work Item: {data.get('work_item_id')}")
    print(f"     Workflow: {data.get('workflow_name')}")


async def handle_workflow_completed(event):
    """Handle workflow.completed events."""
    data = event.get("data", {})
    print(f"  ✓ Workflow completed:")
    print(f"     Run ID: {data.get('workflow_run_id')}")
    print(f"     Status: {data.get('status')}")
    print(f"     Duration: {data.get('duration_seconds')}s")


async def handle_execution_started(event):
    """Handle execution.started events."""
    data = event.get("data", {})
    print(f"  ▶ Execution started:")
    print(f"     Execution ID: {data.get('execution_id')}")
    print(f"     Agent: {data.get('agent_id')}")
    print(f"     Stage: {data.get('stage_name')}")


async def handle_execution_progress(event):
    """Handle execution.progress events."""
    data = event.get("data", {})
    progress = data.get("progress", {})
    pct = progress.get("percentage", 0)
    step = progress.get("current_step", "")
    print(f"  ⏳ Execution progress: {pct}% - {step}")


async def handle_execution_completed(event):
    """Handle execution.completed events."""
    data = event.get("data", {})
    print(f"  ✓ Execution completed:")
    print(f"     Execution ID: {data.get('execution_id')}")
    print(f"     Status: {data.get('status')}")


async def handle_execution_failed(event):
    """Handle execution.failed events."""
    data = event.get("data", {})
    print(f"  ✗ Execution failed:")
    print(f"     Execution ID: {data.get('execution_id')}")
    print(f"     Error: {data.get('error_message')}")


async def handle_work_item_updated(event):
    """Handle work_item.updated events."""
    data = event.get("data", {})
    print(f"  📝 Work item updated:")
    print(f"     Work Item ID: {data.get('work_item_id')}")
    print(f"     Status: {data.get('status')}")
    print(f"     Stage: {data.get('workflow_stage')}")


async def log_all_events(event):
    """Log all events (for debugging)."""
    # Pretty print the entire event
    print(f"  Raw event: {json.dumps(event, indent=2)}")


async def main():
    """Example usage: Monitor all workflow and execution events."""
    client = CodetoreumEventStream(token=API_TOKEN)

    # Register event handlers
    client.on("workflow.started", handle_workflow_started)
    client.on("workflow.completed", handle_workflow_completed)
    client.on("execution.started", handle_execution_started)
    client.on("execution.progress", handle_execution_progress)
    client.on("execution.completed", handle_execution_completed)
    client.on("execution.failed", handle_execution_failed)
    client.on("work_item.updated", handle_work_item_updated)

    # Optionally log all events for debugging
    # client.on_all(log_all_events)

    # Connect and listen
    await client.connect()

    try:
        print("\n📡 Listening for events... (Press Ctrl+C to stop)\n")
        await client.listen()
    except KeyboardInterrupt:
        print("\n\nStopping...")
    finally:
        await client.disconnect()


async def example_filtered_monitoring():
    """Example: Monitor only specific execution."""
    client = CodetoreumEventStream(token=API_TOKEN)

    # Track specific execution
    target_execution_id = "exec_abc123"

    async def handle_target_execution(event):
        data = event.get("data", {})
        if data.get("execution_id") == target_execution_id:
            print(f"Target execution event: {event.get('type')}")
            print(f"  Data: {json.dumps(data, indent=2)}")

    # Register handler for all execution events
    client.on("execution.started", handle_target_execution)
    client.on("execution.progress", handle_target_execution)
    client.on("execution.completed", handle_target_execution)
    client.on("execution.failed", handle_target_execution)

    await client.connect()
    try:
        await client.listen()
    finally:
        await client.disconnect()


if __name__ == "__main__":
    # Run main example
    asyncio.run(main())

    # Or run filtered monitoring example
    # asyncio.run(example_filtered_monitoring())
