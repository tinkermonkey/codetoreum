---
name: review_resolver_discussion_adapter_validation
description: Review of proposed AdapterResolver.resolve_discussion_adapter() fixes for GITHUB_ORG emptiness and identity_service None-guard; establishes precedent for where each class of validation belongs
metadata:
  type: feedback
---

## Context
Reviewed two proposed fixes to `src/codetoreum/infrastructure/adapters/resolver.py::resolve_discussion_adapter()` (~line 406-453): (1) reject empty `GITHUB_ORG`, (2) guard `identity_service` before passing to `GitHubDiscussionAdapter`.

## Finding: premise for the GITHUB_ORG "silent masking" bug was stale
As of the reviewed HEAD (branch `feature/issue-943-phase-14-select-githubdiscus`, commit `0f73ab22`), empty `GITHUB_ORG` is **already** guarded twice, so the described failure mode (malformed `/repos//repo` URL → misleading 404 at runtime) does not reproduce:
1. `factory.py` registers the "github" discussion_adapter with `AdapterCredentialRequirement(env_vars=("GITHUB_TOKEN", "GITHUB_ORG"), ...)` (~line 543-554), so `validate_credentials()` (called first in `resolve_all()`) already rejects a *missing* `GITHUB_ORG`.
2. `GitHubDiscussionConfig.__post_init__` (`adapters/secondary/github_discussion_adapter.py` lines 76-87) raises `ValidationError` if `organization` is falsy — this fires inside `resolve_discussion_adapter()` during `resolve_all()` (Phase 2), and is **not** swallowed; it propagates through `ProductionApplicationBootstrap.setup()`'s outer try/except and crashes bootstrap.

The only real gap: `validate_credentials()`'s env_var check is a presence test (`env_var not in os.environ`), deliberately falsy-tolerant per its own docstring/comment (line ~156, ~195) — so `GITHUB_ORG=""` (set-but-empty) passes pre-flight and only fails later via `GitHubDiscussionConfig.__post_init__`, which raises `ValidationError` (a `ports.exceptions.PortError` subclass), **not** `AdapterConfigurationError`. That means this one specific edge case: (a) isn't part of the aggregated batch-error report `validate_credentials()` promises, (b) is caught by the generic `except Exception` branch in bootstrap instead of the dedicated `except AdapterConfigurationError` branch. Still fails fast, still logged with `exc_info=True` — just miscategorized. This is MINOR/ADVISORY, not CRITICAL.

**Lesson: verify a bug's premise against current HEAD before accepting its severity claim** — this file was touched by recent commits (`893db76a` "Fix GitHub Discussion Adapter architectural violations and error handling") that likely already closed the gap the ticket was written against.

## Precedent: where each class of resolver validation belongs
- **Generic env-var/config-key presence** → `AdapterCredentialRequirement` registered in `factory.py`, enforced by the shared `validate_credentials()` pre-flight pass. This mechanism is intentionally falsy-tolerant across all 32 slots (some slots legitimately want `0`/`False`/`""` as valid config) — do not special-case it to reject empty strings; that would be a non-local behavior change for all 32 adapter slots, not a targeted fix.
- **Adapter-specific semantic invariants** (e.g. "org must be non-empty specifically") → belongs in the adapter's own construction-time invariant (`GitHubDiscussionConfig.__post_init__` already does this correctly — it protects *any* caller, not just this resolver path). If the resolver wants this surfaced as `AdapterConfigurationError` for aggregated-error consistency, **translate the exception at the call site** (catch `ValidationError` around the `GitHubDiscussionConfig(...)` construction, re-raise as `AdapterConfigurationError`) rather than duplicating the emptiness check inline in the resolver — duplicating creates two sources of truth for the same invariant that can drift.
- **Cross-adapter resolution-order dependencies within `resolve_all()`** (e.g. "identity_service must already be in `self._resolved` before this adapter can be built") → use the `required_keys = [...]; missing = [k for k in required_keys if k not in self._resolved]; if missing: raise AdapterConfigurationError([...])` comprehension pattern. This is the dominant precedent (`resolve_repair_cycle` lines ~711-722, `resolve_container_recovery` lines ~805-816 — 2 of 3 existing examples). `resolve_coding_agent`'s manual `if ar is None or wis is None:` check (lines ~344-352) is the same idea but an older, less consistent form — prefer the comprehension pattern for new code, don't replicate the manual form.

## Confirmed valid finding: identity_service None-guard
`resolve_discussion_adapter()` passes `identity_service=self._resolved.get("identity_service")` (line ~438) with no None-check, into `GitHubDiscussionAdapter.__init__(identity_service: IIdentityService, ...)` which is non-optional and does not itself validate. Currently unreachable via the only production call path (`resolve_all()` resolves `identity_service` in step 1, `discussion_adapter` in step 5 — see resolver.py lines ~1072, ~1093), but that's an ordering *coincidence*, not an enforced invariant — exactly the class of latent bug the `required_keys`/`missing` pattern exists to prevent. Legitimate, worth fixing (MINOR — defense-in-depth/consistency, not urgent since currently unreachable).

Note: `ticket_adapter` in the same constructor call does **not** need a guard — it's genuinely `Optional[ITicketSystem] = None` in `GitHubDiscussionAdapter.__init__`, and `self._resolved.get("ticket")` returning `None` is correct, documented fallback behavior (falls back to `config.repository`).
