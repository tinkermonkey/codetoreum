# Codetoreum Documentation

This directory contains all documentation for the Codetoreum AI Agent Orchestration Platform.

## Table of Contents

### Getting Started
- [Project Overview](../README.md) - Main project README with quick start guide
- [Environment Setup](claude_thoughts/ENVIRONMENT_SETUP.md) - Initial environment configuration
- [Setup Summary](claude_thoughts/SETUP_SUMMARY.md) - Setup process summary

### Architecture & Design

#### Gen 2 Architecture (Current)
- [Design Changes](01_design/01_design_changes.md) - Key changes from Gen 1 to Gen 2
- [High Level Architecture](01_design/02_high_level_arch.md) - Hexagonal architecture overview
- [Implementation Plan](01_design/03_implementation_plan.md) - Detailed implementation roadmap

##### Domain Layer
- [Domain Inventory](01_design/domains/domains_inventory.md) - All domain models
- [Work Item](01_design/domains/work_item_design.md)
- [Agent](01_design/domains/agent_design.md)
- [Agent Execution](01_design/domains/agent_execution_design.md)
- [Workflow](01_design/domains/workflow_design.md)
- [Workflow Template](01_design/domains/workflow_template_design.md)
- [Pipeline Stage](01_design/domains/pipeline_stage_design.md)
- [Review Cycle](01_design/domains/review_cycle_design.md)
- [Execution Result](01_design/domains/execution_result_design.md)
- [Project Context](01_design/domains/project_context_design.md)
- [Workspace Context](01_design/domains/workspace_context_design.md)
- [Value Objects](01_design/domains/value_objects_design.md)
- [Domain Services](01_design/domains/domain_services_design.md)
- [Domain Events](01_design/domains/domain_events_design.md)

##### Application Services
- [Application Services Inventory](01_design/application_services/application_services_inventory.md)
- [Workflow Orchestrator](01_design/application_services/workflow_orchestrator_design.md)
- [Agent Executor](01_design/application_services/agent_executor_design.md)
- [Consolidated Services](01_design/application_services/consolidated_services_design.md)

##### Ports (Interfaces)
- [Input Ports Inventory](01_design/input_ports/input_ports_inventory.md)
  - [Workflow Command Port](01_design/input_ports/workflow_command_port_design.md)
  - [Agent Interaction Command Port](01_design/input_ports/agent_interaction_command_port_design.md)
  - [Configuration Command Port](01_design/input_ports/configuration_command_port_design.md)
  - [GitHub Webhook Port](01_design/input_ports/github_webhook_port_design.md)
- [Output Ports Inventory](01_design/output_ports/output_ports_inventory.md)
  - [ITicketSystem](01_design/output_ports/iticket_system_design.md)
  - [ILLMProvider](01_design/output_ports/illm_provider_design.md)
  - [IContainer](01_design/output_ports/icontainer_design.md)
  - [IRepository](01_design/output_ports/irepository_design.md)
  - [IEventStore](01_design/output_ports/ievent_store_design.md)
  - [IStorage](01_design/output_ports/istorage_design.md)
  - [IConfigStore](01_design/output_ports/iconfig_store_design.md)
  - [ILogger](01_design/output_ports/ilogger_design.md)
  - [IMetrics](01_design/output_ports/imetrics_design.md)
  - [ITracer](01_design/output_ports/itracer_design.md)
  - [IAuditor](01_design/output_ports/iauditor_design.md)
  - [INotifier](01_design/output_ports/inotifier_design.md)

##### Adapters
- [Primary Adapters Inventory](01_design/primary_adapters/primary_adapters_inventory.md) - Inbound adapters
  - [Web UI Adapter](01_design/primary_adapters/web_ui_adapter_design.md)
  - [CLI Adapter](01_design/primary_adapters/cli_adapter.md)
  - [GitHub Webhook Adapter](01_design/primary_adapters/github_webhook_adapter_design.md)
- [Secondary Adapters Inventory](01_design/secondary_adapters/secondary_adapters_inventory.md) - Outbound adapters
  - [Ticket System Adapters](01_design/secondary_adapters/ticket_system_adapters_design.md)
  - [LLM Provider Adapters](01_design/secondary_adapters/llm_provider_adapters_design.md)
  - [Infrastructure Adapters](01_design/secondary_adapters/infrastructure_adapters_design.md)

##### Events
- [Events Inventory](01_design/events/events_inventory.md)
- [Agent Lifecycle Events](01_design/events/agent_lifecycle_events_design.md)
- [Pipeline and Repair Events](01_design/events/pipeline_and_repair_events_design.md)
- [Decision Events](01_design/events/decision_events_design.md)
- [System and Integration Events](01_design/events/system_and_integration_events_design.md)

##### Infrastructure
- [Infrastructure Inventory](01_design/infrastructure/infrastructure_inventory.md)
- [Resilience Infrastructure](01_design/infrastructure/resilience_infrastructure_design.md)
- [Event Sourcing Implementation](01_design/infrastructure/event_sourcing_implementation.md)

##### External Systems
- [External Systems Inventory](01_design/external_systems/external_systems_inventory.md)
- [GitHub API](01_design/external_systems/github_api_design.md)
- [Claude API](01_design/external_systems/claude_api_design.md)
- [Docker](01_design/external_systems/docker_design.md)
- [Redis](01_design/external_systems/redis_design.md)
- [Elasticsearch](01_design/external_systems/elasticsearch_design.md)

#### Gen 1 Architecture (Legacy)
- [Gen 1 Overview](00_legacy/README.md)
- [Redesign Goals](00_legacy/00_redesign_goals.md)
- [Components and Layers](00_legacy/01_components_and_layers.md)
- [Component Interfaces](00_legacy/02_component_interfaces.md)
- [Information Flow Patterns](00_legacy/03_information_flow_patterns.md)
- [Containerization Architecture](00_legacy/04_containerization_architecture.md)
- [Quick Reference](00_legacy/QUICK_REFERENCE.md)

