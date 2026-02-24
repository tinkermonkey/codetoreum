#!/usr/bin/env python3
"""Run a full workflow simulation: create ticket -> place in Backlog -> move to Ready.

Usage:
    python sim_run_workflow.py --project-id <id>
    python sim_run_workflow.py --project-id <id> --board-id board-1 --title "My Feature"
"""

import argparse
import json
import sys
import time

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a full workflow simulation")
    parser.add_argument("--server", default="http://localhost:8000", help="Simulation server URL")
    parser.add_argument("--project-id", required=True, help="Project ID")
    parser.add_argument("--board-id", default="board-1", help="Board ID")
    parser.add_argument("--title", default="Simulated Feature Request", help="Issue title")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Poll interval in seconds")
    parser.add_argument("--poll-count", type=int, default=5, help="Number of poll iterations")
    args = parser.parse_args()

    base = f"{args.server}/api/v2/simulation/ticketing"
    client = httpx.Client(timeout=10.0)

    try:
        # Step 1: Create ticket and place in Backlog
        print(f"[1/4] Creating ticket: {args.title}")
        resp = client.post(f"{base}/issues", json={
            "title": args.title,
            "description": f"Automated simulation of: {args.title}",
            "project_id": args.project_id,
            "labels": ["simulation", "automated"],
            "priority": "medium",
            "board_id": args.board_id,
            "column": "Backlog",
        })
        resp.raise_for_status()
        issue = resp.json()
        issue_id = issue["id"]
        print(f"       Created: {issue_id} ({issue['title']})")

        # Step 2: Move to Ready
        print(f"[2/4] Moving to Ready column...")
        resp = client.post(f"{base}/issues/{issue_id}/move", json={
            "target_column": "Ready",
        })
        resp.raise_for_status()
        move = resp.json()
        print(f"       Moved: {move['from_column']} -> {move['to_column']}")

        # Step 3: Add a comment
        print(f"[3/4] Adding comment...")
        resp = client.post(f"{base}/issues/{issue_id}/comment", json={
            "body": "This issue is ready for orchestrator pickup.",
            "author": "simulation-operator",
        })
        resp.raise_for_status()
        comment = resp.json()
        print(f"       Comment added: {comment['id']}")

        # Step 4: Poll board status
        print(f"[4/4] Polling board status ({args.poll_count} iterations)...")
        for i in range(args.poll_count):
            resp = client.get(
                f"{base}/board/{args.board_id}/columns",
                params={"project_id": args.project_id},
            )
            if resp.status_code == 200:
                board = resp.json()
                summary = {col["name"]: col["item_count"] for col in board["columns"]}
                print(f"       [{i+1}/{args.poll_count}] Board: {json.dumps(summary)}")
            else:
                print(f"       [{i+1}/{args.poll_count}] Board query failed: {resp.status_code}")

            if i < args.poll_count - 1:
                time.sleep(args.poll_interval)

        print("\nWorkflow simulation complete.")

    except httpx.HTTPStatusError as e:
        print(f"Error {e.response.status_code}: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except httpx.ConnectError:
        print(f"Could not connect to {args.server}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    main()
