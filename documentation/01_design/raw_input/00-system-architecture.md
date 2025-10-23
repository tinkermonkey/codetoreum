# System Architecture Overview

## Executive Summary

Codetroeum is a next-generation AI-powered software development orchestration system designed with testability, extensibility, and reliability at its core. The system follows a **Hexagonal Architecture** pattern (Ports & Adapters) combined with **Event Sourcing** and **CQRS** to enable complete simulation testing, plugin-based extensibility, and comprehensive observability.

## Core Architecture Diagram

```mermaid
graph TB
    subgraph "External Systems"
        GH[GitHub Webhooks]
        UI[Web Dashboard]
        CLI[CLI Tools]
        CRON[Scheduled Tasks]
    end
    
    subgraph "Primary Adapters"
        WHA[Webhook Adapter]
        RESTA[REST API Adapter]
        WSA[WebSocket Adapter]
        CLIA[CLI Adapter]
    end
    
    subgraph "Input Ports"
        WCP[WorkflowCommandPort]
        TQP[TaskQueryPort]
        ESP[EventStreamPort]
        CCP[ConfigCommandPort]
    end
    
    subgraph "Hexagonal Core"
        subgraph "Application Services"
            WO[Workflow Orchestrator]
            AS[Agent Scheduler]
            PM[Pipeline Manager]
            RS[Review Service]
            WR[Workspace Router]
            EP[Event Processor]
        end
        
        subgraph "Domain Layer"
            WI[Work Item]
            AE[Agent Execution]
            PS[Pipeline Stage]
            PC[Project Context]
            WT[Workflow Template]
            RC[Review Cycle]
        end
        
        subgraph "Event Store"
            ES[Event Store]
            ESS[Event Stream]
            ESP2[Event Snapshot]
        end
    end
    
    subgraph "Output Ports"
        TSP[ITicketSystem]
        LLP[ILLMProvider]
        RRP[IRepository]
        CTP[IContainer]
        EVP[IEventStore]
        MTP[IMetrics]
        NTP[INotifier]
        STP[IStorage]
    end
    
    subgraph "Secondary Adapters - Production"
        GHA[GitHub Adapter]
        CCA[Claude Code Adapter]
        GRA[Git Repository Adapter]
        DCA[Docker Container Adapter]
        REA[Redis Event Adapter]
        ESA[Elasticsearch Adapter]
    end
    
    subgraph "Secondary Adapters - Testing"
        MTA[Mock Ticket Adapter]
        MLA[Mock LLM Adapter]
        MRA[Mock Repo Adapter]
        FCA[Fake Container Adapter]
        MEA[Memory Event Adapter]
        MMA[Memory Metrics Adapter]
    end
    
    GH --> WHA
    UI --> RESTA
    UI --> WSA
    CLI --> CLIA
    CRON --> WHA
    
    WHA --> WCP
    RESTA --> WCP
    RESTA --> TQP
    WSA --> ESP
    CLIA --> CCP
    
    WCP --> WO
    TQP --> AS
    ESP --> EP
    CCP --> PM
    
    WO --> ES
    AS --> ES
    PM --> ES
    RS --> ES
    
    WO --> TSP
    AS --> LLP
    PM --> RRP
    WR --> CTP
    EP --> EVP
    
    TSP --> GHA
    TSP --> MTA
    LLP --> CCA
    LLP --> MLA
    RRP --> GRA
    RRP --> MRA
    CTP --> DCA
    CTP --> FCA
    EVP --> REA
    EVP --> MEA
    MTP --> ESA
    MTP --> MMA
```

## Architectural Patterns

### 1. Hexagonal Architecture (Ports & Adapters)

The system is organized into three main zones:

- **Core Domain**: Pure business logic with no external dependencies
- **Ports**: Interfaces that define contracts between core and external world
- **Adapters**: Implementations that connect to external systems

This separation enables:
- Complete isolation of business logic
- Easy testing with mock adapters
- Plugin-based extensibility
- Technology-agnostic core

### 2. Event Sourcing

All state changes are captured as immutable events:

