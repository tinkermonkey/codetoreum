# Codetoreum Architect Memory Index

- [GitHubVersionControlAdapter review and fixes](review_github_version_control_adapter.md) — CRITICAL bug (wrong method name status vs get_status), MAJOR violation (raw subprocess in adapter), and doc gap corrected
- [MPO/container/auth bootstrap fixes](project_mpo_container_auth_fixes.md) — DEF-004 MPO not started, DEF-DOC-002 requires_docker was false, DEF-DOC-003 auth undocumented+missing from curl calls
- [ExecutionState typed port review](review_execution_state_tracker_typed_port.md) — approved typed ExecutionState dataclass; found live broken import in InMemoryWorkExecutionStateTracker anticipating the fix
- [resolve_discussion_adapter validation review](review_resolver_discussion_adapter_validation.md) — GITHUB_ORG empty-string bug premise was stale (already double-guarded); identity_service None-guard confirmed valid; establishes precedent for where each validation class belongs
