"""Production branch resolution adapter for intelligent branch reuse.

This adapter implements the IBranchResolutionService interface, executing a
five-step priority-ordered resolution chain to decide whether to create a new
branch or reuse an existing one for a work item.

Resolution Chain:
1. Exact match on feature/issue-{issue_id}-* pattern (confidence 1.0)
2. Parent issue lookup via ITicketSystem, check parent's branch (confidence 0.95)
3. Sibling issues - query parent's children, check for shared branch (confidence 0.9)
4. Fuzzy matching using Jaccard similarity on keywords (confidence 0.5-0.8)
5. Create new branch using _generate_branch_name() logic (confidence 1.0)

All external API calls (list_branches, get_related_items) are cached with a
configurable TTL to reduce redundant calls within a single pipeline run.
"""

import asyncio
import logging
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from codetoreum.domain.events.branch_events import (
    BranchResolutionCreatedEvent,
    BranchResolvedEvent,
    BranchReusedEvent,
)
from codetoreum.domain.value_objects import BranchResolution
from codetoreum.ports.exceptions import ExternalServiceError
from codetoreum.ports.output.branch_resolution_service import IBranchResolutionService
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.ticket_system import ITicketSystem
from codetoreum.ports.output.version_control_service import IVersionControlService

logger = logging.getLogger(__name__)


