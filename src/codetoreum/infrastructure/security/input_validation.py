"""
Input validation and sanitization utilities.

This module provides security functions to prevent common vulnerabilities:
- Path traversal attacks
- SQL injection (via parameterized queries)
- File upload validation
- Input sanitization
"""

import os
import re
from pathlib import Path
from typing import List, Optional, Set

from fastapi import HTTPException, UploadFile

# File upload limits
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_CONTENT_TYPES = {
    'application/json',
    'application/yaml',
    'application/x-yaml',
    'text/plain',
    'text/yaml',
}

# Input validation patterns
SAFE_FILENAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\.]+$')
SAFE_ENV_VAR_NAME_PATTERN = re.compile(r'^[A-Z][A-Z0-9_]*$')
SAFE_AGENT_NAME_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')
SAFE_LABEL_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\.:/]+$')


class PathTraversalError(Exception):
    """Raised when path traversal attempt is detected."""
    pass


class InvalidInputError(Exception):
    """Raised when invalid input is detected."""
    pass


def safe_path_join(base_path: str, user_path: str) -> Path:
    """
    Safely join paths preventing traversal attacks.

    Args:
        base_path: The base directory path (trusted)
        user_path: User-provided path component (untrusted)

    Returns:
        Resolved Path object within base directory

    Raises:
        PathTraversalError: If path traversal attempt detected

    Example:
        >>> base = "/app/workspaces"
        >>> safe_path_join(base, "project1/file.txt")
        Path("/app/workspaces/project1/file.txt")
        >>> safe_path_join(base, "../../../etc/passwd")
        PathTraversalError: Path traversal attempt detected
    """
    base = Path(base_path).resolve()
    target = (base / user_path).resolve()

    # Ensure target is within base directory
    try:
        target.relative_to(base)
    except ValueError:
        raise PathTraversalError(
            f"Path traversal attempt detected: '{user_path}' resolves outside base path"
        )

    return target


async def validate_upload(
    file: UploadFile,
    max_size: int = MAX_FILE_SIZE,
    allowed_types: Optional[Set[str]] = None
) -> None:
    """
    Validate uploaded file for security.

    Args:
        file: FastAPI UploadFile object
        max_size: Maximum file size in bytes
        allowed_types: Set of allowed MIME types (None = use defaults)

    Raises:
        HTTPException: If validation fails

    Example:
        >>> await validate_upload(file)  # Uses defaults
        >>> await validate_upload(file, max_size=5*1024*1024)  # 5 MB limit
    """
    if allowed_types is None:
        allowed_types = ALLOWED_CONTENT_TYPES

    # Check content type
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{file.content_type}'. "
                   f"Allowed types: {', '.join(sorted(allowed_types))}"
        )

    # Check filename for path traversal
    if file.filename and ('/' in file.filename or '\\' in file.filename or '..' in file.filename):
        raise HTTPException(
            status_code=400,
            detail="Invalid filename: path separators not allowed"
        )

    # Validate filename pattern
    if file.filename and not SAFE_FILENAME_PATTERN.match(file.filename):
        raise HTTPException(
            status_code=400,
            detail="Invalid filename: only alphanumeric, underscore, hyphen, and dot allowed"
        )

    # Check file size
    file.file.seek(0, 2)  # Seek to end
    size = file.file.tell()
    file.file.seek(0)  # Reset to beginning

    if size > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {max_size / (1024*1024):.1f} MB"
        )

    if size == 0:
        raise HTTPException(
            status_code=400,
            detail="File is empty"
        )


def sanitize_string(
    value: str,
    max_length: Optional[int] = None,
    strip: bool = True,
    allow_empty: bool = False
) -> str:
    """
    Sanitize string input.

    Args:
        value: Input string to sanitize
        max_length: Maximum allowed length (None = no limit)
        strip: Whether to strip leading/trailing whitespace
        allow_empty: Whether to allow empty strings

    Returns:
        Sanitized string

    Raises:
        InvalidInputError: If validation fails
    """
    if not isinstance(value, str):
        raise InvalidInputError(f"Expected string, got {type(value).__name__}")

    if strip:
        value = value.strip()

    if not allow_empty and not value:
        raise InvalidInputError("Empty string not allowed")

    if max_length and len(value) > max_length:
        raise InvalidInputError(
            f"String too long. Maximum length: {max_length}, got: {len(value)}"
        )

    return value


def validate_env_var_name(name: str) -> str:
    """
    Validate environment variable name.

    Args:
        name: Environment variable name

    Returns:
        Validated name

    Raises:
        InvalidInputError: If name is invalid

    Example:
        >>> validate_env_var_name("API_KEY")
        "API_KEY"
        >>> validate_env_var_name("api-key")
        InvalidInputError: Invalid environment variable name
    """
    name = sanitize_string(name, max_length=255)

    if not SAFE_ENV_VAR_NAME_PATTERN.match(name):
        raise InvalidInputError(
            "Invalid environment variable name. Must start with uppercase letter "
            "and contain only uppercase letters, digits, and underscores."
        )

    return name