### Implementation Guides

#### Implementation Summaries
- [Domain Models Implementation](implementation/domain_models_summary.md)
- [Integration Implementation](implementation/integration_summary.md)
- [Resilience Patterns Implementation](implementation/resilience_patterns_summary.md)
- [Web Dashboard Implementation](implementation/web_dashboard_summary.md)
- [Revision Complete](implementation/revision_complete.md)

#### API Documentation
- [REST API Overview](api/rest_api_overview.md)
- [Config & Metrics API Implementation](api/config_metrics_implementation.md)
- [API Usage Examples](api/usage_examples.md)
- [API Authentication](API_AUTHENTICATION.md)

#### Frontend
- [Build Instructions](frontend/build_instructions.md)

#### Configuration & Operation
- [Hybrid Mode Configuration Guide](hybrid_mode_configuration_guide.md)
- [Implementation Notes: Hybrid Mode](implementation_notes_hybrid_mode.md)
- [Simulation Mode Testing Plan](simulation_mode_testing_plan.md)
- [Exception Handling Guide](exception_handling_guide.md)
- [WebSocket Horizontal Scaling](websocket_horizontal_scaling.md)
- [Event Handler Usage Guide](claude_thoughts/EVENT_HANDLER_USAGE_GUIDE.md)

### Task Reports & Implementation Details
- [Phase 2.4 Implementation](claude_thoughts/PHASE_2_4_IMPLEMENTATION_SUMMARY.md)
- [Phase 2.5 Implementation](claude_thoughts/PHASE_2_5_IMPLEMENTATION_SUMMARY.md)
- [Phase 2.6 Implementation](claude_thoughts/PHASE_2_6_IMPLEMENTATION_SUMMARY.md)
- [Phase 5-6 Completion](claude_thoughts/PHASE_5_6_COMPLETION_SUMMARY.md)
- [Phase 7 Part 1 Summary](claude_thoughts/PHASE_7_PART_1_SUMMARY.md)
- [Phase 7 Part 1 Revision](claude_thoughts/PHASE_7_PART_1_REVISION_SUMMARY.md)
- [Phase 7 Part 2 Implementation](claude_thoughts/PHASE_7_PART_2_IMPLEMENTATION_SUMMARY.md)
- [Phase 7 Completion Report](claude_thoughts/PHASE_7_COMPLETION_REPORT.md)
- [Phase 7 Revision Implementation](claude_thoughts/PHASE_7_REVISION_IMPLEMENTATION.md)
- [Phase 7 Revision Complete](claude_thoughts/PHASE7_REVISION_COMPLETE.md)
- [Reliability Improvements](claude_thoughts/RELIABILITY_IMPROVEMENTS_SUMMARY.md)
- [Revision Summary](claude_thoughts/REVISION_SUMMARY.md)

## Documentation Organization

### `/documentation/00_legacy/`
Contains documentation for the Gen 1 system architecture. This is kept for historical reference and understanding the evolution of the system.

### `/documentation/01_design/`
Contains all Gen 2 architecture design specifications organized by layer:
- `domains/` - Domain model specifications
- `application_services/` - Application service designs
- `input_ports/` - Inbound port interfaces
- `output_ports/` - Outbound port interfaces
- `primary_adapters/` - Inbound adapter implementations
- `secondary_adapters/` - Outbound adapter implementations
- `events/` - Domain event catalog
- `infrastructure/` - Cross-cutting infrastructure
- `external_systems/` - External system integration specs

### `/documentation/api/`
REST API documentation including:
- API overviews and architecture
- Implementation details
- Usage examples
- Authentication guides

### `/documentation/frontend/`
Frontend application documentation including:
- Build and deployment instructions
- Component architecture
- Development guides

### `/documentation/implementation/`
Implementation summaries documenting the development progress and key decisions made during different implementation stages of the project.

### `/documentation/claude_thoughts/`
Detailed task completion reports and implementation summaries for specific features and improvements.

## Key Concepts

### Hexagonal Architecture
The Gen 2 system follows hexagonal architecture (ports and adapters pattern) with:
- **Domain Layer**: Pure business logic with no external dependencies
- **Application Layer**: Orchestration services
- **Ports**: Clean interfaces between core and external systems
- **Adapters**: Swappable implementations (production + mock/simulation)

### Event Sourcing
All state changes in the system emit domain events, providing:
- Complete audit trail
- Replay capability for debugging
- Time-travel debugging in simulation mode

### Simulation Mode
The system supports full end-to-end testing without external services through:
- Mock adapters for all external systems
- Deterministic LLM responses
- Time manipulation for fast-forwarding
- Event replay for debugging

### Security Model
Containerized agents operate with:
- ✅ Internet access
- ✅ Mounted project files (read/write or read-only)
- ✅ Project-level environment variables
- ❌ No git credentials or SSH keys
- ❌ No GitHub credentials
- ❌ No Docker socket access

The orchestrator handles all privileged operations (git, GitHub API, etc.).

## Contributing to Documentation

When adding or updating documentation:

1. Place design docs in appropriate `/01_design/` subdirectories
2. Place implementation guides in `/implementation/` or `/api/` or `/frontend/`
3. Place task reports in `/claude_thoughts/`
4. Update this README's table of contents
5. Follow markdown best practices (headers, code blocks, links)
6. Include diagrams where helpful (mermaid, ASCII art, or images)

## Questions or Issues?

Refer to the [main README](../README.md) for project overview and quick start instructions.
