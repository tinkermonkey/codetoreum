"""Integration tests for FeedbackProcessor."""

import pytest

from codetoreum.application.feedback_processor import (
    FeedbackProcessor,
    FeedbackType,
    ParsedFeedback,
    ParsedIssue,
    Severity,
)
from codetoreum.domain.review_cycle import ReviewDecision


# Fixtures


@pytest.fixture
def feedback_processor():
    """Create FeedbackProcessor instance."""
    return FeedbackProcessor()


# Test data


APPROVAL_REVIEW = """
## Summary
The code looks good and follows best practices.

[APPROVED]

No issues found. The implementation is clean and well-documented.
"""

ISSUES_REVIEW = """
## Summary
Found several issues that need to be addressed.

## Issues
1. [Missing Type Hints]: Function `calculate` in file.py:42 lacks type annotations
2. [Security Vulnerability]: SQL injection risk in database.py:123
3. [Performance Issue]: Inefficient loop in process.py line 56

## Suggestions
- Add comprehensive docstrings
- Consider using type hints throughout
"""

ESCALATION_REVIEW = """
## Summary
This requires human review due to architectural concerns.

[ESCALATE]

The proposed changes would significantly impact the system architecture.
I recommend escalating this to a senior developer for review.
"""

MIXED_REVIEW = """
## Summary
Some good improvements, but a few critical issues remain.

## Issues
1. **Critical Security Issue**: XSS vulnerability in render.py:89
2. Minor style issue: Consider using f-strings

## Suggestions
1. Add input validation
2. Improve error handling
3. Add unit tests
"""


# Tests


@pytest.mark.asyncio
async def test_parse_approval_review(feedback_processor):
    """Test parsing an approval review."""
    result = await feedback_processor.parse_review_output(APPROVAL_REVIEW)

    assert result.success
    assert result.parsed_feedback is not None

    feedback = result.parsed_feedback
    assert feedback.decision == ReviewDecision.APPROVE
    assert "looks good" in feedback.comment.lower()
    assert len(feedback.issues) == 0
    assert feedback.summary is not None


@pytest.mark.asyncio
async def test_parse_issues_review(feedback_processor):
    """Test parsing a review with issues."""
    result = await feedback_processor.parse_review_output(ISSUES_REVIEW)

    assert result.success
    assert result.parsed_feedback is not None

    feedback = result.parsed_feedback
    assert feedback.decision == ReviewDecision.REQUEST_CHANGES
    assert len(feedback.issues) == 3
    assert len(feedback.suggestions) == 2

    # Check first issue
    issue1 = feedback.issues[0]
    assert issue1.title == "Missing Type Hints"
    assert "calculate" in issue1.description
    assert issue1.file_path == "file.py"
    assert issue1.line_number == 42

    # Check second issue (security)
    issue2 = feedback.issues[1]
    assert issue2.title == "Security Vulnerability"
    assert issue2.severity == Severity.CRITICAL
    assert issue2.file_path == "database.py"
    assert issue2.line_number == 123

    # Check third issue
    issue3 = feedback.issues[2]
    assert issue3.title == "Performance Issue"
    assert "process.py" in issue3.description


@pytest.mark.asyncio
async def test_parse_escalation_review(feedback_processor):
    """Test parsing an escalation review."""
    result = await feedback_processor.parse_review_output(ESCALATION_REVIEW)

    assert result.success
    assert result.parsed_feedback is not None

    feedback = result.parsed_feedback
    assert feedback.decision == ReviewDecision.ESCALATE
    assert "human review" in feedback.comment.lower() or "escalat" in feedback.comment.lower()


@pytest.mark.asyncio
async def test_parse_mixed_review(feedback_processor):
    """Test parsing a review with mixed severity issues."""
    result = await feedback_processor.parse_review_output(MIXED_REVIEW)

    assert result.success
    assert result.parsed_feedback is not None

    feedback = result.parsed_feedback
    assert feedback.decision == ReviewDecision.REQUEST_CHANGES
    assert len(feedback.issues) == 2
    assert len(feedback.suggestions) == 3

    # Check critical issue
    critical_issue = feedback.issues[0]
    assert critical_issue.severity == Severity.CRITICAL
    assert "XSS" in critical_issue.title or "Security" in critical_issue.title


