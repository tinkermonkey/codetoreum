#!/usr/bin/env python3
"""Add a comment to a ticket in the simulation server.

Usage:
    python sim_add_comment.py --work-item-id <id> --body "This looks good"
    python sim_add_comment.py --work-item-id <id> --body "Needs changes" --author "reviewer-bot"
"""

import argparse
import json
import sys

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Add a comment to a simulation ticket")
    parser.add_argument("--server", default="http://localhost:8000", help="Simulation server URL")
    parser.add_argument("--work-item-id", required=True, help="Work item ID to comment on")
    parser.add_argument("--body", required=True, help="Comment body")
    parser.add_argument("--author", default="simulation-user", help="Comment author")
    args = parser.parse_args()

    payload = {"body": args.body, "author": args.author}
    url = f"{args.server}/api/v2/simulation/ticketing/issues/{args.work_item_id}/comment"

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
