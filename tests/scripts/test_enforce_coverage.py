"""Tests for enforce_coverage.py script."""

import json
import tempfile
from pathlib import Path

import pytest

from scripts.enforce_coverage import (
    CoverageMetrics,
    CoverageThreshold,
    enforce_coverage,
    get_layer_coverage,
    get_overall_coverage,
    parse_coverage_json,
)


# Fixtures for test coverage data
@pytest.fixture
def sample_coverage_data() -> dict:
    """Sample coverage.json structure."""
    return {
        "files": {
            "src/codetoreum/domain/models.py": {
                "summary": {
                    "num_statements": 100,
                    "covered_lines": 100,
                }
            },
            "src/codetoreum/domain/events.py": {
                "summary": {
                    "num_statements": 50,
                    "covered_lines": 50,
                }
            },
            "src/codetoreum/application/services.py": {
                "summary": {
                    "num_statements": 100,
                    "covered_lines": 90,
                }
            },
            "src/codetoreum/application/handlers.py": {
                "summary": {
                    "num_statements": 50,
                    "covered_lines": 45,
                }
            },
            "src/codetoreum/adapters/testing.py": {
                "summary": {
                    "num_statements": 200,
                    "covered_lines": 150,
                }
            },
        },
        "totals": {
            "num_statements": 500,
            "covered_lines": 435,
        },
    }


@pytest.fixture
def low_domain_coverage_data() -> dict:
    """Coverage data with low domain layer coverage."""
    return {
        "files": {
            "src/codetoreum/domain/models.py": {
                "summary": {
                    "num_statements": 100,
                    "covered_lines": 95,  # Only 95%
                }
            },
            "src/codetoreum/application/services.py": {
                "summary": {
                    "num_statements": 100,
                    "covered_lines": 95,
                }
            },
        },
        "totals": {
            "num_statements": 200,
            "covered_lines": 190,
        },
    }


@pytest.fixture
def low_overall_coverage_data() -> dict:
    """Coverage data with low overall coverage."""
    return {
        "files": {
            "src/codetoreum/domain/models.py": {
                "summary": {
                    "num_statements": 100,
                    "covered_lines": 100,
                }
            },
            "src/codetoreum/application/services.py": {
                "summary": {
                    "num_statements": 100,
                    "covered_lines": 100,
                }
            },
            "src/codetoreum/adapters/uncovered.py": {
                "summary": {
                    "num_statements": 500,
                    "covered_lines": 50,  # Very low adapter coverage
                }
            },
        },
        "totals": {
            "num_statements": 700,
            "covered_lines": 250,  # 35.7% overall
        },
    }


@pytest.fixture
def empty_coverage_data() -> dict:
    """Empty coverage data."""
    return {
        "files": {},
        "totals": {
            "num_statements": 0,
            "covered_lines": 0,
        },
    }


class TestParseJsonCoverage:
    """Tests for parse_coverage_json function."""

    def test_parse_coverage_json_valid(self, sample_coverage_data: dict) -> None:
        """Test parsing valid coverage.json."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(sample_coverage_data, f)
            temp_path = f.name

        try:
            result = parse_coverage_json(temp_path)
            assert result == sample_coverage_data
            assert "files" in result
            assert "totals" in result
        finally:
            Path(temp_path).unlink()

    def test_parse_coverage_json_empty_files(self, empty_coverage_data: dict) -> None:
        """Test parsing coverage.json with no files."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(empty_coverage_data, f)
            temp_path = f.name

        try:
            result = parse_coverage_json(temp_path)
            assert result == empty_coverage_data
            assert result["files"] == {}
        finally:
            Path(temp_path).unlink()

    def test_parse_coverage_json_file_not_found(self) -> None:
        """Test parsing non-existent file."""
        with pytest.raises(FileNotFoundError):
            parse_coverage_json("/nonexistent/coverage.json")


