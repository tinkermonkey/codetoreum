"""
Unit tests for input validation and sanitization utilities.

Tests all security functions comprehensively to ensure proper protection
against common vulnerabilities.
"""

from io import BytesIO
from typing import cast

import pytest
from fastapi import HTTPException, UploadFile

from codetoreum.infrastructure.security.input_validation import (
    InvalidInputError,
    PathTraversalError,
    safe_path_join,
    sanitize_search_query,
    sanitize_string,
    validate_agent_name,
    validate_env_var_name,
    validate_float_range,
    validate_integer_range,
    validate_labels,
    validate_upload,
    validate_url,
)

# ============================================================================
# Path Traversal Protection Tests
# ============================================================================


class TestSafePathJoin:
    """Test path traversal protection"""

    def test_safe_path_join_valid(self, tmp_path):
        """Test joining safe paths"""
        base = str(tmp_path)
        result = safe_path_join(base, "subdir/file.txt")

        assert result == tmp_path / "subdir" / "file.txt"
        assert result.is_relative_to(tmp_path)

    def test_safe_path_join_traversal_parent(self, tmp_path):
        """Test protection against ../ traversal"""
        base = str(tmp_path)

        with pytest.raises(PathTraversalError, match="Path traversal attempt detected"):
            safe_path_join(base, "../../../etc/passwd")

    def test_safe_path_join_traversal_absolute(self, tmp_path):
        """Test protection against absolute paths"""
        base = str(tmp_path)

        with pytest.raises(PathTraversalError, match="Path traversal attempt detected"):
            safe_path_join(base, "/etc/passwd")

    def test_safe_path_join_traversal_sneaky(self, tmp_path):
        """Test protection against sneaky traversals"""
        base = str(tmp_path)

        with pytest.raises(PathTraversalError, match="Path traversal attempt detected"):
            safe_path_join(base, "subdir/../../../../../../etc/passwd")

    def test_safe_path_join_symbolic_links(self, tmp_path):
        """Test handling of symbolic links"""
        # Create a target directory outside base
        external_dir = tmp_path.parent / "external"
        external_dir.mkdir(exist_ok=True)

        # Create a symlink inside base pointing outside
        symlink_path = tmp_path / "link_to_external"
        symlink_path.symlink_to(external_dir)

        base = str(tmp_path)

        # Following the symlink should fail (resolves outside base)
        with pytest.raises(PathTraversalError):
            safe_path_join(base, "link_to_external/file.txt")


# ============================================================================
# File Upload Validation Tests
# ============================================================================


class MockUploadFile:
    """Mock FastAPI UploadFile for testing"""

    def __init__(self, filename: str, content: bytes, content_type: str):
        self.filename = filename
        self.content_type = content_type
        self.file = BytesIO(content)


class TestValidateUpload:
    """Test file upload validation"""

    @pytest.mark.asyncio
    async def test_validate_upload_valid_json(self):
        """Test valid JSON file upload"""
        file = MockUploadFile(
            filename="config.json",
            content=b'{"key": "value"}',
            content_type="application/json"
        )

        # Should not raise
        await validate_upload(cast("UploadFile", file))

    @pytest.mark.asyncio
    async def test_validate_upload_valid_yaml(self):
        """Test valid YAML file upload"""
        file = MockUploadFile(
            filename="config.yaml",
            content=b"key: value\n",
            content_type="application/yaml"
        )

        # Should not raise
        await validate_upload(cast("UploadFile", file))

    @pytest.mark.asyncio
    async def test_validate_upload_invalid_content_type(self):
        """Test rejection of invalid content type"""
        file = MockUploadFile(
            filename="script.sh",
            content=b'#!/bin/bash\necho "test"',
            content_type="application/x-sh"
        )

        with pytest.raises(HTTPException, match="Invalid file type"):
            await validate_upload(cast("UploadFile", file))

    @pytest.mark.asyncio
    async def test_validate_upload_path_traversal_in_filename(self):
        """Test rejection of path traversal in filename"""
        file = MockUploadFile(
            filename="../../../etc/passwd",
            content=b"test content",
            content_type="text/plain"
        )

        with pytest.raises(HTTPException, match="path separators not allowed"):
            await validate_upload(cast("UploadFile", file))

    @pytest.mark.asyncio
    async def test_validate_upload_invalid_filename_chars(self):
        """Test rejection of special characters in filename"""
        file = MockUploadFile(
            filename="config<script>.json",
            content=b'{"key": "value"}',
            content_type="application/json"
        )

        with pytest.raises(HTTPException, match="only alphanumeric"):
            await validate_upload(cast("UploadFile", file))

    @pytest.mark.asyncio
    async def test_validate_upload_file_too_large(self):
        """Test rejection of oversized files"""
        large_content = b"x" * (11 * 1024 * 1024)  # 11 MB
        file = MockUploadFile(
            filename="large.json",
            content=large_content,
            content_type="application/json"
        )

        with pytest.raises(HTTPException, match="File too large"):
            await validate_upload(cast("UploadFile", file))

    @pytest.mark.asyncio
    async def test_validate_upload_empty_file(self):
        """Test rejection of empty files"""
        file = MockUploadFile(
            filename="empty.json",
            content=b"",
            content_type="application/json"
        )

        with pytest.raises(HTTPException, match="File is empty"):
            await validate_upload(cast("UploadFile", file))


