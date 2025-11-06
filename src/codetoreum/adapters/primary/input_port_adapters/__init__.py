"""
Input Port Adapters

This package contains implementations of input ports (primary adapters).

Input ports define the API that external actors (REST API, CLI, webhooks) use to
interact with the system. These adapters implement those port interfaces by:

- Query adapters: Reading from PostgreSQL read models and event store
- Command adapters: Delegating to application services that execute business logic
- Mock adapters: Providing in-memory implementations for development and testing

Directory structure:
- query/: PostgreSQL-backed query port implementations
- command/: Command port implementations that delegate to application services
- mock/: Mock/in-memory implementations for all ports (testing and development)
"""