def validate_agent_name(name: str) -> str:
    """
    Validate agent name.

    Args:
        name: Agent name

    Returns:
        Validated name

    Raises:
        InvalidInputError: If name is invalid

    Example:
        >>> validate_agent_name("code_reviewer")
        "code_reviewer"
        >>> validate_agent_name("Code-Reviewer")
        InvalidInputError: Invalid agent name
    """
    name = sanitize_string(name, max_length=100)

    if not SAFE_AGENT_NAME_PATTERN.match(name):
        raise InvalidInputError(
            "Invalid agent name. Must start with lowercase letter "
            "and contain only lowercase letters, digits, and underscores."
        )

    return name


def validate_labels(labels: List[str], max_labels: int = 20) -> List[str]:
    """
    Validate list of labels.

    Args:
        labels: List of label strings
        max_labels: Maximum number of labels allowed

    Returns:
        List of validated labels

    Raises:
        InvalidInputError: If validation fails
    """
    if not isinstance(labels, list):
        raise InvalidInputError(f"Expected list, got {type(labels).__name__}")

    if len(labels) > max_labels:
        raise InvalidInputError(
            f"Too many labels. Maximum: {max_labels}, got: {len(labels)}"
        )

    validated = []
    for label in labels:
        label_str = sanitize_string(label, max_length=100)

        if not SAFE_LABEL_PATTERN.match(label_str):
            raise InvalidInputError(
                f"Invalid label '{label_str}'. Only alphanumeric, "
                "underscore, hyphen, dot, colon, and slash allowed."
            )

        validated.append(label_str)

    return validated


def validate_url(url: str, allowed_schemes: Optional[Set[str]] = None) -> str:
    """
    Validate URL format.

    Args:
        url: URL string to validate
        allowed_schemes: Set of allowed URL schemes (default: http, https)

    Returns:
        Validated URL

    Raises:
        InvalidInputError: If URL is invalid
    """
    if allowed_schemes is None:
        allowed_schemes = {'http', 'https'}

    url = sanitize_string(url, max_length=2048)

    # Basic URL validation
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except Exception as e:
        raise InvalidInputError(f"Invalid URL format: {e}")

    if not parsed.scheme:
        raise InvalidInputError("URL must include scheme (http:// or https://)")

    if parsed.scheme not in allowed_schemes:
        raise InvalidInputError(
            f"Invalid URL scheme '{parsed.scheme}'. "
            f"Allowed: {', '.join(sorted(allowed_schemes))}"
        )

    if not parsed.netloc:
        raise InvalidInputError("URL must include hostname")

    return url


def validate_integer_range(
    value: int,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None,
    field_name: str = "value"
) -> int:
    """
    Validate integer is within range.

    Args:
        value: Integer value to validate
        min_value: Minimum allowed value (inclusive)
        max_value: Maximum allowed value (inclusive)
        field_name: Name of field for error messages

    Returns:
        Validated integer

    Raises:
        InvalidInputError: If value out of range
    """
    if not isinstance(value, int):
        raise InvalidInputError(f"{field_name}: Expected integer, got {type(value).__name__}")

    if min_value is not None and value < min_value:
        raise InvalidInputError(
            f"{field_name}: Value {value} below minimum {min_value}"
        )

    if max_value is not None and value > max_value:
        raise InvalidInputError(
            f"{field_name}: Value {value} above maximum {max_value}"
        )

    return value


def validate_float_range(
    value: float,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    field_name: str = "value"
) -> float:
    """
    Validate float is within range.

    Args:
        value: Float value to validate
        min_value: Minimum allowed value (inclusive)
        max_value: Maximum allowed value (inclusive)
        field_name: Name of field for error messages

    Returns:
        Validated float

    Raises:
        InvalidInputError: If value out of range
    """
    if not isinstance(value, (int, float)):
        raise InvalidInputError(f"{field_name}: Expected number, got {type(value).__name__}")

    value = float(value)

    if min_value is not None and value < min_value:
        raise InvalidInputError(
            f"{field_name}: Value {value} below minimum {min_value}"
        )

    if max_value is not None and value > max_value:
        raise InvalidInputError(
            f"{field_name}: Value {value} above maximum {max_value}"
        )

    return value


def sanitize_search_query(query: str, max_length: int = 500) -> str:
    """
    Sanitize search query to prevent injection attacks while preserving search syntax.

    Preserves common search operators: -, +, *, " for advanced search functionality.

    Args:
        query: Search query string
        max_length: Maximum query length

    Returns:
        Sanitized query string

    Raises:
        InvalidInputError: If query is invalid
    """
    query = sanitize_string(query, max_length=max_length, allow_empty=True)

    # Remove control characters except allowed ones
    # Keep tabs, newlines, carriage returns for readability
    # Keep search operators: -, +, *, "
    allowed_chars = set('\t\n\r-+*"')
    query = ''.join(
        char for char in query
        if ord(char) >= 32 or char in allowed_chars
    )

    # Remove multiple consecutive spaces
    query = re.sub(r'\s+', ' ', query)

    return query.strip()