# ============================================================================
# String Sanitization Tests
# ============================================================================


class TestSanitizeString:
    """Test string sanitization"""

    def test_sanitize_string_valid(self):
        """Test sanitizing valid string"""
        result = sanitize_string("  Hello World  ")
        assert result == "Hello World"

    def test_sanitize_string_max_length(self):
        """Test max length enforcement"""
        with pytest.raises(InvalidInputError, match="String too long"):
            sanitize_string("x" * 1000, max_length=100)

    def test_sanitize_string_empty_not_allowed(self):
        """Test empty string rejection"""
        with pytest.raises(InvalidInputError, match="Empty string not allowed"):
            sanitize_string("   ", allow_empty=False)

    def test_sanitize_string_empty_allowed(self):
        """Test empty string allowed"""
        result = sanitize_string("", allow_empty=True)
        assert result == ""

    def test_sanitize_string_no_strip(self):
        """Test string without stripping"""
        result = sanitize_string("  test  ", strip=False)
        assert result == "  test  "


# ============================================================================
# Environment Variable Validation Tests
# ============================================================================


class TestValidateEnvVarName:
    """Test environment variable name validation"""

    def test_validate_env_var_name_valid(self):
        """Test valid environment variable names"""
        assert validate_env_var_name("API_KEY") == "API_KEY"
        assert validate_env_var_name("DATABASE_URL") == "DATABASE_URL"
        assert validate_env_var_name("PORT") == "PORT"
        assert validate_env_var_name("LOG_LEVEL_DEBUG") == "LOG_LEVEL_DEBUG"

    def test_validate_env_var_name_invalid_lowercase(self):
        """Test rejection of lowercase names"""
        with pytest.raises(InvalidInputError, match="Invalid environment variable name"):
            validate_env_var_name("api_key")

    def test_validate_env_var_name_invalid_hyphen(self):
        """Test rejection of hyphens"""
        with pytest.raises(InvalidInputError, match="Invalid environment variable name"):
            validate_env_var_name("API-KEY")

    def test_validate_env_var_name_invalid_starts_with_digit(self):
        """Test rejection of names starting with digit"""
        with pytest.raises(InvalidInputError, match="Invalid environment variable name"):
            validate_env_var_name("1API_KEY")


# ============================================================================
# Agent Name Validation Tests
# ============================================================================


class TestValidateAgentName:
    """Test agent name validation"""

    def test_validate_agent_name_valid(self):
        """Test valid agent names"""
        assert validate_agent_name("code_reviewer") == "code_reviewer"
        assert validate_agent_name("test_executor") == "test_executor"
        assert validate_agent_name("deployer") == "deployer"

    def test_validate_agent_name_invalid_uppercase(self):
        """Test rejection of uppercase names"""
        with pytest.raises(InvalidInputError, match="Invalid agent name"):
            validate_agent_name("Code_Reviewer")

    def test_validate_agent_name_invalid_hyphen(self):
        """Test rejection of hyphens"""
        with pytest.raises(InvalidInputError, match="Invalid agent name"):
            validate_agent_name("code-reviewer")

    def test_validate_agent_name_invalid_starts_with_digit(self):
        """Test rejection of names starting with digit"""
        with pytest.raises(InvalidInputError, match="Invalid agent name"):
            validate_agent_name("1_code_reviewer")


# ============================================================================
# Label Validation Tests
# ============================================================================


class TestValidateLabels:
    """Test label validation"""

    def test_validate_labels_valid(self):
        """Test valid labels"""
        labels = ["bug", "enhancement", "priority:high", "team/backend"]
        result = validate_labels(labels)
        assert result == labels

    def test_validate_labels_too_many(self):
        """Test rejection of too many labels"""
        labels = [f"label{i}" for i in range(25)]
        with pytest.raises(InvalidInputError, match="Too many labels"):
            validate_labels(labels, max_labels=20)

    def test_validate_labels_invalid_chars(self):
        """Test rejection of invalid characters"""
        labels = ["bug", "test<script>"]
        with pytest.raises(InvalidInputError, match="Invalid label"):
            validate_labels(labels)

    def test_validate_labels_not_list(self):
        """Test rejection of non-list input"""
        with pytest.raises(InvalidInputError, match="Expected list"):
            validate_labels("bug,enhancement")  # type: ignore


# ============================================================================
# URL Validation Tests
# ============================================================================