@pytest.mark.asyncio
async def test_extract_actionable_items(feedback_processor):
    """Test extracting actionable items from feedback."""
    # First parse the review
    parse_result = await feedback_processor.parse_review_output(ISSUES_REVIEW)
    parsed_feedback = parse_result.parsed_feedback

    # Extract actionable items
    result = await feedback_processor.extract_actionable_items(parsed_feedback)

    assert result.success
    assert len(result.actionable_items) > 0

    # Should have items from both issues and suggestions
    # 3 issues + 2 suggestions = 5 total
    assert len(result.actionable_items) == 5

    # Check that items are sorted by priority
    priorities = [item.priority for item in result.actionable_items]
    assert priorities == sorted(priorities)

    # Check for critical item (security vulnerability should be priority 1)
    has_critical = any(item.priority == 1 for item in result.actionable_items)
    assert has_critical

    # Should create work items for critical issues
    assert result.should_create_work_items


@pytest.mark.asyncio
async def test_detect_approval_decision(feedback_processor):
    """Test detecting approval decision."""
    test_cases = [
        ("[APPROVED] Looks good", ReviewDecision.APPROVE),
        ("LGTM - everything works", ReviewDecision.APPROVE),
        ("Looks good to me!", ReviewDecision.APPROVE),
        ("No issues found", ReviewDecision.APPROVE),
    ]

    for review_text, expected_decision in test_cases:
        decision = feedback_processor._detect_decision(review_text)
        assert decision == expected_decision, f"Failed for: {review_text}"


@pytest.mark.asyncio
async def test_detect_request_changes_decision(feedback_processor):
    """Test detecting request changes decision."""
    test_cases = [
        ("## Issues\n1. Fix this bug", ReviewDecision.REQUEST_CHANGES),
        ("Found an error in the code", ReviewDecision.REQUEST_CHANGES),
        ("There's a problem with the implementation", ReviewDecision.REQUEST_CHANGES),
    ]

    for review_text, expected_decision in test_cases:
        decision = feedback_processor._detect_decision(review_text)
        assert decision == expected_decision, f"Failed for: {review_text}"


@pytest.mark.asyncio
async def test_detect_escalation_decision(feedback_processor):
    """Test detecting escalation decision."""
    test_cases = [
        ("[ESCALATE] Needs human review", ReviewDecision.ESCALATE),
        ("This should be escalated to senior dev", ReviewDecision.ESCALATE),
        ("Requires manual review", ReviewDecision.ESCALATE),
    ]

    for review_text, expected_decision in test_cases:
        decision = feedback_processor._detect_decision(review_text)
        assert decision == expected_decision, f"Failed for: {review_text}"


@pytest.mark.asyncio
async def test_infer_severity(feedback_processor):
    """Test severity inference."""
    test_cases = [
        ("Critical security vulnerability", Severity.CRITICAL),
        ("Security issue found", Severity.CRITICAL),
        ("Error in function", Severity.HIGH),
        ("Bug causing failures", Severity.HIGH),
        ("Warning: consider refactoring", Severity.MEDIUM),
        ("Minor style issue", Severity.LOW),
        ("Note: you might want to add docs", Severity.INFO),
    ]

    for description, expected_severity in test_cases:
        severity = feedback_processor._infer_severity(description)
        assert severity == expected_severity, f"Failed for: {description}"


@pytest.mark.asyncio
async def test_extract_location(feedback_processor):
    """Test extracting file location from description."""
    test_cases = [
        ("Error in file.py:123", ("file.py", 123)),
        ("Bug in src/utils.py:45", ("src/utils.py", 45)),
        ("Issue in module.py line 78", ("module.py", 78)),
        ("Problem in path/to/file.py:100", ("path/to/file.py", 100)),
        ("Generic issue", (None, None)),
    ]

    for description, expected_location in test_cases:
        file_path, line_number = feedback_processor._extract_location(description)
        assert (file_path, line_number) == expected_location, f"Failed for: {description}"