class BranchResolutionAdapter(IBranchResolutionService):
    """Production branch resolution adapter with intelligent reuse strategy.

    Implements the five-step resolution chain for determining whether to create
    a new branch or reuse an existing one. Uses caching to minimize external
    API calls during a single orchestration cycle.

    Args:
        ticket_system: ITicketSystem for querying issue relationships
        version_control: IVersionControlService for querying branches
        event_emitter: IEventEmitter for emitting resolution events
        min_confidence_threshold: Minimum confidence for fuzzy matches to be
                                 accepted. Fuzzy matches below this threshold
                                 fall through to next strategy. (default: 0.7)
        cache_ttl_seconds: TTL for list_branches cache in seconds (default: 30)

    Example:
        adapter = BranchResolutionAdapter(
            ticket_system=github_adapter,
            version_control=git_adapter,
            event_emitter=event_bus,
            min_confidence_threshold=0.7,
            cache_ttl_seconds=30
        )

        resolution = await adapter.resolve_branch(
            project_id="proj-123",
            issue_id="456",
            issue_metadata={"title": "Fix auth bug", "labels": ["bug"]}
        )

        if resolution.action == "reuse":
            print(f"Reuse: {resolution.branch_name}")
        else:
            print(f"Create: {resolution.branch_name}")
    """

    def __init__(
        self,
        ticket_system: ITicketSystem,
        version_control: IVersionControlService,
        event_emitter: IEventEmitter,
        min_confidence_threshold: float = 0.7,
        cache_ttl_seconds: int = 30,
    ) -> None:
        """Initialize the branch resolution adapter.

        Args:
            ticket_system: Ticket system adapter for issue queries
            version_control: Version control adapter for branch queries
            event_emitter: Event emitter for publishing resolution events
            min_confidence_threshold: Minimum fuzzy match confidence (0.0-1.0)
            cache_ttl_seconds: Cache TTL for list_branches results
        """
        self._ticket_system = ticket_system
        self._version_control = version_control
        self._event_emitter = event_emitter

        if not 0.0 <= min_confidence_threshold <= 1.0:
            msg = "min_confidence_threshold must be between 0.0 and 1.0"
            raise ValueError(msg)
        self._min_confidence_threshold = min_confidence_threshold
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)

        # Branch cache: {repo_identifier} -> (timestamp, [branch_names])
        self._branch_cache: dict[str, tuple[datetime, list[str]]] = {}
        self._cache_lock = asyncio.Lock()

        # Parent items cache: {issue_id} -> parent_items (for reducing duplicate API calls)
        self._parent_items_cache: dict[str, Any] = {}
        self._parent_items_lock = asyncio.Lock()

    # =========================================================================
    # IEventEmitter Implementation (Delegation)
    # =========================================================================

    def on(self, event_type: str, handler: Callable) -> None:
        """Subscribe to events (delegated to event_emitter)."""
        self._event_emitter.on(event_type, handler)

    def off(self, event_type: str, handler: Callable) -> None:
        """Unsubscribe from events (delegated to event_emitter)."""
        self._event_emitter.off(event_type, handler)

    def emit(self, event: Any) -> None:
        """Emit an event (delegated to event_emitter)."""
        self._event_emitter.emit(event)

    async def resolve_branch(
        self,
        project_id: str,
        issue_id: str,
        issue_metadata: Mapping[str, Any],
        repo_path: str,
    ) -> BranchResolution:
        """Resolve branch using five-step priority chain.

        Executes the following strategies in order:
        1. Exact match on feature/issue-{issue_id}-* (confidence 1.0)
        2. Parent issue branch (confidence 0.95)
        3. Sibling issue branch (confidence 0.9)
        4. Fuzzy keyword match (confidence 0.5-0.8)
        5. Create new branch (confidence 1.0)

        Args:
            project_id: Project identifier
            issue_id: Issue/work item identifier
            issue_metadata: Issue metadata (title, description, labels, etc.)
            repo_path: Local repository path (required for list_branches calls)

        Returns:
            BranchResolution with action, branch_name, confidence, and reason

        Raises:
            ExternalServiceError: If ticket system or version control fails
        """
        try:
            # Convert immutable mapping to dict for convenience
            metadata = dict(issue_metadata) if issue_metadata else {}

            # Clear parent items cache for this resolution call
            async with self._parent_items_lock:
                self._parent_items_cache.clear()

            # Strategy 1: Exact match
            resolution = await self._strategy_exact_match(repo_path, issue_id)
            if resolution:
                await self._emit_events(resolution, project_id, issue_id)
                return resolution

            # Strategy 2: Parent issue
            resolution = await self._strategy_parent_issue(
                repo_path, issue_id, metadata
            )
            if resolution:
                await self._emit_events(resolution, project_id, issue_id)
                return resolution

            # Strategy 3: Sibling issues
            resolution = await self._strategy_sibling_issues(
                repo_path, issue_id, metadata
            )
            if resolution:
                await self._emit_events(resolution, project_id, issue_id)
                return resolution

            # Strategy 4: Fuzzy matching
            resolution = await self._strategy_fuzzy_match(
                repo_path, issue_id, metadata
            )
            if resolution:
                await self._emit_events(resolution, project_id, issue_id)
                return resolution

            # Strategy 5: Create new branch
            resolution = await self._strategy_create_new(repo_path, issue_id, metadata)
            await self._emit_events(resolution, project_id, issue_id)
            return resolution

        except Exception as e:
            logger.exception(
                "Branch resolution failed for issue %s in project %s",
                issue_id,
                project_id,
            )
            raise ExternalServiceError("branch_resolution", f"Branch resolution failed: {e!s}") from e

    async def _strategy_exact_match(
        self, repo_path: str, issue_id: str
    ) -> BranchResolution | None:
        """Strategy 1: Exact match on feature/issue-{issue_id}-* pattern.

        Searches for branches matching the pattern feature/issue-{issue_id}-*
        (case-insensitive).

        Returns:
            BranchResolution with confidence 1.0 if found, None otherwise
        """
        try:
            branches = await self._list_branches(repo_path)

            # Look for exact pattern: feature/issue-{issue_id}-*
            pattern = f"feature/issue-{issue_id}-".lower()
            for branch in branches:
                if branch.lower().startswith(pattern):
                    return BranchResolution(
                        action="reuse",
                        branch_name=branch,
                        confidence=1.0,
                        reason=f"Exact match found for issue #{issue_id}",
                        resolution_strategy="exact_match",
                        parent_issue_id=None,
                    )
            return None

        except Exception as e:
            logger.warning(
                "Exact match strategy failed: %s", str(e), exc_info=True
            )
            return None

    async def _strategy_parent_issue(
        self,
        repo_path: str,
        issue_id: str,
        metadata: dict[str, Any],
    ) -> BranchResolution | None:
        """Strategy 2: Check parent issue for existing branch.

        Queries ITicketSystem.get_related_items(issue_id, "child-of") to find
        the parent issue, then looks for a branch matching the parent's ID.

        Returns:
            BranchResolution with confidence 0.95 if parent branch found, else None
        """
        try:
            # Get parent issue (uses cache to avoid duplicate calls)
            parent_items = await self._get_parent_items(issue_id)

            if not parent_items:
                return None

            parent_issue = parent_items[0]  # Take first parent
            parent_id = parent_issue.id

            # Look for parent's branch
            branches = await self._list_branches(repo_path)
            pattern = f"feature/issue-{parent_id}-".lower()

            for branch in branches:
                if branch.lower().startswith(pattern):
                    return BranchResolution(
                        action="reuse",
                        branch_name=branch,
                        confidence=0.95,
                        reason=f"Parent issue #{parent_id} has existing branch",
                        resolution_strategy="parent_issue",
                        parent_issue_id=parent_id,
                    )

            return None

        except Exception as e:
            logger.warning(
                "Parent issue strategy failed: %s", str(e), exc_info=True
            )
            return None

    async def _strategy_sibling_issues(
        self,
        repo_path: str,
        issue_id: str,
        metadata: dict[str, Any],
    ) -> BranchResolution | None:
        """Strategy 3: Check sibling issues for shared branch.

        First queries get_related_items(issue_id, "child-of") to find parent,
        then queries get_related_items(parent_id, "parent-of") to find siblings.
        Looks for a branch associated with any sibling.

        Returns:
            BranchResolution with confidence 0.9 if sibling branch found, else None
        """
        try:
            # Get parent issue (uses cache to avoid duplicate calls)
            parent_items = await self._get_parent_items(issue_id)

            if not parent_items:
                return None

            parent_issue = parent_items[0]
            parent_id = parent_issue.id

            # Get siblings
            sibling_items = await self._ticket_system.get_related_items(
                parent_id, relationship="parent-of"
            )

            # Skip ourselves, look for siblings with branches
            branches = await self._list_branches(repo_path)

            for sibling in sibling_items:
                if sibling.id == issue_id:
                    continue

                pattern = f"feature/issue-{sibling.id}-".lower()
                for branch in branches:
                    if branch.lower().startswith(pattern):
                        return BranchResolution(
                            action="reuse",
                            branch_name=branch,
                            confidence=0.9,
                            reason=f"Sibling issue #{sibling.id} has existing branch",
                            resolution_strategy="sibling",
                            parent_issue_id=parent_id,
                        )

            return None

        except Exception as e:
            logger.warning(
                "Sibling issue strategy failed: %s", str(e), exc_info=True
            )
            return None

    async def _strategy_fuzzy_match(
        self,
        repo_path: str,
        issue_id: str,
        metadata: dict[str, Any],
    ) -> BranchResolution | None:
        """Strategy 4: Fuzzy match using Jaccard similarity on keywords.

        Extracts keywords from issue title and description, slugifies them,
        then compares against branch names using Jaccard similarity (token overlap).
        Only accepts matches with confidence >= min_confidence_threshold.

        Returns:
            BranchResolution with confidence 0.5-0.8 if fuzzy match found above
            threshold, else None
        """
        try:
            # Extract and slugify keywords from issue metadata
            issue_keywords = self._extract_keywords(metadata)
            if not issue_keywords:
                return None

            branches = await self._list_branches(repo_path)

            best_match = None
            best_similarity = 0.0

            for branch in branches:
                # Skip exact pattern branches (already handled by strategy 1)
                if self._is_exact_pattern_branch(branch, issue_id):
                    continue

                branch_keywords = self._extract_branch_keywords(branch)
                similarity = self._jaccard_similarity(issue_keywords, branch_keywords)

                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = branch

            # Only return if above threshold
            if best_match and best_similarity >= self._min_confidence_threshold:
                # Confidence maps similarity to 0.5-0.8 range
                confidence = 0.5 + (best_similarity * 0.3)
                return BranchResolution(
                    action="reuse",
                    branch_name=best_match,
                    confidence=min(0.8, confidence),  # Cap at 0.8
                    reason=f"Fuzzy match on branch keywords (similarity: {best_similarity:.2f})",
                    resolution_strategy="fuzzy",
                    parent_issue_id=None,
                )

            return None

        except Exception as e:
            logger.warning(
                "Fuzzy match strategy failed: %s", str(e), exc_info=True
            )
            return None

    async def _strategy_create_new(
        self,
        repo_path: str,
        issue_id: str,
        metadata: dict[str, Any],
    ) -> BranchResolution:
        """Strategy 5: Create new branch.

        Falls back to creating a new branch using _generate_branch_name() logic.
        This is always successful with confidence 1.0.

        Returns:
            BranchResolution with action="create" and confidence 1.0
        """
        branch_name = self._generate_branch_name(issue_id, metadata)

        return BranchResolution(
            action="create",
            branch_name=branch_name,
            confidence=1.0,
            reason="No existing branch found, creating new",
            resolution_strategy="new",
            parent_issue_id=None,
        )

    async def _emit_events(
        self, resolution: BranchResolution, project_id: str, issue_id: str
    ) -> None:
        """Emit resolution and outcome-specific events.

        Emits:
        1. BranchResolvedEvent (primary audit event)
        2. BranchReusedEvent (if action="reuse") or BranchResolutionCreatedEvent
           (if action="create")

        Args:
            resolution: The resolution result
            project_id: Project identifier
            issue_id: Issue identifier
        """
        now = datetime.now(UTC)
        timestamp = now.isoformat()

        # Primary audit event
        resolved_event = BranchResolvedEvent(
            type="branch.resolved",
            timestamp=timestamp,
            source="branch_resolution",
            project_id=project_id,
            issue_id=issue_id,
            action=resolution.action,
            branch_name=resolution.branch_name,
            confidence=resolution.confidence,
            reason=resolution.reason,
            parent_issue_id=resolution.parent_issue_id,
            resolution_strategy=resolution.resolution_strategy,
        )
        self.emit(resolved_event)

        # Outcome-specific event
        if resolution.action == "reuse":
            outcome_event = BranchReusedEvent(
                type="branch.reused",
                timestamp=timestamp,
                source="branch_resolution",
                project_id=project_id,
                issue_id=issue_id,
                branch_name=resolution.branch_name,
                confidence=resolution.confidence,
                reason=resolution.reason,
                parent_issue_id=resolution.parent_issue_id,
                resolution_strategy=resolution.resolution_strategy,
            )
        else:
            outcome_event = BranchResolutionCreatedEvent(
                type="branch.created",
                timestamp=timestamp,
                source="branch_resolution",
                project_id=project_id,
                issue_id=issue_id,
                branch_name=resolution.branch_name,
                reason=resolution.reason,
            )

        self.emit(outcome_event)

    async def _get_parent_items(self, issue_id: str) -> Any:
        """Get parent items for an issue with caching within a resolve_branch call.

        Caches the result to avoid duplicate API calls when multiple strategies
        need the parent issue (e.g., parent_issue strategy and sibling_issues strategy).

        Args:
            issue_id: Issue identifier

        Returns:
            Parent items list from get_related_items
        """
        async with self._parent_items_lock:
            # Check cache first
            if issue_id in self._parent_items_cache:
                return self._parent_items_cache[issue_id]

            # Fetch parent items (with lock held to prevent duplicate calls)
            parent_items = await self._ticket_system.get_related_items(
                issue_id, relationship="child-of"
            )

            # Cache result (still holding lock)
            self._parent_items_cache[issue_id] = parent_items

        return parent_items

    async def _list_branches(self, repo_path: str) -> list[str]:
        """Get list of branches with caching.

        Caches results for cache_ttl_seconds to reduce redundant API calls
        within a single pipeline run.

        Args:
            repo_path: Local repository path

        Returns:
            List of branch names (without remote prefix)
        """
        async with self._cache_lock:
            now = datetime.now(UTC)

            # Check cache first
            if repo_path in self._branch_cache:
                timestamp, branches = self._branch_cache[repo_path]
                if now - timestamp < self._cache_ttl:
                    return list(branches)

            # Fetch fresh branches (with lock held to prevent duplicate calls)
            branches = await self._version_control.list_branches(repo_path, remote=True)

            # Cache result (still holding lock)
            self._branch_cache[repo_path] = (datetime.now(UTC), branches)

        return branches

    def _extract_keywords(self, metadata: dict[str, Any]) -> set[str]:
        """Extract and slugify keywords from issue metadata.

        Processes title and description, extracting tokens and slugifying them.
        Slugification converts to lowercase and replaces non-alphanumeric chars
        with hyphens.

        Args:
            metadata: Issue metadata dict

        Returns:
            Set of slugified keywords
        """
        keywords = set()

        # Extract from title
        if title := metadata.get("title", ""):
            keywords.update(self._slugify(title))

        # Extract from description
        if description := metadata.get("description", ""):
            keywords.update(self._slugify(description))

        # Extract from labels
        if labels := metadata.get("labels"):
            for label in labels:
                if isinstance(label, str):
                    keywords.update(self._slugify(label))

        return keywords

    def _extract_branch_keywords(self, branch_name: str) -> set[str]:
        """Extract keywords from branch name.

        Splits on common separators and slugifies tokens.

        Args:
            branch_name: Branch name (e.g., "feature/issue-123-fix-auth-bug")

        Returns:
            Set of slugified keywords from branch name
        """
        # Remove prefix (feature/, bugfix/, etc.)
        name = branch_name.rsplit("/", maxsplit=1)[-1] if "/" in branch_name else branch_name

        # Split on common separators
        keywords = set()
        for token in re.split(r"[-_]", name):
            if token and token not in ("feature", "issue"):
                keywords.add(token.lower())

        return keywords

    def _jaccard_similarity(self, set_a: set[str], set_b: set[str]) -> float:
        """Calculate Jaccard similarity (token overlap).

        Jaccard = |A ∩ B| / |A ∪ B|

        Args:
            set_a: First set of tokens
            set_b: Second set of tokens

        Returns:
            Similarity score from 0.0 to 1.0
        """
        if not set_a or not set_b:
            return 0.0

        intersection = len(set_a & set_b)
        union = len(set_a | set_b)

        return intersection / union if union > 0 else 0.0

    def _slugify(self, text: str) -> set[str]:
        """Convert text to slugified tokens.

        Converts to lowercase, splits on non-alphanumeric chars, filters
        empty tokens.

        Args:
            text: Input text

        Returns:
            Set of slugified tokens
        """
        # Convert to lowercase and replace non-alphanumeric with spaces
        normalized = re.sub(r"[^a-z0-9]+", " ", text.lower())

        # Split and filter empty tokens
        tokens = {token for token in normalized.split() if token}

        return tokens

    def _is_exact_pattern_branch(self, branch: str, issue_id: str) -> bool:
        """Check if branch matches exact pattern for issue.

        Args:
            branch: Branch name
            issue_id: Issue ID

        Returns:
            True if branch matches feature/issue-{issue_id}-* pattern
        """
        pattern = f"feature/issue-{issue_id}-".lower()
        return branch.lower().startswith(pattern)

    def _generate_branch_name(
        self, issue_id: str, metadata: dict[str, Any]
    ) -> str:
        """Generate a new branch name.

        Creates feature/issue-{issue_id}-{slugified-title} branch name.
        Falls back to feature/issue-{issue_id}-branch if title unavailable.

        Args:
            issue_id: Issue ID
            metadata: Issue metadata

        Returns:
            Generated branch name
        """
        # Get title
        title = metadata.get("title", "")

        if title:
            # Slugify title: lowercase, remove special chars, replace spaces/hyphens
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")

            # Limit length to reasonable size
            slug = slug[:50] if len(slug) > 50 else slug

            # Clean up trailing hyphens
            slug = slug.rstrip("-")

            return f"feature/issue-{issue_id}-{slug}" if slug else f"feature/issue-{issue_id}"

        return f"feature/issue-{issue_id}"