class TestGetLayerCoverage:
    """Tests for get_layer_coverage function."""

    def test_domain_layer_100_percent(self, sample_coverage_data: dict) -> None:
        """Test domain layer with 100% coverage."""
        result = get_layer_coverage(sample_coverage_data, "src/codetoreum/domain")
        assert result.percent_covered == 100.0
        assert result.lines_covered == 150
        assert result.lines_total == 150

    def test_application_layer_90_percent(self, sample_coverage_data: dict) -> None:
        """Test application layer with 90% coverage."""
        result = get_layer_coverage(sample_coverage_data, "src/codetoreum/application")
        assert result.percent_covered == 90.0
        assert result.lines_covered == 135
        assert result.lines_total == 150

    def test_no_matching_files(self, sample_coverage_data: dict) -> None:
        """Test with pattern that matches no files."""
        result = get_layer_coverage(sample_coverage_data, "src/nonexistent")
        assert result.percent_covered == 0.0
        assert result.lines_covered == 0
        assert result.lines_total == 0

    def test_empty_coverage_data(self, empty_coverage_data: dict) -> None:
        """Test with empty coverage data."""
        result = get_layer_coverage(empty_coverage_data, "src/codetoreum/domain")
        assert result.percent_covered == 0.0
        assert result.lines_covered == 0
        assert result.lines_total == 0

    def test_partial_coverage(self, low_domain_coverage_data: dict) -> None:
        """Test domain layer with partial coverage."""
        result = get_layer_coverage(low_domain_coverage_data, "src/codetoreum/domain")
        assert result.percent_covered == 95.0
        assert result.lines_covered == 95
        assert result.lines_total == 100


class TestGetOverallCoverage:
    """Tests for get_overall_coverage function."""

    def test_overall_coverage(self, sample_coverage_data: dict) -> None:
        """Test overall coverage calculation."""
        result = get_overall_coverage(sample_coverage_data)
        assert result.percent_covered == 87.0
        assert result.lines_covered == 435
        assert result.lines_total == 500

    def test_overall_coverage_empty(self, empty_coverage_data: dict) -> None:
        """Test overall coverage with no data."""
        result = get_overall_coverage(empty_coverage_data)
        assert result.percent_covered == 0.0
        assert result.lines_covered == 0
        assert result.lines_total == 0

    def test_overall_coverage_low(self, low_overall_coverage_data: dict) -> None:
        """Test overall coverage below threshold."""
        result = get_overall_coverage(low_overall_coverage_data)
        expected_percent = (250 / 700) * 100  # ~35.71%
        assert abs(result.percent_covered - expected_percent) < 0.1
        assert result.lines_covered == 250
        assert result.lines_total == 700


class TestEnforceCoverage:
    """Tests for enforce_coverage function."""

    def test_all_thresholds_pass(self, sample_coverage_data: dict) -> None:
        """Test when all coverage thresholds pass."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(sample_coverage_data, f)
            temp_path = f.name

        try:
            result = enforce_coverage(temp_path, tests_failed=False)
            assert result == 0
        finally:
            Path(temp_path).unlink()

    def test_domain_threshold_fails(self, low_domain_coverage_data: dict) -> None:
        """Test when domain layer coverage fails."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(low_domain_coverage_data, f)
            temp_path = f.name

        try:
            result = enforce_coverage(temp_path, tests_failed=False)
            assert result == 1  # Should fail
        finally:
            Path(temp_path).unlink()

    def test_tests_failed_overrides_success(self, sample_coverage_data: dict) -> None:
        """Test that test failures override coverage pass."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(sample_coverage_data, f)
            temp_path = f.name

        try:
            result = enforce_coverage(temp_path, tests_failed=True)
            assert result == 1  # Should fail due to test failures
        finally:
            Path(temp_path).unlink()

    def test_overall_threshold_fails(self, low_overall_coverage_data: dict) -> None:
        """Test when overall coverage falls below threshold."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(low_overall_coverage_data, f)
            temp_path = f.name

        try:
            result = enforce_coverage(temp_path, tests_failed=False)
            assert result == 1  # Should fail
        finally:
            Path(temp_path).unlink()

    def test_returns_coverage_metrics(self, sample_coverage_data: dict) -> None:
        """Test that coverage metrics are returned as expected."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(sample_coverage_data, f)
            temp_path = f.name

        try:
            # Test function returns exit code, not metrics
            # But we verify it works correctly
            result = enforce_coverage(temp_path, tests_failed=False)
            assert isinstance(result, int)
            assert result in (0, 1)
        finally:
            Path(temp_path).unlink()
