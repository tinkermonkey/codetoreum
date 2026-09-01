#!/bin/bash
#
# End-to-End Conversational Loop Verification Script
#
# This script helps you run the E2E test for the conversational loop
# with production GitHub wiring.
#
# Usage:
#   ./tests/e2e/run_e2e_verification.sh
#
# It will prompt for required environment variables if not set.

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Codetoreum E2E Test: Conversational Loop Production Wiring${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# Check for required environment variables
check_env_var() {
    local var_name=$1
    local var_prompt=$2

    if [ -z "${!var_name:-}" ]; then
        echo -e "${YELLOW}⚠ ${var_name} not set${NC}"
        read -p "  $var_prompt: " var_value
        export "$var_name=$var_value"
    else
        echo -e "${GREEN}✓ ${var_name} is set${NC}"
    fi
}

# Collect environment variables
echo "Checking required environment variables..."
echo ""

check_env_var "GITHUB_TOKEN" "Enter your GitHub personal access token (ghp_...)"
check_env_var "GITHUB_TEST_REPO" "Enter test repository in format 'org/repo'"
check_env_var "GITHUB_TEST_WORK_ITEM_ID" "Enter GitHub issue or discussion number"

echo ""
echo -e "${BLUE}───────────────────────────────────────────────────────────────${NC}"
echo "Configuration:"
echo -e "  Repository: ${GITHUB_TEST_REPO}"
echo -e "  Work Item ID: ${GITHUB_TEST_WORK_ITEM_ID}"
echo -e "  Token: ${GITHUB_TOKEN:0:20}...${GITHUB_TOKEN: -4}"
echo -e "${BLUE}───────────────────────────────────────────────────────────────${NC}"
echo ""

# Validate token by making a test API call
echo "Validating GitHub token..."
if response=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: token ${GITHUB_TOKEN}" \
    https://api.github.com/user); then
    if [ "$response" = "200" ]; then
        echo -e "${GREEN}✓ GitHub token is valid${NC}"
    else
        echo -e "${RED}✗ GitHub token validation failed (HTTP $response)${NC}"
        echo "  Ensure your token has 'repo' scope"
        exit 1
    fi
else
    echo -e "${RED}✗ Failed to validate token${NC}"
    exit 1
fi

echo ""

# Run the E2E test
echo -e "${BLUE}Running E2E test...${NC}"
echo ""

python -m pytest \
    tests/e2e/test_conversational_loop_production_e2e.py::TestConversationalLoopProductionE2E::test_conversational_loop_posts_to_real_github \
    -v -s \
    --tb=short

test_result=$?

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"

if [ $test_result -eq 0 ]; then
    echo -e "${GREEN}✅ E2E Test PASSED${NC}"
    echo ""
    echo "Verification complete!"
    echo "✓ Conversational loop with production GitHub wiring verified"
    echo "✓ Comment detected and response posted to real GitHub"
    echo "✓ Full event path confirmed"
    echo ""
else
    echo -e "${RED}❌ E2E Test FAILED${NC}"
    echo ""
    echo "Troubleshooting tips:"
    echo "  • Check GitHub token has 'repo' scope"
    echo "  • Verify work item exists: ${GITHUB_TEST_REPO}/issues/${GITHUB_TEST_WORK_ITEM_ID}"
    echo "  • Check GitHub API rate limits: curl -H \"Authorization: token \$GITHUB_TOKEN\" https://api.github.com/rate_limit"
    echo ""
fi

echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"

exit $test_result