class TestValidateUrl:
    """Test URL validation"""

    def test_validate_url_valid_http(self):
        """Test valid HTTP URL"""
        url = "http://example.com/path?query=value"
        assert validate_url(url) == url

    def test_validate_url_valid_https(self):
        """Test valid HTTPS URL"""
        url = "https://example.com/path"
        assert validate_url(url) == url

    def test_validate_url_invalid_scheme(self):
        """Test rejection of invalid schemes"""
        with pytest.raises(InvalidInputError, match="Invalid URL scheme"):
            validate_url("ftp://example.com/file")

    def test_validate_url_missing_scheme(self):
        """Test rejection of URL without scheme"""
        with pytest.raises(InvalidInputError, match="must include scheme"):
            validate_url("example.com/path")

    def test_validate_url_missing_hostname(self):
        """Test rejection of URL without hostname"""
        with pytest.raises(InvalidInputError, match="must include hostname"):
            validate_url("http:///path")


# ============================================================================
# Numeric Range Validation Tests
# ============================================================================


class TestValidateIntegerRange:
    """Test integer range validation"""

    def test_validate_integer_range_valid(self):
        """Test valid integer in range"""
        assert validate_integer_range(50, min_value=0, max_value=100) == 50

    def test_validate_integer_range_below_min(self):
        """Test rejection of value below minimum"""
        with pytest.raises(InvalidInputError, match="below minimum"):
            validate_integer_range(-10, min_value=0)

    def test_validate_integer_range_above_max(self):
        """Test rejection of value above maximum"""
        with pytest.raises(InvalidInputError, match="above maximum"):
            validate_integer_range(150, max_value=100)

    def test_validate_integer_range_not_integer(self):
        """Test rejection of non-integer"""
        with pytest.raises(InvalidInputError, match="Expected integer"):
            validate_integer_range(50.5, min_value=0, max_value=100)  # type: ignore


class TestValidateFloatRange:
    """Test float range validation"""

    def test_validate_float_range_valid(self):
        """Test valid float in range"""
        assert validate_float_range(50.5, min_value=0.0, max_value=100.0) == 50.5

    def test_validate_float_range_integer_accepted(self):
        """Test integer accepted as float"""
        assert validate_float_range(50, min_value=0.0, max_value=100.0) == 50.0

    def test_validate_float_range_below_min(self):
        """Test rejection of value below minimum"""
        with pytest.raises(InvalidInputError, match="below minimum"):
            validate_float_range(-10.5, min_value=0.0)

    def test_validate_float_range_above_max(self):
        """Test rejection of value above maximum"""
        with pytest.raises(InvalidInputError, match="above maximum"):
            validate_float_range(150.5, max_value=100.0)


# ============================================================================
# Search Query Sanitization Tests
# ============================================================================


class TestSanitizeSearchQuery:
    """Test search query sanitization"""

    def test_sanitize_search_query_valid(self):
        """Test sanitizing valid search query"""
        query = "search term with spaces"
        result = sanitize_search_query(query)
        assert result == query

    def test_sanitize_search_query_preserve_operators(self):
        """Test preserving search operators"""
        query = 'term1 +term2 -term3 "exact phrase" *wildcard*'
        result = sanitize_search_query(query)
        assert result == query

    def test_sanitize_search_query_remove_control_chars(self):
        """Test removal of control characters"""
        query = "test\x00\x01\x02query"
        result = sanitize_search_query(query)
        assert "\x00" not in result
        assert "\x01" not in result
        assert "test" in result
        assert "query" in result

    def test_sanitize_search_query_collapse_spaces(self):
        """Test collapsing multiple spaces"""
        query = "test    query    with    spaces"
        result = sanitize_search_query(query)
        assert result == "test query with spaces"

    def test_sanitize_search_query_max_length(self):
        """Test max length enforcement"""
        query = "x" * 1000
        with pytest.raises(InvalidInputError, match="String too long"):
            sanitize_search_query(query, max_length=500)

    def test_sanitize_search_query_empty_allowed(self):
        """Test empty query handling"""
        result = sanitize_search_query("")
        assert result == ""


# ============================================================================
# Integration Tests
# ============================================================================


class TestSecurityIntegration:
    """Test integration of multiple security functions"""

    def test_full_validation_chain(self):
        """Test using multiple validation functions together"""
        # Validate environment variable
        env_name = validate_env_var_name("DATABASE_URL")
        assert env_name == "DATABASE_URL"

        # Validate URL value
        url_value = validate_url("https://db.example.com:5432/mydb")
        assert "https://" in url_value

        # Validate agent name
        agent = validate_agent_name("database_migrator")
        assert agent == "database_migrator"

        # Validate labels
        labels = validate_labels(["database", "migration", "priority:high"])
        assert len(labels) == 3

    def test_error_handling_consistency(self):
        """Test that all validation functions raise consistent errors"""
        # All should raise InvalidInputError for invalid input
        with pytest.raises(InvalidInputError):
            sanitize_string("", allow_empty=False)

        with pytest.raises(InvalidInputError):
            validate_env_var_name("invalid-name")

        with pytest.raises(InvalidInputError):
            validate_agent_name("Invalid_Name")

        with pytest.raises(InvalidInputError):
            validate_integer_range(200, max_value=100)
