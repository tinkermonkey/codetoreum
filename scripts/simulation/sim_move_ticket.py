#!/usr/bin/env python3
"""Move a ticket between board columns in the simulation server.

Usage:
    python sim_move_ticket.py --work-item-id <id> --target-column "In Progress"
"""

import argparse
import json
import sys

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Move a simulation ticket between columns")
    parser.add_argument("--server", default="http://localhost:8000", help="Simulation server URL")
    parser.add_argument("--work-item-id", required=True, help="Work item ID to move")
    parser.add_argument("--target-column", required=True, help="Target column name")
    args = parser.parse_args()

    payload = {"target_column": args.target_column}
    url = f"{args.server}/api/v2/simulation/ticketing/issues/{args.work_item_id}/move"

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
