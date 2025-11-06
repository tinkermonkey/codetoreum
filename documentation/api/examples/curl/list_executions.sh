#!/bin/bash
#
# Example: List and monitor agent executions
#
# This example demonstrates how to list executions, filter by status,
# and retrieve execution logs using cURL.

# Configuration
BASE_URL="http://localhost:8000"
API_TOKEN="your_token_here"  # Get from server startup logs

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Listing Running Executions ===${NC}\n"

# List all running executions
RUNNING=$(curl -s -X GET "${BASE_URL}/api/v2/executions/?status=running" \
  -H "Authorization: Bearer ${API_TOKEN}")

TOTAL=$(echo "$RUNNING" | jq -r '.total')
echo "Found ${TOTAL} running execution(s)"
echo ""

if [ "$TOTAL" -gt 0 ]; then
  echo "$RUNNING" | jq -r '.items[] | "  ID: \(.id)\n  Agent: \(.agent_id)\n  Work Item: \(.work_item_id)\n  Status: \(.status)\n  Started: \(.started_at)\n"'
fi

# List recent completed executions
echo -e "${BLUE}=== Recent Completed Executions ===${NC}\n"

COMPLETED=$(curl -s -X GET "${BASE_URL}/api/v2/executions/?status=completed&limit=5&sort_by=completed_at&sort_order=desc" \
  -H "Authorization: Bearer ${API_TOKEN}")

TOTAL=$(echo "$COMPLETED" | jq -r '.total')
echo "Found ${TOTAL} completed execution(s)"
echo ""

if [ "$TOTAL" -gt 0 ]; then
  echo "$COMPLETED" | jq -r '.items[] | "  ID: \(.id)\n  Status: \(.status)\n  Duration: \(.duration_seconds // "N/A")s\n"'
fi

# Get details of first running execution (if any)
FIRST_RUNNING=$(echo "$RUNNING" | jq -r '.items[0].id // empty')

if [ -n "$FIRST_RUNNING" ]; then
  echo -e "${BLUE}=== Execution Details: ${FIRST_RUNNING} ===${NC}\n"

  curl -s -X GET "${BASE_URL}/api/v2/executions/${FIRST_RUNNING}" \
    -H "Authorization: Bearer ${API_TOKEN}" | jq '.'

  echo ""
  echo -e "${BLUE}=== Execution Logs (Last 20 lines) ===${NC}\n"

  LOGS=$(curl -s -X GET "${BASE_URL}/api/v2/executions/${FIRST_RUNNING}/logs?tail=20" \
    -H "Authorization: Bearer ${API_TOKEN}")

  echo "$LOGS" | jq -r '.logs[]'
  echo ""
fi

# List failed executions for debugging
echo -e "${BLUE}=== Recent Failed Executions ===${NC}\n"

FAILED=$(curl -s -X GET "${BASE_URL}/api/v2/executions/?status=failed&limit=5&sort_by=completed_at&sort_order=desc" \
  -H "Authorization: Bearer ${API_TOKEN}")

TOTAL=$(echo "$FAILED" | jq -r '.total')
echo "Found ${TOTAL} failed execution(s)"
echo ""

if [ "$TOTAL" -gt 0 ]; then
  # Get each failed execution and show error details
  echo "$FAILED" | jq -r '.items[] | .id' | while read -r EXEC_ID; do
    DETAILS=$(curl -s -X GET "${BASE_URL}/api/v2/executions/${EXEC_ID}" \
      -H "Authorization: Bearer ${API_TOKEN}")

    echo -e "  ${RED}ID: ${EXEC_ID}${NC}"
    echo "  Agent: $(echo "$DETAILS" | jq -r '.agent_id')"
    echo "  Failed at: $(echo "$DETAILS" | jq -r '.completed_at // "N/A"')"

    ERROR=$(echo "$DETAILS" | jq -r '.error_message // empty')
    if [ -n "$ERROR" ]; then
      echo "  Error: ${ERROR}"
    fi

    # Get last 5 lines of logs
    LOGS=$(curl -s -X GET "${BASE_URL}/api/v2/executions/${EXEC_ID}/logs?tail=5" \
      -H "Authorization: Bearer ${API_TOKEN}")

    LOG_COUNT=$(echo "$LOGS" | jq -r '.logs | length')
    if [ "$LOG_COUNT" -gt 0 ]; then
      echo "  Last logs:"
      echo "$LOGS" | jq -r '.logs[] | "    \(.)"'
    fi

    echo ""
  done
fi

# Execution control examples
echo -e "${BLUE}=== Execution Control Examples ===${NC}\n"

echo "To terminate an execution:"
echo "  curl -X POST \"${BASE_URL}/api/v2/executions/\${EXECUTION_ID}/terminate\" \\"
echo "    -H \"Authorization: Bearer \${API_TOKEN}\""
echo ""

echo "To pause an execution:"
echo "  curl -X POST \"${BASE_URL}/api/v2/executions/\${EXECUTION_ID}/pause\" \\"
echo "    -H \"Authorization: Bearer \${API_TOKEN}\""
echo ""

echo "To resume a paused execution:"
echo "  curl -X POST \"${BASE_URL}/api/v2/executions/\${EXECUTION_ID}/resume\" \\"
echo "    -H \"Authorization: Bearer \${API_TOKEN}\""
echo ""

# Filter examples
echo -e "${BLUE}=== Filter Examples ===${NC}\n"

echo "Filter by work item:"
echo "  curl \"${BASE_URL}/api/v2/executions/?work_item_id=wi_abc123\" \\"
echo "    -H \"Authorization: Bearer \${API_TOKEN}\""
echo ""

echo "Filter by agent:"
echo "  curl \"${BASE_URL}/api/v2/executions/?agent_id=agent_xyz789\" \\"
echo "    -H \"Authorization: Bearer \${API_TOKEN}\""
echo ""

echo "Filter by workflow run:"
echo "  curl \"${BASE_URL}/api/v2/executions/?workflow_run_id=run_def456\" \\"
echo "    -H \"Authorization: Bearer \${API_TOKEN}\""
echo ""

echo "Pagination:"
echo "  curl \"${BASE_URL}/api/v2/executions/?offset=0&limit=50&sort_by=started_at&sort_order=desc\" \\"
echo "    -H \"Authorization: Bearer \${API_TOKEN}\""
echo ""

echo -e "${GREEN}✓ Done${NC}"
