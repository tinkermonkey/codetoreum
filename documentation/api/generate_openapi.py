"""
Generate OpenAPI specification with enhanced examples and documentation.

This script extracts the OpenAPI spec from the FastAPI application and enhances it
with comprehensive examples, error responses, and authentication documentation.
"""
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from codetoreum.adapters.primary.fastapi_app import create_app


def enhance_openapi_spec(spec: dict) -> dict:
    """Enhance OpenAPI spec with examples and documentation."""

    # Add comprehensive API info
    spec["info"]["description"] = """
# Codetoreum API Documentation

AI Agent Orchestration Platform for automating software development workflows.

## Authentication

This API uses JWT-based single-token authentication similar to JupyterLab.

### Getting Your Token

The authentication token is printed to the console when the server starts:

```
[Codetoreum] Access token: eyJhbGc...
```

### Using the Token

Include the token in one of three ways:

1. **Authorization Header** (Recommended):
   ```
   Authorization: Bearer eyJhbGc...
   ```

2. **Query Parameter**:
   ```
   GET /api/v2/work-items?token=eyJhbGc...
   ```

3. **Cookie** (after login):
   ```
   Cookie: codetoreum_token=eyJhbGc...
   ```

### Token Information

- Get token info: `GET /api/v2/auth/token-info?token=YOUR_TOKEN`
- Logout: `POST /api/v2/auth/logout`

## Rate Limiting

Default: 100 requests per minute per IP address.

Rate limit headers in responses:
- `X-RateLimit-Limit`: Total requests allowed
- `X-RateLimit-Remaining`: Remaining requests
- `X-RateLimit-Reset`: Time when limit resets

## Error Responses

All endpoints return consistent error responses:

```json
{
  "detail": "Error message",
  "error_code": "ERROR_CODE",
  "timestamp": "2025-11-05T10:30:00Z"
}
```

Common HTTP status codes:
- `400`: Bad Request - Invalid input
- `401`: Unauthorized - Missing or invalid token
- `403`: Forbidden - Insufficient permissions
- `404`: Not Found - Resource doesn't exist
- `422`: Unprocessable Entity - Validation error
- `429`: Too Many Requests - Rate limit exceeded
- `500`: Internal Server Error - Server error

## WebSocket Events

Real-time event streaming via WebSocket:

```
ws://localhost:8000/api/v2/events/stream?token=YOUR_TOKEN
```

Event types:
- `workflow.started`
- `workflow.stage_changed`
- `execution.started`
- `execution.completed`
- `execution.failed`
- `work_item.updated`

## Pagination

List endpoints support pagination:

Query parameters:
- `offset`: Number of items to skip (default: 0)
- `limit`: Maximum items to return (default: 50, max: 100)
- `sort_by`: Field to sort by
- `sort_order`: `asc` or `desc`

Response includes:
```json
{
  "items": [...],
  "total": 150,
  "offset": 0,
  "limit": 50
}
```

## Versioning

Current API version: v2 (`/api/v2/*`)

Legacy v1 API still available for backward compatibility.
"""

    # Add security scheme
    spec["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT token authentication. Get token from server startup logs."
        },
        "QueryAuth": {
            "type": "apiKey",
            "in": "query",
            "name": "token",
            "description": "JWT token as query parameter (alternative to Bearer auth)"
        },
        "CookieAuth": {
            "type": "apiKey",
            "in": "cookie",
            "name": "codetoreum_token",
            "description": "JWT token in cookie (set after login)"
        }
    }

    # Add example components
    spec["components"]["examples"] = {
        "WorkItemExample": {
            "value": {
                "id": "wi_abc123",
                "external_id": "123",
                "title": "Implement user authentication",
                "description": "Add JWT-based authentication to the API",
                "status": "in_progress",
                "project_id": "my-project",
                "assignee": "agent-backend-dev",
                "labels": ["feature", "authentication"],
                "workflow_stage": "development",
                "priority": "high",
                "created_at": "2025-11-05T10:00:00Z",
                "updated_at": "2025-11-05T11:30:00Z"
            }
        },
        "AgentExample": {
            "value": {
                "id": "agent_xyz789",
                "name": "backend-dev",
                "description": "Backend development specialist",
                "agent_type": "claude_code",
                "capabilities": ["python", "fastapi", "postgresql"],
                "configuration": {
                    "model": "claude-sonnet-4",
                    "temperature": 0.7,
                    "max_tokens": 4000
                },
                "active": True,
                "created_at": "2025-11-01T09:00:00Z"
            }
        },
        "ExecutionExample": {
            "value": {
                "id": "exec_def456",
                "agent_id": "agent_xyz789",
                "work_item_id": "wi_abc123",
                "workflow_run_id": "run_ghi789",
                "stage_name": "development",
                "status": "running",
                "started_at": "2025-11-05T11:30:00Z",
                "container_id": "abc123def456",
                "progress": {
                    "current_step": "writing_code",
                    "total_steps": 5,
                    "percentage": 40
                }
            }
        },
        "WorkflowExample": {
            "value": {
                "id": "wf_jkl012",
                "name": "standard-feature-workflow",
                "description": "Standard workflow for feature development",
                "version": "1.0.0",
                "active": True,
                "stages": [
                    {
                        "name": "analysis",
                        "agent_id": "agent-analyzer",
                        "entry_conditions": ["work_item.labels contains 'feature'"],
                        "timeout_minutes": 30
                    },
                    {
                        "name": "development",
                        "agent_id": "agent-backend-dev",
                        "entry_conditions": ["previous_stage.status == 'completed'"],
                        "timeout_minutes": 120
                    }
                ]
            }
        },
        "ErrorResponse": {
            "value": {
                "detail": "Work item not found",
                "error_code": "WORK_ITEM_NOT_FOUND",
                "timestamp": "2025-11-05T12:00:00Z"
            }
        },
        "ValidationError": {
            "value": {
                "detail": [
                    {
                        "loc": ["body", "title"],
                        "msg": "field required",
                        "type": "value_error.missing"
                    }
                ]
            }
        },
        "UnauthorizedError": {
            "value": {
                "detail": "Invalid or expired authentication token",
                "error_code": "INVALID_TOKEN",
                "timestamp": "2025-11-05T12:00:00Z"
            }
        },
        "RateLimitError": {
            "value": {
                "detail": "Rate limit exceeded. Try again in 60 seconds.",
                "error_code": "RATE_LIMIT_EXCEEDED",
                "timestamp": "2025-11-05T12:00:00Z"
            }
        }
    }

    # Add common error responses to all authenticated endpoints
    common_error_responses = {
        "401": {
            "description": "Unauthorized - Invalid or missing authentication token",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Invalid or expired authentication token",
                        "error_code": "INVALID_TOKEN",
                        "timestamp": "2025-11-05T12:00:00Z"
                    }
                }
            }
        },
        "429": {
            "description": "Too Many Requests - Rate limit exceeded",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Rate limit exceeded. Try again in 60 seconds.",
                        "error_code": "RATE_LIMIT_EXCEEDED",
                        "timestamp": "2025-11-05T12:00:00Z"
                    }
                }
            }
        },
        "500": {
            "description": "Internal Server Error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An unexpected error occurred",
                        "error_code": "INTERNAL_ERROR",
                        "timestamp": "2025-11-05T12:00:00Z"
                    }
                }
            }
        }
    }

    # Add error responses to all paths
    for path_data in spec.get("paths", {}).values():
        for operation in path_data.values():
            if isinstance(operation, dict) and "responses" in operation:
                # Skip health check endpoints (they don't require auth)
                if operation.get("tags", [None])[0] != "health":
                    operation["responses"].update(common_error_responses)

    return spec


