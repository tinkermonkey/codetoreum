#!/bin/bash
#
# Example: Authentication flows in Codetoreum API
#
# This example demonstrates the different ways to authenticate
# with the Codetoreum API.

# Configuration
BASE_URL="http://localhost:8000"
API_TOKEN="your_token_here"  # Get from server startup logs

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Authentication Examples ===${NC}\n"

echo "The Codetoreum API uses JWT-based single-token authentication."
echo "The token is printed to the console when the server starts."
echo ""

# Method 1: Authorization Header (Recommended)
echo -e "${BLUE}Method 1: Authorization Header (Recommended)${NC}\n"

echo "Using Bearer token in Authorization header:"
echo ""

curl -s -X GET "${BASE_URL}/api/v2/health" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -w "\nHTTP Status: %{http_code}\n" | jq '.'

echo ""

# Method 2: Query Parameter
echo -e "${BLUE}Method 2: Query Parameter${NC}\n"

echo "Using token as query parameter:"
echo ""

curl -s -X GET "${BASE_URL}/api/v2/health?token=${API_TOKEN}" \
  -w "\nHTTP Status: %{http_code}\n" | jq '.'

echo ""

# Method 3: Cookie (after setting)
echo -e "${BLUE}Method 3: Cookie${NC}\n"

echo "Using cookie (must be set first):"
echo ""

# Create a cookie jar
COOKIE_JAR=$(mktemp)

# First request sets the cookie (simulated - normally done by login endpoint)
curl -s -X GET "${BASE_URL}/api/v2/health" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -c "${COOKIE_JAR}" \
  -w "\nHTTP Status: %{http_code}\n" | jq '.'

echo ""
echo "Cookie stored in: ${COOKIE_JAR}"
echo "Cookie contents:"
cat "${COOKIE_JAR}"
echo ""

# Subsequent request uses the cookie
echo "Making request with cookie:"
curl -s -X GET "${BASE_URL}/api/v2/health" \
  -b "${COOKIE_JAR}" \
  -w "\nHTTP Status: %{http_code}\n" | jq '.'

# Clean up
rm -f "${COOKIE_JAR}"
echo ""

# Get token information
echo -e "${BLUE}=== Get Token Information ===${NC}\n"

TOKEN_INFO=$(curl -s -X GET "${BASE_URL}/api/v2/auth/token-info?token=${API_TOKEN}")

echo "Token information:"
echo "$TOKEN_INFO" | jq '.'
echo ""

# Check if token is valid
IS_VALID=$(echo "$TOKEN_INFO" | jq -r '.valid')

if [ "$IS_VALID" = "true" ]; then
  echo -e "${GREEN}✓ Token is valid${NC}"

  EXPIRES_AT=$(echo "$TOKEN_INFO" | jq -r '.expires_at // "never"')
  echo "Expires at: ${EXPIRES_AT}"
else
  echo -e "${YELLOW}⚠ Token is invalid or expired${NC}"
fi

echo ""

# Error examples
echo -e "${BLUE}=== Error Examples ===${NC}\n"

echo "1. Missing authentication:"
curl -s -X GET "${BASE_URL}/api/v2/work-items/" \
  -w "\nHTTP Status: %{http_code}\n" | jq '.'

echo ""

echo "2. Invalid token:"
curl -s -X GET "${BASE_URL}/api/v2/work-items/" \
  -H "Authorization: Bearer invalid_token_here" \
  -w "\nHTTP Status: %{http_code}\n" | jq '.'

echo ""

# Logout
echo -e "${BLUE}=== Logout ===${NC}\n"

echo "To logout and clear the cookie:"
curl -s -X POST "${BASE_URL}/api/v2/auth/logout" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -w "\nHTTP Status: %{http_code}\n" | jq '.'

echo ""

# Best practices
echo -e "${BLUE}=== Best Practices ===${NC}\n"

cat <<EOF
1. Store tokens securely (environment variables, secret managers)
2. Use Authorization header for API clients (most secure)
3. Use query parameter only for WebSocket connections
4. Never commit tokens to version control
5. Regenerate tokens if compromised
6. Use HTTPS in production to prevent token interception

Example environment variable usage:
  export CODETOREUM_API_TOKEN="your_token_here"
  curl -H "Authorization: Bearer \${CODETOREUM_API_TOKEN}" \\
    "${BASE_URL}/api/v2/work-items/"

For WebSocket connections:
  wscat -c "ws://localhost:8000/api/v2/events/stream?token=\${CODETOREUM_API_TOKEN}"
EOF

echo ""
echo -e "${GREEN}✓ Done${NC}"
