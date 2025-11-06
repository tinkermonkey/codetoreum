#!/bin/bash
#
# Example: Start workflow execution for a work item
#
# This example demonstrates how to create a work item and start
# a workflow execution using cURL.

# Configuration
BASE_URL="http://localhost:8000"
API_TOKEN="your_token_here"  # Get from server startup logs

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Creating Work Item ===${NC}\n"

# Create work item
WORK_ITEM=$(curl -s -X POST "${BASE_URL}/api/v2/work-items/" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Add user profile API endpoint",
    "description": "Implement a new API endpoint for user profile management:\n- GET /api/v2/users/{user_id}/profile\n- PUT /api/v2/users/{user_id}/profile\n- Include authentication and validation\n- Write tests",
    "project_id": "my-api-project",
    "labels": ["feature", "api", "backend"],
    "priority": "high",
    "status": "pending",
    "external_id": "GH-456"
  }')

# Check if request was successful
if [ $? -eq 0 ]; then
  WORK_ITEM_ID=$(echo "$WORK_ITEM" | jq -r '.id')

  echo -e "${GREEN}✓ Created work item: ${WORK_ITEM_ID}${NC}"
  echo ""

  # Pretty print work item
  echo "$WORK_ITEM" | jq '.'
  echo ""
else
  echo "Error creating work item"
  echo "$WORK_ITEM"
  exit 1
fi

# Check entry conditions (optional)
echo -e "${BLUE}=== Checking Entry Conditions ===${NC}\n"

STAGE_NAME="development"
ENTRY_CHECK=$(curl -s -X POST "${BASE_URL}/api/v2/orchestrator/check-entry-conditions" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"work_item_id\": \"${WORK_ITEM_ID}\",
    \"stage_name\": \"${STAGE_NAME}\"
  }")

CONDITIONS_MET=$(echo "$ENTRY_CHECK" | jq -r '.conditions_met')
echo "Conditions met for '${STAGE_NAME}' stage: ${CONDITIONS_MET}"
echo ""

if [ "$CONDITIONS_MET" = "false" ]; then
  echo -e "${YELLOW}⚠ Entry conditions not met${NC}"
  echo "$ENTRY_CHECK" | jq '.details'
  echo ""
fi

# Start workflow
echo -e "${BLUE}=== Starting Workflow ===${NC}\n"

WORKFLOW_RUN=$(curl -s -X POST "${BASE_URL}/api/v2/orchestrator/start" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"work_item_id\": \"${WORK_ITEM_ID}\"
  }")

# Check if workflow started successfully
if [ $? -eq 0 ]; then
  WORKFLOW_RUN_ID=$(echo "$WORKFLOW_RUN" | jq -r '.workflow_run_id')
  WORKFLOW_NAME=$(echo "$WORKFLOW_RUN" | jq -r '.workflow_name // "auto-selected"')
  CURRENT_STAGE=$(echo "$WORKFLOW_RUN" | jq -r '.current_stage')
  STATUS=$(echo "$WORKFLOW_RUN" | jq -r '.status')

  echo -e "${GREEN}✓ Started workflow run: ${WORKFLOW_RUN_ID}${NC}"
  echo ""
  echo "Workflow Run ID: ${WORKFLOW_RUN_ID}"
  echo "Workflow: ${WORKFLOW_NAME}"
  echo "Current Stage: ${CURRENT_STAGE}"
  echo "Status: ${STATUS}"
  echo ""

  # Pretty print workflow run
  echo "Full response:"
  echo "$WORKFLOW_RUN" | jq '.'
  echo ""

  # Workflow control examples
  echo -e "${BLUE}=== Workflow Control Examples ===${NC}\n"

  echo "To pause the workflow:"
  echo "  curl -X POST \"${BASE_URL}/api/v2/orchestrator/${WORKFLOW_RUN_ID}/pause\" \\"
  echo "    -H \"Authorization: Bearer ${API_TOKEN}\""
  echo ""

  echo "To resume the workflow:"
  echo "  curl -X POST \"${BASE_URL}/api/v2/orchestrator/${WORKFLOW_RUN_ID}/resume\" \\"
  echo "    -H \"Authorization: Bearer ${API_TOKEN}\""
  echo ""

  echo "To cancel the workflow:"
  echo "  curl -X POST \"${BASE_URL}/api/v2/orchestrator/${WORKFLOW_RUN_ID}/cancel\" \\"
  echo "    -H \"Authorization: Bearer ${API_TOKEN}\""
  echo ""

  # Monitor workflow via WebSocket
  echo -e "${BLUE}=== Monitor Workflow (WebSocket) ===${NC}\n"

  echo "To monitor workflow progress in real-time:"
  echo "  wscat -c \"ws://localhost:8000/api/v2/events/stream?token=${API_TOKEN}\""
  echo ""
  echo "Or use websocat:"
  echo "  websocat \"ws://localhost:8000/api/v2/events/stream?token=${API_TOKEN}\""
  echo ""

  # Check workflow status via API
  echo -e "${BLUE}=== Get Work Item Status ===${NC}\n"

  echo "To check work item status:"
  echo "  curl \"${BASE_URL}/api/v2/work-items/${WORK_ITEM_ID}\" \\"
  echo "    -H \"Authorization: Bearer ${API_TOKEN}\" | jq '.'"
  echo ""

  echo "To list executions for this workflow:"
  echo "  curl \"${BASE_URL}/api/v2/executions/?workflow_run_id=${WORKFLOW_RUN_ID}\" \\"
  echo "    -H \"Authorization: Bearer ${API_TOKEN}\" | jq '.'"
  echo ""

else
  echo "Error starting workflow"
  echo "$WORKFLOW_RUN"
  exit 1
fi

echo -e "${GREEN}✓ Workflow started successfully${NC}"
echo "  Monitor at: ${BASE_URL}/api/docs"