def main() -> None:
    """Generate enhanced OpenAPI specification."""
    # Create app with minimal config (no external dependencies)
    print("Creating FastAPI application...")
    app = create_app(
        disable_auth=True,  # Disable auth for spec generation
        cors_origins=["*"]
    )

    # Get OpenAPI spec
    print("Generating OpenAPI specification...")
    spec = app.openapi()

    # Enhance with examples and documentation
    print("Enhancing specification with examples...")
    enhanced_spec = enhance_openapi_spec(spec)

    # Write to file
    output_path = Path(__file__).parent / "openapi.yaml"
    print(f"Writing to {output_path}...")

    # Convert to YAML for better readability
    try:
        import yaml
        with open(output_path, "w") as f:
            yaml.dump(enhanced_spec, f, default_flow_style=False, sort_keys=False)
        print(f"✓ OpenAPI spec written to {output_path}")
    except ImportError:
        # Fallback to JSON if PyYAML not available
        output_path = output_path.with_suffix(".json")
        with open(output_path, "w") as f:
            json.dump(enhanced_spec, f, indent=2)
        print(f"✓ OpenAPI spec written to {output_path} (JSON)")
        print("  Install PyYAML for YAML output: pip install pyyaml")

    # Also write JSON version
    json_path = Path(__file__).parent / "openapi.json"
    with open(json_path, "w") as f:
        json.dump(enhanced_spec, f, indent=2)
    print(f"✓ OpenAPI spec (JSON) written to {json_path}")


if __name__ == "__main__":
    main()
