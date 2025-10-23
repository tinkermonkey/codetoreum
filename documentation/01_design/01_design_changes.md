# Design Changes

## New capabilities

- The ability to manage environment variables at the project level.
  - Web UI to add/edit/delete environment variables for a project, storage TBD

- The ability to mount commands and sub-agents into project agents.
  - Web UI to select which commands and sub-agents to mount into the project agent.

## Agent Containers

Update the agent design with the following interface changes.

### General Purpose Containerized Agents

- The general purpose containerized agents will NOT have access to:
  - git credentials or mounts
  - github credentials, app keys or mounts
  - ssh keys
  - docker socket or mounts

- The general purpose containerized agents will have access to:
  - internet access (for downloading dependencies, accessing APIs, etc.)
  - mounted project files (the files in the project repository), read/write or read-only based on configuration
  - environment variables defined at the project level
  - mounted commands and sub-agents defined at the project level
  - mounted mcp config and credentials for accessing MCP services (e.g., artifact storage, logging, etc.)
  - mounted request + context data (issues, pull requests, code snippets, etc.)

- Fundamentally change the way that the general purpose containerized agents receive context
  - Instead of passing in prompts combined with context, store the context in files that are mounted into the container
  - Pass in a reference to the context files in the prompt (e.g., "See the file /context/issue.txt for the issue description.")
  - This allows for much larger context to be passed to the agent without hitting token limits
  - This also allows for more complex context to be passed to the agent (e.g., multiple files, directories, etc.)

**Implications:**

- The Orchestrator will be responsible for managing git operations (clone, pull, push, etc.) and branch selection and will provide the necessary project files to the general purpose containerized agents, with the correct branch checked out.

- The Orchestrator will be responsible for collecting all context needed for the agent to perform its tasks, including issues, pull requests, code snippets, etc., and providing that context to the general purpose containerized agents.
