#!/usr/bin/env python3
"""View board status in the simulation server.

Usage:
    python sim_board_status.py --board-id board-1 --project-id <id>
    python sim_board_status.py --board-id board-1 --project-id <id> --items
    python sim_board_status.py --board-id board-1 --history
"""

import argparse
import json
import sys

import httpx


def main():
    parser = argparse.ArgumentParser(description="View simulation board status")
    parser.add_argument("--server", default="http://localhost:8000", help="Simulation server URL")
    parser.add_argument("--board-id", required=True, help="Board ID")
    parser.add_argument("--project-id", default=None, help="Project ID (required for columns/items)")
    parser.add_argument("--items", action="store_true", help="Show all items and positions")
    parser.add_argument("--history", action="store_true", help="Show movement history")
    args = parser.parse_args()

    base = f"{args.server}/api/v2/simulation/ticketing/board/{args.board_id}"

    try:
        if args.history:
            url = f"{base}/history"
            resp = httpx.get(url, timeout=10.0)
        elif args.items:
            if not args.project_id:
                print("--project-id is required for --items", file=sys.stderr)
                sys.exit(1)
            url = f"{base}/items"
            resp = httpx.get(url, params={"project_id": args.project_id}, timeout=10.0)
        else:
            if not args.project_id:
                print("--project-id is required for columns view", file=sys.stderr)
                sys.exit(1)
            url = f"{base}/columns"
            resp = httpx.get(url, params={"project_id": args.project_id}, timeout=10.0)

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