@pytest.mark.asyncio
async def test_format_feedback_for_maker(feedback_processor):
    """Test formatting feedback for maker agent."""
    # Parse a review
    parse_result = await feedback_processor.parse_review_output(ISSUES_REVIEW)
    parsed_feedback = parse_result.parsed_feedback

    # Format for maker
    formatted = feedback_processor.format_feedback_for_maker(parsed_feedback)

    assert "## Review Summary" in formatted
    assert "**Decision**:" in formatted
    assert "## Issues to Address" in formatted
    assert "## Suggestions" in formatted
    assert "Missing Type Hints" in formatted
    assert "file.py:42" in formatted


@pytest.mark.asyncio
async def test_severity_to_priority(feedback_processor):
    """Test severity to priority conversion."""
    assert feedback_processor._severity_to_priority(Severity.CRITICAL) == 1
    assert feedback_processor._severity_to_priority(Severity.HIGH) == 2
    assert feedback_processor._severity_to_priority(Severity.MEDIUM) == 3
    assert feedback_processor._severity_to_priority(Severity.LOW) == 4
    assert feedback_processor._severity_to_priority(Severity.INFO) == 5


@pytest.mark.asyncio
async def test_actionable_items_prioritization(feedback_processor):
    """Test that actionable items are properly prioritized."""
    review_with_mixed_severity = """
## Issues
1. [Critical Bug]: Security vulnerability in auth.py:10
2. [Minor Issue]: Code style in utils.py:20
3. [High Priority]: Data validation missing in api.py:30

## Suggestions
- Add more tests
"""

    parse_result = await feedback_processor.parse_review_output(
        review_with_mixed_severity
    )
    parsed_feedback = parse_result.parsed_feedback

    result = await feedback_processor.extract_actionable_items(parsed_feedback)

    # Should have 3 issues + 1 suggestion
    assert len(result.actionable_items) == 4

    # First item should be critical (priority 1)
    assert result.actionable_items[0].priority == 1
    assert "Critical" in result.actionable_items[0].description or "Security" in result.actionable_items[0].description

    # Should create work items due to critical issue
    assert result.should_create_work_items


@pytest.mark.asyncio
async def test_empty_review(feedback_processor):
    """Test parsing an empty review."""
    result = await feedback_processor.parse_review_output("")

    assert result.success
    assert result.parsed_feedback is not None
    # Empty review should default to approve
    assert result.parsed_feedback.decision == ReviewDecision.APPROVE


@pytest.mark.asyncio
async def test_malformed_review(feedback_processor):
    """Test handling malformed review gracefully."""
    malformed_review = """
This is just some random text
with no structure at all
@@@@####
"""

    result = await feedback_processor.parse_review_output(malformed_review)

    # Should still parse successfully, defaulting to reasonable values
    assert result.success
    assert result.parsed_feedback is not None
    assert result.parsed_feedback.decision in [
        ReviewDecision.APPROVE,
        ReviewDecision.REQUEST_CHANGES,
    ]


@pytest.mark.asyncio
async def test_numbered_list_parsing(feedback_processor):
    """Test parsing numbered issue lists."""
    review = """
## Issues
1. [First Issue]: Description 1
2. [Second Issue]: Description 2
3. [Third Issue]: Description 3
"""

    result = await feedback_processor.parse_review_output(review)

    assert result.success
    assert len(result.parsed_feedback.issues) == 3
    assert result.parsed_feedback.issues[0].title == "First Issue"
    assert result.parsed_feedback.issues[1].title == "Second Issue"
    assert result.parsed_feedback.issues[2].title == "Third Issue"


@pytest.mark.asyncio
async def test_bulleted_list_parsing(feedback_processor):
    """Test parsing bulleted issue lists."""
    review = """
## Issues
- [First Issue]: Description 1
- [Second Issue]: Description 2
* [Third Issue]: Description 3
"""

    result = await feedback_processor.parse_review_output(review)

    assert result.success
    assert len(result.parsed_feedback.issues) == 3


@pytest.mark.asyncio
async def test_extract_suggestions_various_formats(feedback_processor):
    """Test extracting suggestions in various formats."""
    review = """
## Suggestions
1. First suggestion
2. Second suggestion
- Third suggestion
* Fourth suggestion
Plain text suggestion
"""

    result = await feedback_processor.parse_review_output(review)

    assert result.success
    # Should extract all suggestions regardless of format
    assert len(result.parsed_feedback.suggestions) >= 3
