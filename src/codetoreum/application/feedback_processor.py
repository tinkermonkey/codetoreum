"""Feedback Processor application service."""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from codetoreum.domain.review_cycle import ReviewDecision

logger = logging.getLogger(__name__)


class FeedbackType(Enum):
    """Type of feedback detected."""

    APPROVAL = "approval"
    ISSUES_FOUND = "issues_found"
    SUGGESTIONS = "suggestions"
    ESCALATION = "escalation"
    MIXED = "mixed"


class Severity(Enum):
    """Severity level for issues."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class ParsedIssue:
    """Parsed issue from review feedback."""

    title: str
    description: str
    severity: Severity
    line_number: Optional[int] = None
    file_path: Optional[str] = None


@dataclass
class ParsedFeedback:
    """Structured feedback parsed from review output."""

    decision: ReviewDecision
    comment: str
    issues: List[ParsedIssue]
    suggestions: List[str]
    summary: Optional[str] = None
    raw_output: str = ""


@dataclass
class ActionableItem:
    """Actionable item extracted from feedback."""

    type: str  # 'fix', 'improve', 'investigate'
    description: str
    priority: int  # 1-5, where 1 is highest
    related_issue: Optional[ParsedIssue] = None


@dataclass
class FeedbackProcessingResult:
    """Result from feedback processing."""

    success: bool
    parsed_feedback: Optional[ParsedFeedback] = None
    actionable_items: List[ActionableItem] = None
    should_create_work_items: bool = False
    error: Optional[str] = None


class FeedbackProcessor:
    """
    Application service for processing review feedback.

    Responsibilities:
    - Parse review feedback into structured data
    - Extract actionable items from feedback
    - Determine if new work items should be created
    - Classify feedback severity and priority
    """

    def __init__(self):
        """Initialize FeedbackProcessor."""
        # Patterns for detecting approval
        self.approval_patterns = [
            r"\[APPROVED\]",
            r"LGTM",
            r"looks?\s+good",
            r"approved?",
            r"no\s+issues?\s+found",
        ]

        # Patterns for detecting escalation
        self.escalation_patterns = [
            r"\[ESCALATE\]",
            r"escalat(e|ing)",
            r"needs?\s+human\s+review",
            r"requires?\s+manual\s+review",
        ]

        # Severity keywords
        self.severity_keywords = {
            Severity.CRITICAL: [
                "critical",
                "blocker",
                "security",
                "vulnerability",
                "broken",
                "injection",
                "xss",
                "csrf",
            ],
            Severity.HIGH: ["error", "bug", "fails?", "incorrect", "wrong"],
            Severity.MEDIUM: ["warning", "improvement", "should", "consider"],
            Severity.LOW: ["minor", "nitpick", "style", "formatting"],
            Severity.INFO: ["note", "info", "fyi", "suggestion"],
        }

    async def parse_review_output(
        self, review_output: str
    ) -> FeedbackProcessingResult:
        """
        Parse reviewer output into structured feedback.

        Args:
            review_output: Raw output from reviewer agent

        Returns:
            FeedbackProcessingResult with parsed feedback
        """
        try:
            # Detect decision
            decision = self._detect_decision(review_output)

            # Extract summary
            summary = self._extract_section(review_output, "Summary")

            # Extract issues
            issues = self._extract_issues(review_output)

            # Extract suggestions
            suggestions = self._extract_suggestions(review_output)

            # Build comment from summary or first few lines
            comment = summary or self._extract_comment(review_output)

            parsed_feedback = ParsedFeedback(
                decision=decision,
                comment=comment,
                issues=issues,
                suggestions=suggestions,
                summary=summary,
                raw_output=review_output,
            )

            logger.info(
                f"Parsed review feedback: decision={decision.value}, "
                f"issues={len(issues)}, suggestions={len(suggestions)}"
            )

            return FeedbackProcessingResult(
                success=True,
                parsed_feedback=parsed_feedback,
                actionable_items=[],
            )

        except Exception as e:
            logger.error(f"Failed to parse review output: {e}")
            return FeedbackProcessingResult(
                success=False,
                error=str(e),
            )

    async def extract_actionable_items(
        self, parsed_feedback: ParsedFeedback
    ) -> FeedbackProcessingResult:
        """
        Extract actionable items from parsed feedback.

        Args:
            parsed_feedback: Parsed feedback structure

        Returns:
            FeedbackProcessingResult with actionable items
        """
        try:
            actionable_items: List[ActionableItem] = []

            # Convert issues to actionable items
            for issue in parsed_feedback.issues:
                priority = self._severity_to_priority(issue.severity)

                actionable_items.append(
                    ActionableItem(
                        type="fix",
                        description=f"{issue.title}: {issue.description}",
                        priority=priority,
                        related_issue=issue,
                    )
                )

            # Convert suggestions to actionable items
            for suggestion in parsed_feedback.suggestions:
                actionable_items.append(
                    ActionableItem(
                        type="improve",
                        description=suggestion,
                        priority=3,  # Medium priority for suggestions
                    )
                )

            # Sort by priority (ascending, so 1 = highest priority first)
            actionable_items.sort(key=lambda x: x.priority)

            # Determine if should create work items
            # Create work items for critical/high severity issues
            should_create = any(
                item.priority <= 2 for item in actionable_items
            )

            logger.info(
                f"Extracted {len(actionable_items)} actionable items, "
                f"should_create_work_items={should_create}"
            )

            return FeedbackProcessingResult(
                success=True,
                parsed_feedback=parsed_feedback,
                actionable_items=actionable_items,
                should_create_work_items=should_create,
            )

        except Exception as e:
            logger.error(f"Failed to extract actionable items: {e}")
            return FeedbackProcessingResult(
                success=False,
                parsed_feedback=parsed_feedback,
                error=str(e),
            )

    def _detect_decision(self, review_output: str) -> ReviewDecision:
        """
        Detect reviewer's decision from output.

        Args:
            review_output: Raw review output

        Returns:
            ReviewDecision enum value
        """
        output_lower = review_output.lower()

        # Check for approval
        for pattern in self.approval_patterns:
            if re.search(pattern, output_lower, re.IGNORECASE):
                return ReviewDecision.APPROVE

        # Check for escalation
        for pattern in self.escalation_patterns:
            if re.search(pattern, output_lower, re.IGNORECASE):
                return ReviewDecision.ESCALATE

        # Check for issues section
        if "## issues" in output_lower or "# issues" in output_lower:
            return ReviewDecision.REQUEST_CHANGES

        # Default to request changes if contains error/bug keywords
        if any(
            keyword in output_lower
            for keyword in ["error", "bug", "issue", "problem", "incorrect"]
        ):
            return ReviewDecision.REQUEST_CHANGES

        # Default to approve if no issues detected
        return ReviewDecision.APPROVE

    def _extract_section(self, text: str, section_name: str) -> Optional[str]:
        """
        Extract content from a markdown section.

        Args:
            text: Text to search
            section_name: Section header name (without ##)

        Returns:
            Section content or None
        """
        # Match ## Section or # Section
        pattern = rf"#+\s+{re.escape(section_name)}\s*\n(.*?)(?=\n#+\s+|\Z)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)

        if match:
            return match.group(1).strip()

        return None

    def _extract_issues(self, review_output: str) -> List[ParsedIssue]:
        """
        Extract issues from review output.

        Looks for "## Issues" section and parses issue list.

        Expected formats:
        - "1. [Issue Title]: Description"
        - "- [Issue Title]: Description"
        - "* Issue Title: Description"

        Args:
            review_output: Raw review output

        Returns:
            List of ParsedIssue objects
        """
        issues: List[ParsedIssue] = []

        issues_section = self._extract_section(review_output, "Issues")
        if not issues_section:
            return issues

        # Parse numbered or bulleted lists
        # Pattern: "1. [Title]: Description" or "- [Title]: Description"
        patterns = [
            r"^\d+\.\s*\[([^\]]+)\]:\s*(.+)$",  # Numbered with brackets
            r"^[\-\*]\s*\[([^\]]+)\]:\s*(.+)$",  # Bulleted with brackets
            r"^\d+\.\s*([^:]+):\s*(.+)$",  # Numbered without brackets
            r"^[\-\*]\s*([^:]+):\s*(.+)$",  # Bulleted without brackets
        ]

        for line in issues_section.split("\n"):
            line = line.strip()
            if not line:
                continue

            for pattern in patterns:
                match = re.match(pattern, line)
                if match:
                    title = match.group(1).strip()
                    description = match.group(2).strip()

                    # Infer severity from description
                    severity = self._infer_severity(description)

                    # Try to extract file and line number
                    file_path, line_number = self._extract_location(description)

                    issues.append(
                        ParsedIssue(
                            title=title,
                            description=description,
                            severity=severity,
                            file_path=file_path,
                            line_number=line_number,
                        )
                    )
                    break

        return issues

    def _extract_suggestions(self, review_output: str) -> List[str]:
        """
        Extract suggestions from review output.

        Looks for "## Suggestions" section and parses suggestion list.

        Args:
            review_output: Raw review output

        Returns:
            List of suggestion strings
        """
        suggestions: List[str] = []

        suggestions_section = self._extract_section(review_output, "Suggestions")
        if not suggestions_section:
            return suggestions

        # Parse numbered or bulleted lists
        pattern = r"^[\d\-\*]+\.?\s*(.+)$"

        for line in suggestions_section.split("\n"):
            line = line.strip()
            if not line:
                continue

            match = re.match(pattern, line)
            if match:
                suggestions.append(match.group(1).strip())
            elif line:  # Add non-empty lines that don't match pattern
                suggestions.append(line)

        return suggestions

    def _extract_comment(self, review_output: str) -> str:
        """
        Extract comment from review output.

        Takes first non-header paragraph as comment.

        Args:
            review_output: Raw review output

        Returns:
            Comment string
        """
        lines = review_output.split("\n")

        comment_lines = []
        for line in lines:
            line = line.strip()

            # Skip headers
            if line.startswith("#"):
                continue

            # Skip special markers
            if line.startswith("["):
                continue

            # Add non-empty lines
            if line:
                comment_lines.append(line)

            # Stop after first paragraph
            if len(comment_lines) > 0 and not line:
                break

        # Return first 3 lines max
        return " ".join(comment_lines[:3]) if comment_lines else "Review completed"

    def _infer_severity(self, text: str) -> Severity:
        """
        Infer severity level from text.

        Args:
            text: Text to analyze

        Returns:
            Severity enum value
        """
        text_lower = text.lower()

        # Check each severity level
        for severity, keywords in self.severity_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                return severity

        # Default to medium
        return Severity.MEDIUM

    def _extract_location(self, description: str) -> tuple[Optional[str], Optional[int]]:
        """
        Extract file path and line number from description.

        Looks for patterns like:
        - "in file.py:123"
        - "file.py line 123"
        - "file.py:123"

        Args:
            description: Issue description

        Returns:
            Tuple of (file_path, line_number) or (None, None)
        """
        # Pattern: "path/to/file.py:123" or "file.py line 123"
        patterns = [
            r"([a-zA-Z0-9_/\.\-]+\.py):(\d+)",  # file.py:123
            r"([a-zA-Z0-9_/\.\-]+\.py)\s+line\s+(\d+)",  # file.py line 123
            r"in\s+([a-zA-Z0-9_/\.\-]+\.py):(\d+)",  # in file.py:123
        ]

        for pattern in patterns:
            match = re.search(pattern, description)
            if match:
                return match.group(1), int(match.group(2))

        return None, None

    def _severity_to_priority(self, severity: Severity) -> int:
        """
        Convert severity to priority (1-5).

        Args:
            severity: Severity level

        Returns:
            Priority integer (1=highest, 5=lowest)
        """
        severity_to_priority_map = {
            Severity.CRITICAL: 1,
            Severity.HIGH: 2,
            Severity.MEDIUM: 3,
            Severity.LOW: 4,
            Severity.INFO: 5,
        }

        return severity_to_priority_map.get(severity, 3)

    def format_feedback_for_maker(
        self, parsed_feedback: ParsedFeedback
    ) -> str:
        """
        Format parsed feedback for presentation to maker agent.

        Args:
            parsed_feedback: Parsed feedback structure

        Returns:
            Formatted feedback string
        """
        lines = []

        # Add summary
        if parsed_feedback.summary:
            lines.append("## Review Summary")
            lines.append(parsed_feedback.summary)
            lines.append("")

        # Add decision
        lines.append(f"**Decision**: {parsed_feedback.decision.value.upper()}")
        lines.append("")

        # Add issues if any
        if parsed_feedback.issues:
            lines.append("## Issues to Address")
            for i, issue in enumerate(parsed_feedback.issues, 1):
                location = ""
                if issue.file_path:
                    location = f" ({issue.file_path}"
                    if issue.line_number:
                        location += f":{issue.line_number}"
                    location += ")"

                lines.append(
                    f"{i}. **{issue.title}** [{issue.severity.value}]{location}"
                )
                lines.append(f"   {issue.description}")
                lines.append("")

        # Add suggestions if any
        if parsed_feedback.suggestions:
            lines.append("## Suggestions")
            for i, suggestion in enumerate(parsed_feedback.suggestions, 1):
                lines.append(f"{i}. {suggestion}")
            lines.append("")

        return "\n".join(lines)
