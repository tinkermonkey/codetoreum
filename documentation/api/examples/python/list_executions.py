"""
Example: List and monitor agent executions

This example demonstrates how to list executions, filter by status,
and retrieve execution logs.
"""
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

import requests  # type: ignore[import-untyped]

# Configuration
BASE_URL = "http://localhost:8000"
API_TOKEN = "your_token_here"  # Get from server startup logs


def list_executions(
    status: Optional[str] = None,
    work_item_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    workflow_run_id: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
    sort_by: str = "started_at",
    sort_order: str = "desc"
) -> Dict[str, Any]:
    """
    List agent executions with filtering and pagination.

    Args:
        status: Filter by status (pending, running, completed, failed, cancelled)
        work_item_id: Filter by work item
        agent_id: Filter by agent
        workflow_run_id: Filter by workflow run
        offset: Number of items to skip
        limit: Maximum items to return
        sort_by: Field to sort by
        sort_order: Sort order (asc or desc)

    Returns:
        Dictionary with items, total count, and pagination info

    Raises:
        requests.HTTPError: If request fails
    """
    url = f"{BASE_URL}/api/v2/executions/"

    headers = {
        "Authorization": f"Bearer {API_TOKEN}"
    }

    params = {
        "offset": offset,
        "limit": limit,
        "sort_by": sort_by,
        "sort_order": sort_order
    }

    # Add optional filters
    if status:
        params["status"] = status
    if work_item_id:
        params["work_item_id"] = work_item_id
    if agent_id:
        params["agent_id"] = agent_id
    if workflow_run_id:
        params["workflow_run_id"] = workflow_run_id

    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()

    return cast(Dict[str, Any], response.json())


def get_execution_details(execution_id: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific execution.

    Args:
        execution_id: Execution ID

    Returns:
        Execution details including status, progress, and metadata
    """
    url = f"{BASE_URL}/api/v2/executions/{execution_id}"

    headers = {
        "Authorization": f"Bearer {API_TOKEN}"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    return cast(Dict[str, Any], response.json())


def get_execution_logs(
    execution_id: str,
    tail: Optional[int] = None,
    follow: bool = False
) -> List[str]:
    """
    Get execution logs.

    Args:
        execution_id: Execution ID
        tail: Return only last N lines
        follow: Stream logs in real-time (not implemented in HTTP, use WebSocket)

    Returns:
        List of log lines
    """
    url = f"{BASE_URL}/api/v2/executions/{execution_id}/logs"

    headers = {
        "Authorization": f"Bearer {API_TOKEN}"
    }

    params = {}
    if tail:
        params["tail"] = tail

    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()

    data = cast(Dict[str, Any], response.json())
    return cast(List[str], data.get("logs", []))


def wait_for_execution(
    execution_id: str,
    check_interval: int = 5,
    timeout: int = 3600,
    print_logs: bool = True
) -> Dict[str, Any]:
    """
    Wait for an execution to complete.

    Args:
        execution_id: Execution ID
        check_interval: Seconds between status checks
        timeout: Maximum seconds to wait
        print_logs: Print logs while waiting

    Returns:
        Final execution status

    Raises:
        TimeoutError: If execution doesn't complete within timeout
    """
    start_time = time.time()
    last_log_count = 0

    while True:
        # Check if timeout exceeded
        if time.time() - start_time > timeout:
            raise TimeoutError(f"Execution {execution_id} did not complete within {timeout}s")

        # Get execution status
        execution = get_execution_details(execution_id)
        status = execution["status"]

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Status: {status}", end="")

        if "progress" in execution:
            progress = execution["progress"]
            pct = progress.get("percentage", 0)
            print(f" - {pct}%", end="")

        print()

        # Print new logs if requested
        if print_logs:
            logs = get_execution_logs(execution_id)
            new_logs = logs[last_log_count:]
            for log in new_logs:
                print(f"  {log}")
            last_log_count = len(logs)

        # Check if completed
        if status in ["completed", "failed", "cancelled"]:
            return execution

        # Wait before next check
        time.sleep(check_interval)


def main() -> None:
    """Example usage."""
    try:
        print("=== Listing Running Executions ===\n")

        # List all running executions
        running = list_executions(status="running")
        print(f"Found {running['total']} running execution(s)")

        for execution in running["items"]:
            print(f"\n  ID: {execution['id']}")
            print(f"  Agent: {execution['agent_id']}")
            print(f"  Work Item: {execution['work_item_id']}")
            print(f"  Status: {execution['status']}")
            print(f"  Started: {execution['started_at']}")

        # List recent completed executions
        print("\n\n=== Recent Completed Executions ===\n")
        completed = list_executions(status="completed", limit=5)
        print(f"Found {completed['total']} completed execution(s)")

        for execution in completed["items"]:
            print(f"\n  ID: {execution['id']}")
            print(f"  Status: {execution['status']}")
            print(f"  Duration: {execution.get('duration_seconds', 'N/A')}s")

        # Monitor a specific execution (if any running)
        if running["items"]:
            execution_id = running["items"][0]["id"]
            print(f"\n\n=== Monitoring Execution {execution_id} ===\n")

            try:
                final_status = wait_for_execution(
                    execution_id,
                    check_interval=5,
                    timeout=300,  # 5 minutes
                    print_logs=True
                )
                print(f"\n✓ Execution completed with status: {final_status['status']}")
            except TimeoutError as e:
                print(f"\n⚠ {e}")
            except requests.exceptions.HTTPError as e:
                print(f"\n✗ Failed to monitor execution: HTTP {e.response.status_code}")
            except KeyError as e:
                print(f"\n✗ Unexpected response format: missing field {e}")

        # List failed executions for debugging
        print("\n\n=== Recent Failed Executions ===\n")
        failed = list_executions(status="failed", limit=5)
        print(f"Found {failed['total']} failed execution(s)")

        for execution in failed["items"]:
            print(f"\n  ID: {execution['id']}")
            print(f"  Agent: {execution['agent_id']}")
            print(f"  Failed at: {execution.get('completed_at', 'N/A')}")

            # Get last 10 lines of logs
            try:
                logs = get_execution_logs(execution['id'], tail=10)
                if logs:
                    print("  Last logs:")
                    for log in logs[-5:]:  # Show last 5 lines
                        print(f"    {log}")
            except requests.exceptions.HTTPError:
                print("  (Unable to retrieve logs)")

    except requests.exceptions.HTTPError as e:
        print(f"\n✗ API Error: {e.response.status_code}")
        try:
            error_detail = e.response.json()
            print(f"  Detail: {error_detail.get('detail', 'No details provided')}")
        except (ValueError, requests.exceptions.JSONDecodeError):
            print(f"  Detail: {e.response.text}")
    except requests.exceptions.ConnectionError:
        print(f"\n✗ Connection Error: Unable to connect to {BASE_URL}")
        print("  Ensure the API server is running")
    except requests.exceptions.Timeout:
        print(f"\n✗ Timeout Error: Request took too long")
    except requests.exceptions.RequestException as e:
        print(f"\n✗ Request Error: {str(e)}")
    except KeyError as e:
        print(f"\n✗ Data Error: Missing expected field {e} in API response")
    except Exception as e:
        print(f"\n✗ Unexpected Error: {type(e).__name__}: {str(e)}")


if __name__ == "__main__":
    main()
