#!/usr/bin/env python3
"""Create a ticket in the simulation server.

Usage:
    python sim_create_ticket.py --title "My Issue" --project-id <id>
    python sim_create_ticket.py --title "My Issue" --project-id <id> --board-id board-1 --column Backlog
"""

import argparse
import json
import sys

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a simulation ticket")
    parser.add_argument("--server", default="http://localhost:8000", help="Simulation server URL")
    parser.add_argument("--title", required=True, help="Issue title")
    parser.add_argument("--description", default="", help="Issue description")
    parser.add_argument("--project-id", required=True, help="Project ID")
    parser.add_argument("--labels", nargs="*", default=[], help="Labels")
    parser.add_argument("--priority", default="medium", help="Priority: low, medium, high, critical")
    parser.add_argument("--board-id", default=None, help="Board ID to place issue on")
    parser.add_argument("--column", default=None, help="Column to place issue in (requires --board-id)")
    args = parser.parse_args()

    payload = {
        "title": args.title,
        "description": args.description,
        "project_id": args.project_id,
        "labels": args.labels,
        "priority": args.priority,
    }
    if args.board_id:
        payload["board_id"] = args.board_id
    if args.column:
        payload["column"] = args.column

    url = f"{args.server}/api/v2/simulation/ticketing/issues"
    try:
        resp = httpx.post(url, json=payload, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        print(json.dumps(data, indent=2))
    except httpx.HTTPStatusError as e:
        print(f"Error {e.response.status_code}: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except httpx.ConnectError:
        print(f"Could not connect to {args.server}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