```mermaid
sequenceDiagram
    participant C as Command
    participant D as Domain
    participant E as Event Store
    participant P as Projections
    
    C->>D: Execute Command
    D->>D: Business Logic
    D->>E: Store Event
    E->>P: Update Read Models
    P-->>C: Query Result
```

Benefits:
- Complete audit trail
- Time-travel debugging
- Event replay for testing
- Eventual consistency

### 3. CQRS (Command Query Responsibility Segregation)

Commands and queries follow separate paths:

```mermaid
graph LR
    subgraph "Write Side"
        CMD[Commands] --> CH[Command Handlers]
        CH --> DM[Domain Models]
        DM --> ES[Event Store]
    end
    
    subgraph "Read Side"
        ES --> PR[Projections]
        PR --> RM[Read Models]
        RM --> QH[Query Handlers]
        QH --> QRY[Queries]
    end
```

### 4. Domain-Driven Design

The core domain is modeled around business concepts:

```mermaid
graph TB
    subgraph "Core Domain"
        WI[Work Item]
        WF[Workflow]
        AG[Agent]
        EX[Execution]
        RV[Review]
        
        WI --> WF
        WF --> AG
        AG --> EX
        EX --> RV
        RV --> WI
    end
```

## System Layers

### 1. External Systems Layer
- GitHub (webhooks, API)
- Web Dashboard (UI)
- CLI Tools
- Scheduled Tasks (cron)

### 2. Primary Adapters Layer
Converts external requests into domain commands:
- **Webhook Adapter**: Processes GitHub webhooks
- **REST API Adapter**: Handles HTTP requests
- **WebSocket Adapter**: Real-time event streaming
- **CLI Adapter**: Command-line interface

### 3. Input Ports Layer
Defines interfaces for incoming operations:
- **WorkflowCommandPort**: Workflow management commands
- **TaskQueryPort**: Task status queries
- **EventStreamPort**: Event subscription
- **ConfigCommandPort**: Configuration management

### 4. Application Services Layer
Orchestrates domain logic:
- **Workflow Orchestrator**: Manages workflow execution
- **Agent Scheduler**: Schedules agent executions
- **Pipeline Manager**: Controls pipeline flow
- **Review Service**: Handles review cycles
- **Workspace Router**: Routes work to appropriate workspace
- **Event Processor**: Processes domain events

### 5. Domain Layer
Pure business logic:
- **Work Item**: Core work unit (issue, task)
- **Agent Execution**: Agent run context
- **Pipeline Stage**: Pipeline step definition
- **Project Context**: Project configuration
- **Workflow Template**: Workflow definition
- **Review Cycle**: Review iteration logic

### 6. Event Store Layer
Persistence and event management:
- **Event Store**: Append-only event storage
- **Event Stream**: Real-time event distribution
- **Event Snapshot**: Point-in-time state capture

### 7. Output Ports Layer
Interfaces for external dependencies:
- **ITicketSystem**: Issue/ticket management
- **ILLMProvider**: LLM integration
- **IRepository**: Source control
- **IContainer**: Container orchestration
- **IEventStore**: Event persistence
- **IMetrics**: Metrics collection
- **INotifier**: Notification dispatch
- **IStorage**: File/configuration storage

### 8. Secondary Adapters Layer
Implements output port interfaces:

**Production Adapters**:
- GitHub Adapter
- Claude Code Adapter
- Git Repository Adapter
- Docker Container Adapter
- Redis Event Adapter
- Elasticsearch Adapter

**Testing Adapters**:
- Mock Ticket Adapter
- Mock LLM Adapter
- Mock Repository Adapter
- Fake Container Adapter
- Memory Event Adapter
- Memory Metrics Adapter

## Data Flow

### 1. Command Flow

```mermaid
sequenceDiagram
    participant E as External System
    participant PA as Primary Adapter
    participant IP as Input Port
    participant AS as App Service
    participant D as Domain
    participant ES as Event Store
    participant OP as Output Port
    participant SA as Secondary Adapter
    
    E->>PA: External Request
    PA->>IP: Convert to Command
    IP->>AS: Execute Command
    AS->>D: Domain Logic
    D->>ES: Store Events
    AS->>OP: Side Effects
    OP->>SA: External Call
    SA-->>E: Response
```

