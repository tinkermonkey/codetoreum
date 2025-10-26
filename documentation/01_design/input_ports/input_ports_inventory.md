# Input Ports Inventory

## Overview

Input ports are the interfaces through which external systems and users interact with the Claudetoreum system. Following hexagonal architecture principles, input ports define the application's entry points and translate external requests into domain operations.

## Input Port Categories

### 1. External Trigger Ports
Ports that receive events and triggers from external systems.

### 2. Command Ports
Ports that accept commands to execute domain operations.

### 3. Query Ports
Ports that retrieve information from the system.

## Input Ports List

### External Trigger Ports

1. **GitHub Webhook Port**
   - Receives webhooks from GitHub for repository events
   - Handles: push events, pull request events, issue events, project board events
   - File: `input_ports/github_webhook_port_design.md`

2. **REST API Port**
   - Accepts HTTP REST requests for system operations
   - Handles: task management, configuration, status queries
   - File: `input_ports/rest_api_port_design.md`

3. **WebSocket Port**
   - Provides real-time bidirectional communication
   - Handles: live agent output streaming, system notifications
   - File: `input_ports/websocket_port_design.md`

4. **CLI Command Port**
   - Accepts command-line interface commands
   - Handles: administrative operations, debugging, manual task execution
   - File: `input_ports/cli_command_port_design.md`

5. **Scheduled Task Port**
   - Receives time-based triggers for scheduled operations
   - Handles: periodic cleanup, health checks, automated maintenance
   - File: `input_ports/scheduled_task_port_design.md`

### Command Ports

6. **Workflow Command Port**
   - Accepts commands to manage workflow execution
   - Handles: start workflow, pause workflow, cancel workflow, resume workflow
   - File: `input_ports/workflow_command_port_design.md`

7. **Task Command Port**
   - Accepts commands for task management
   - Handles: enqueue task, cancel task, retry task, requeue task
   - File: `input_ports/task_command_port_design.md`

8. **Configuration Command Port**
   - Accepts commands to modify system configuration
   - Handles: update project config, update agent config, update pipeline config
   - File: `input_ports/configuration_command_port_design.md`

9. **Agent Interaction Command Port**
   - Accepts user interactions with agents
   - Handles: ask question, provide feedback, approve/reject work, request revision
   - File: `input_ports/agent_interaction_command_port_design.md`

### Query Ports

10. **Task Query Port**
    - Retrieves task information and status
    - Handles: get task details, list tasks, query task history
    - File: `input_ports/task_query_port_design.md`

11. **Event Stream Port**
    - Provides access to system event streams
    - Handles: subscribe to events, query event history, filter events
    - File: `input_ports/event_stream_port_design.md`

12. **Configuration Query Port**
    - Retrieves system configuration
    - Handles: get project config, get agent config, list available agents/pipelines
    - File: `input_ports/configuration_query_port_design.md`

13. **Metrics Query Port**
    - Retrieves system metrics and analytics
    - Handles: get performance metrics, get usage statistics, get error rates
    - File: `input_ports/metrics_query_port_design.md`

14. **Agent Status Query Port**
    - Retrieves agent execution status and results
    - Handles: get agent status, get execution history, get output results
    - File: `input_ports/agent_status_query_port_design.md`

## Design Changes Impact

Based on the design changes documented in `01_design_changes.md`, input ports need to accommodate:

### Environment Variable Management
- New commands for managing project-level environment variables
- Configuration query port must expose environment variable definitions

### Commands and Sub-agents Mounting
- New commands for selecting which commands/sub-agents to mount
- Configuration must include mounted commands/sub-agents metadata

### Context File-Based Approach
- Input ports must support passing context file references instead of inline context
- Supports larger context without token limits
- Enables more complex context structures (multiple files, directories)

### Agent Container Interface Changes
- Input ports must NOT pass:
  - Git credentials
  - GitHub credentials
  - SSH keys
  - Docker socket access
- Input ports MUST pass:
  - Environment variables (project-level)
  - Mounted command/sub-agent references
  - Context file references
  - MCP config references

## Port Relationships

### Primary Flow
```
External Trigger → Command Port → Application Service → Domain
                                         ↓
                                    Output Port → External System
```

### Query Flow
```
Query Port → Application Service → Domain → Read Models
     ↓
  Response
```

### Event Flow
```
Domain Event → Event Store → Event Stream Port → Subscribers
```

## Implementation Notes

All input ports in the redesigned system will:

1. **Be Interface-Based**: Defined as abstract interfaces with multiple potential implementations
2. **Support Simulation**: Have mock/in-memory implementations for testing
3. **Be Technology-Agnostic**: Domain logic should not know about HTTP, WebSocket, or CLI details
4. **Validate Input**: Perform input validation before delegating to application services
5. **Use DTOs**: Convert external data formats to internal domain types
6. **Be Observable**: Emit events for all port interactions
7. **Support Versioning**: Allow multiple API versions for backward compatibility

## Next Steps

1. Create detailed design documents for each input port
2. Define input/output data structures for each port
3. Specify validation rules and error handling
4. Document authentication and authorization requirements
5. Create sequence diagrams for common flows through each port
