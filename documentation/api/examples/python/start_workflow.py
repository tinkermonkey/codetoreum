"""
Example: Start workflow execution for a work item

This example demonstrates how to create a work item and start
a workflow execution.
"""
import requests
from typing import Dict, Any, Optional


# Configuration
BASE_URL = "http://localhost:8000"
API_TOKEN = "your_token_here"  # Get from server startup logs


def create_work_item(
    title: str,
    description: str,
    project_id: str,
    labels: list[str] = None,
    priority: str = "medium",
    external_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a new work item.

    Args:
        title: Work item title
        description: Detailed description
        project_id: Project identifier
        labels: List of labels
        priority: Priority (low, medium, high, critical)
        external_id: External ticket ID (e.g., GitHub issue number)

    Returns:
        Created work item data
    """
    url = f"{BASE_URL}/api/v2/work-items/"

    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "title": title,
        "description": description,
        "project_id": project_id,
        "labels": labels or [],
        "priority": priority,
        "status": "pending"
    }

    if external_id:
        payload["external_id"] = external_id

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()

    work_item = response.json()
    print(f"✓ Created work item: {work_item['id']}")
    return work_item


def start_workflow(
    work_item_id: str,
    workflow_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Start workflow execution for a work item.

    Args:
        work_item_id: Work item ID
        workflow_id: Optional specific workflow ID (auto-selected if not provided)

    Returns:
        Workflow run information including run ID

    Raises:
        requests.HTTPError: If request fails
    """
    url = f"{BASE_URL}/api/v2/orchestrator/start"

    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "work_item_id": work_item_id
    }

    if workflow_id:
        payload["workflow_id"] = workflow_id

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()

    workflow_run = response.json()
    print(f"✓ Started workflow run: {workflow_run['workflow_run_id']}")
    return workflow_run


def check_entry_conditions(
    work_item_id: str,
    stage_name: str
) -> Dict[str, Any]:
    """
    Check if entry conditions are met for a stage.

    Args:
        work_item_id: Work item ID
        stage_name: Stage name to check

    Returns:
        Dictionary with conditions_met boolean and details
    """
    url = f"{BASE_URL}/api/v2/orchestrator/check-entry-conditions"

    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "work_item_id": work_item_id,
        "stage_name": stage_name
    }

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()

    return response.json()


def pause_workflow(workflow_run_id: str) -> Dict[str, Any]:
    """
    Pause a running workflow.

    Args:
        workflow_run_id: Workflow run ID

    Returns:
        Updated workflow run status
    """
    url = f"{BASE_URL}/api/v2/orchestrator/{workflow_run_id}/pause"

    headers = {
        "Authorization": f"Bearer {API_TOKEN}"
    }

    response = requests.post(url, headers=headers)
    response.raise_for_status()

    print(f"✓ Paused workflow run: {workflow_run_id}")
    return response.json()


def resume_workflow(workflow_run_id: str) -> Dict[str, Any]:
    """
    Resume a paused workflow.

    Args:
        workflow_run_id: Workflow run ID

    Returns:
        Updated workflow run status
    """
    url = f"{BASE_URL}/api/v2/orchestrator/{workflow_run_id}/resume"

    headers = {
        "Authorization": f"Bearer {API_TOKEN}"
    }

    response = requests.post(url, headers=headers)
    response.raise_for_status()

    print(f"✓ Resumed workflow run: {workflow_run_id}")
    return response.json()


def cancel_workflow(workflow_run_id: str) -> Dict[str, Any]:
    """
    Cancel a workflow execution.

    Args:
        workflow_run_id: Workflow run ID

    Returns:
        Updated workflow run status
    """
    url = f"{BASE_URL}/api/v2/orchestrator/{workflow_run_id}/cancel"

    headers = {
        "Authorization": f"Bearer {API_TOKEN}"
    }

    response = requests.post(url, headers=headers)
    response.raise_for_status()

    print(f"✓ Cancelled workflow run: {workflow_run_id}")
    return response.json()


def main():
    """Example usage."""
    # Example 1: Create work item and start workflow
    print("=== Creating Work Item ===\n")

    work_item = create_work_item(
        title="Add user profile API endpoint",
        description="""
        Implement a new API endpoint for user profile management:
        - GET /api/v2/users/{user_id}/profile
        - PUT /api/v2/users/{user_id}/profile
        - Include authentication and validation
        - Write tests
        """,
        project_id="my-api-project",
        labels=["feature", "api", "backend"],
        priority="high",
        external_id="GH-456"
    )

    print(f"\nWork Item ID: {work_item['id']}")
    print(f"Title: {work_item['title']}")
    print(f"Status: {work_item['status']}")

    # Check entry conditions (optional)
    print("\n=== Checking Entry Conditions ===\n")
    conditions = check_entry_conditions(work_item['id'], "development")
    print(f"Conditions met: {conditions['conditions_met']}")

    # Start workflow
    print("\n=== Starting Workflow ===\n")
    workflow_run = start_workflow(work_item['id'])

    print(f"\nWorkflow Run ID: {workflow_run['workflow_run_id']}")
    print(f"Workflow: {workflow_run.get('workflow_name', 'auto-selected')}")
    print(f"Current Stage: {workflow_run['current_stage']}")
    print(f"Status: {workflow_run['status']}")

    # Example 2: Workflow control (pause/resume)
    print("\n=== Workflow Control Example ===\n")

    # Simulate pausing workflow
    print("Pausing workflow...")
    # pause_workflow(workflow_run['workflow_run_id'])

    # Wait for some condition...
    # time.sleep(30)

    # Resume workflow
    print("Resuming workflow...")
    # resume_workflow(workflow_run['workflow_run_id'])

    # Example 3: Cancel workflow (if needed)
    # cancel_workflow(workflow_run['workflow_run_id'])

    print("\n✓ Workflow started successfully")
    print(f"  Monitor at: {BASE_URL}/api/docs")
    print(f"  Or use WebSocket: ws://localhost:8000/api/v2/events/stream?token={API_TOKEN[:20]}...")


if __name__ == "__main__":
    main()