### 2. Query Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant API as REST API
    participant QP as Query Port
    participant QH as Query Handler
    participant RM as Read Model
    
    C->>API: Query Request
    API->>QP: Query
    QP->>QH: Handle Query
    QH->>RM: Fetch Data
    RM-->>QH: Data
    QH-->>QP: Result
    QP-->>API: Response
    API-->>C: JSON Response
```

### 3. Event Flow

```mermaid
sequenceDiagram
    participant D as Domain
    participant ES as Event Store
    participant EB as Event Bus
    participant P1 as Projection 1
    participant P2 as Projection 2
    participant WS as WebSocket
    
    D->>ES: Emit Event
    ES->>EB: Publish Event
    EB->>P1: Update Read Model
    EB->>P2: Update Metrics
    EB->>WS: Stream to Clients
```

## Simulation Mode Architecture

The system supports full simulation mode for testing:

```mermaid
graph TB
    subgraph "Simulation Controller"
        SC[Simulation Clock]
        SR[Scenario Runner]
        SV[Scenario Validator]
    end
    
    subgraph "Mock Infrastructure"
        MT[Mock Time]
        ME[Mock Events]
        MA[Mock Adapters]
    end
    
    subgraph "Test Scenarios"
        TS1[Happy Path]
        TS2[Error Cases]
        TS3[Performance]
        TS4[Chaos Testing]
    end
    
    SC --> MT
    SR --> MA
    SR --> ME
    
    TS1 --> SR
    TS2 --> SR
    TS3 --> SR
    TS4 --> SR
    
    SR --> SV
```

## Key Design Decisions

### 1. Hexagonal Architecture
**Decision**: Use Ports & Adapters pattern
**Rationale**: 
- Enables complete testing without external dependencies
- Allows easy swapping of implementations
- Keeps business logic pure and testable

### 2. Event Sourcing
**Decision**: Store all state changes as events
**Rationale**:
- Provides complete audit trail
- Enables replay for debugging
- Supports time-travel testing
- Natural fit for distributed systems

### 3. CQRS
**Decision**: Separate command and query paths
**Rationale**:
- Optimizes read and write operations independently
- Enables different models for queries
- Simplifies caching strategies

### 4. Plugin Architecture
**Decision**: Support pluggable adapters
**Rationale**:
- Easy addition of new ticket systems
- Support for multiple LLM providers
- Enables gradual migration

### 5. Database Configuration
**Decision**: Store configuration in database
**Rationale**:
- Web UI for configuration
- Version control for configs
- Dynamic updates without restart

## Deployment Architecture

```mermaid
graph TB
    subgraph "Container Orchestration"
        K8S[Kubernetes Cluster]
        
        subgraph "Core Services"
            API[API Service]
            WRK[Worker Service]
            SCH[Scheduler Service]
        end
        
        subgraph "Infrastructure Services"
            RD[Redis]
            ES[Elasticsearch]
            PG[PostgreSQL]
        end
        
        subgraph "Monitoring"
            PM[Prometheus]
            GF[Grafana]
            JG[Jaeger]
        end
    end
    
    LB[Load Balancer] --> API
    API --> RD
    WRK --> RD
    SCH --> RD
    
    API --> PG
    WRK --> ES
    
    PM --> GF
    API --> JG
    WRK --> JG
```

## Security Architecture

```mermaid
graph TB
    subgraph "Security Layers"
        AUTH[Authentication]
        AUTHZ[Authorization]
        ENC[Encryption]
        AUD[Audit]
    end
    
    subgraph "Secret Management"
        KV[Key Vault]
        SM[Secret Manager]
        CERT[Certificates]
    end
    
    subgraph "Network Security"
        FW[Firewall]
        VPN[VPN Gateway]
        WAF[Web App Firewall]
    end
    
    AUTH --> KV
    AUTHZ --> SM
    ENC --> CERT
    
    FW --> WAF
    WAF --> VPN
```

## Next Steps

1. Review [Hexagonal Architecture Details](01-hexagonal-architecture.md)
2. Explore [Event Sourcing & CQRS](02-event-sourcing-cqrs.md)
3. Understand [Testing Strategy](03-testing-strategy.md)
4. Dive into component specifications in the [Components Directory](../components/)
