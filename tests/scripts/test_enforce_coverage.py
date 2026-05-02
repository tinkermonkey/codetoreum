"""Tests for enforce_coverage.py script."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.enforce_coverage import (
    CoverageMetrics,
    check_regression,
    enforce_coverage,
    get_layer_coverage,
    get_overall_coverage,
    load_baseline,
    parse_coverage_json,
    run_coverage_tests,
    save_baseline,
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
        """Test when all coverage thresholds pass in strict mode."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(sample_coverage_data, f)
            temp_path = f.name

        try:
            result = enforce_coverage(temp_path, tests_failed=False, strict_mode=True)
            assert result == 0
        finally:
            Path(temp_path).unlink()

    def test_domain_threshold_fails(self, low_domain_coverage_data: dict) -> None:
        """Test when domain layer coverage fails in strict mode."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(low_domain_coverage_data, f)
            temp_path = f.name

        try:
            result = enforce_coverage(temp_path, tests_failed=False, strict_mode=True)
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
        """Test when overall coverage falls below threshold in strict mode."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(low_overall_coverage_data, f)
            temp_path = f.name

        try:
            result = enforce_coverage(temp_path, tests_failed=False, strict_mode=True)
            assert result == 1  # Should fail
        finally:
            Path(temp_path).unlink()

    def test_invalid_json_input(self) -> None:
        """Test enforce_coverage with invalid/malformed JSON input."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{invalid json content")
            temp_path = f.name

        try:
            with pytest.raises(json.JSONDecodeError):
                enforce_coverage(temp_path, tests_failed=False)
        finally:
            Path(temp_path).unlink()


class TestRunCoverageTests:
    """Tests for run_coverage_tests function."""

    @patch("scripts.enforce_coverage.subprocess.run")
    def test_run_coverage_tests_success_with_venv(self, mock_run: MagicMock) -> None:
        """Test successful coverage test run with venv pytest."""
        # Create temporary coverage.json
        with tempfile.TemporaryDirectory() as tmpdir:
            coverage_json = Path(tmpdir) / "coverage.json"
            coverage_json.write_text('{"totals": {"num_statements": 100, "covered_lines": 90}}')

            # Mock subprocess run
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "test output"
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            # Mock the .venv check to return True
            with patch("scripts.enforce_coverage.Path.exists") as mock_exists:
                mock_exists.return_value = True

                # Change to temp dir for this test
                original_cwd = os.getcwd()
                try:
                    os.chdir(tmpdir)
                    result_path, tests_failed = run_coverage_tests()
                    assert tests_failed is False
                    assert "coverage.json" in result_path
                finally:
                    os.chdir(original_cwd)

    @patch("scripts.enforce_coverage.subprocess.run")
    def test_run_coverage_tests_with_test_failures(self, mock_run: MagicMock) -> None:
        """Test coverage tests with test failures (returncode=1)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            coverage_json = Path(tmpdir) / "coverage.json"
            coverage_json.write_text('{"totals": {"num_statements": 100, "covered_lines": 80}}')

            mock_result = MagicMock()
            mock_result.returncode = 1  # Tests failed
            mock_result.stdout = "test failed: some test"
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            with patch("scripts.enforce_coverage.Path.exists") as mock_exists:
                mock_exists.return_value = True

                original_cwd = os.getcwd()
                try:
                    os.chdir(tmpdir)
                    result_path, tests_failed = run_coverage_tests()
                    assert tests_failed is True
                finally:
                    os.chdir(original_cwd)

    @patch("scripts.enforce_coverage.subprocess.run")
    def test_run_coverage_tests_pytest_error(self, mock_run: MagicMock) -> None:
        """Test coverage tests when pytest encounters an error (returncode>1)."""
        mock_result = MagicMock()
        mock_result.returncode = 2  # Pytest error
        mock_result.stdout = ""
        mock_result.stderr = "pytest error"
        mock_run.return_value = mock_result

        with patch("scripts.enforce_coverage.Path.exists") as mock_exists:
            mock_exists.return_value = True

            with pytest.raises(RuntimeError, match="Pytest encountered an error"):
                run_coverage_tests()

    @patch("scripts.enforce_coverage.subprocess.run")
    def test_run_coverage_tests_missing_coverage_json(self, mock_run: MagicMock) -> None:
        """Test run_coverage_tests when coverage.json is not created."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "tests passed"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        # Mock Path.exists to return False for coverage.json
        with patch("scripts.enforce_coverage.Path.exists") as mock_exists:
            mock_exists.return_value = True  # For .venv check
            # But we need a more specific mock for coverage.json check
            with patch("pathlib.Path.exists") as mock_path_exists:
                # First call is for .venv, return True
                # Second call is for coverage.json, return False
                mock_path_exists.side_effect = [True, False]

                with pytest.raises(RuntimeError, match="coverage.json not found"):
                    run_coverage_tests()

    def test_run_coverage_tests_uses_poetry_fallback(self) -> None:
        """Test run_coverage_tests falls back to poetry when venv doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            coverage_json = Path(tmpdir) / "coverage.json"
            coverage_json.write_text('{"totals": {"num_statements": 100, "covered_lines": 90}}')

            # Mock subprocess to capture the command
            with patch("scripts.enforce_coverage.subprocess.run") as mock_run:
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stdout = "tests passed"
                mock_result.stderr = ""
                mock_run.return_value = mock_result

                # We'll mock Path.exists() to return False for .venv/bin/pytest
                # but we need to be careful about when it gets called
                original_exists = Path.exists

                def mock_exists(self: Path) -> bool:
                    path_str = str(self)
                    if ".venv/bin/pytest" in path_str:
                        return False  # venv pytest doesn't exist
                    return original_exists(self)

                with patch.object(Path, "exists", mock_exists):
                    original_cwd = os.getcwd()
                    try:
                        os.chdir(tmpdir)
                        result_path, tests_failed = run_coverage_tests()

                        # Verify poetry command was used (not .venv/bin/pytest)
                        called_cmd = mock_run.call_args[0][0]
                        assert "poetry" in called_cmd
                        assert ".venv" not in str(called_cmd)
                    finally:
                        os.chdir(original_cwd)

    @patch("scripts.enforce_coverage.subprocess.run")
    def test_run_coverage_tests_prints_output_on_failure(
        self, mock_run: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test that pytest output is printed when tests fail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            coverage_json = Path(tmpdir) / "coverage.json"
            coverage_json.write_text('{"totals": {"num_statements": 100, "covered_lines": 80}}')

            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = "FAILED test_something"
            mock_result.stderr = "assertion error"
            mock_run.return_value = mock_result

            with patch("scripts.enforce_coverage.Path.exists") as mock_exists:
                mock_exists.return_value = True

                original_cwd = os.getcwd()
                try:
                    os.chdir(tmpdir)
                    result_path, tests_failed = run_coverage_tests()
                    captured = capsys.readouterr()

                    # Should print stdout and stderr
                    assert "FAILED test_something" in captured.out
                    assert "assertion error" in captured.err
                finally:
                    os.chdir(original_cwd)


class TestRegressionDetection:
    """Tests for regression detection and baseline functionality."""

    def test_check_regression_no_regression(self) -> None:
        """Test check_regression when coverage increased."""
        current = CoverageMetrics(percent_covered=85.0, lines_covered=85, lines_total=100)
        baseline = CoverageMetrics(percent_covered=80.0, lines_covered=80, lines_total=100)

        assert check_regression(current, baseline) is True

    def test_check_regression_equal(self) -> None:
        """Test check_regression when coverage is equal to baseline."""
        current = CoverageMetrics(percent_covered=80.0, lines_covered=80, lines_total=100)
        baseline = CoverageMetrics(percent_covered=80.0, lines_covered=80, lines_total=100)

        assert check_regression(current, baseline) is True

    def test_check_regression_decreased(self) -> None:
        """Test check_regression when coverage decreased."""
        current = CoverageMetrics(percent_covered=75.0, lines_covered=75, lines_total=100)
        baseline = CoverageMetrics(percent_covered=80.0, lines_covered=80, lines_total=100)

        assert check_regression(current, baseline) is False

    def test_save_and_load_baseline(self) -> None:
        """Test saving and loading baseline coverage data."""
        coverage_data = {
            "files": {
                "src/codetoreum/domain/models.py": {
                    "summary": {
                        "num_statements": 100,
                        "covered_lines": 100,
                    }
                }
            },
            "totals": {
                "num_statements": 100,
                "covered_lines": 100,
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            baseline_path = str(Path(tmpdir) / "baseline.json")

            # Save baseline
            save_baseline(coverage_data, baseline_path)
            assert Path(baseline_path).exists()

            # Load baseline
            loaded_data = load_baseline(baseline_path)
            assert loaded_data == coverage_data

    def test_load_baseline_not_exists(self) -> None:
        """Test load_baseline when file doesn't exist."""
        result = load_baseline("/nonexistent/baseline.json")
        assert result is None

    def test_enforce_coverage_regression_detection_mode(self, sample_coverage_data: dict) -> None:
        """Test enforce_coverage in regression detection mode (default)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create current coverage
            current_path = str(Path(tmpdir) / "coverage.json")
            with open(current_path, "w") as f:
                json.dump(sample_coverage_data, f)

            # Create baseline with lower coverage
            baseline_data = {
                "files": {
                    "src/codetoreum/domain/models.py": {
                        "summary": {"num_statements": 100, "covered_lines": 100}
                    },
                    "src/codetoreum/domain/events.py": {
                        "summary": {"num_statements": 50, "covered_lines": 40}
                    },
                    "src/codetoreum/application/services.py": {
                        "summary": {"num_statements": 100, "covered_lines": 70}
                    },
                    "src/codetoreum/application/handlers.py": {
                        "summary": {"num_statements": 50, "covered_lines": 30}
                    },
                    "src/codetoreum/adapters/testing.py": {
                        "summary": {"num_statements": 200, "covered_lines": 100}
                    },
                },
                "totals": {"num_statements": 500, "covered_lines": 340},
            }

            baseline_path = str(Path(tmpdir) / "baseline.json")
            with open(baseline_path, "w") as f:
                json.dump(baseline_data, f)

            # Run enforcement in regression detection mode (strict_mode=False)
            result = enforce_coverage(
                current_path, tests_failed=False, strict_mode=False, baseline_path=baseline_path
            )

            # Should pass because coverage improved
            assert result == 0

    def test_enforce_coverage_regression_detected(
        self, low_overall_coverage_data: dict
    ) -> None:
        """Test enforce_coverage detects regression from baseline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create current coverage (lower than baseline)
            current_path = str(Path(tmpdir) / "coverage.json")
            with open(current_path, "w") as f:
                json.dump(low_overall_coverage_data, f)

            # Create baseline with higher coverage
            baseline_data = {
                "files": {
                    "src/codetoreum/domain/models.py": {
                        "summary": {"num_statements": 100, "covered_lines": 100}
                    },
                    "src/codetoreum/application/services.py": {
                        "summary": {"num_statements": 100, "covered_lines": 100}
                    },
                    "src/codetoreum/adapters/uncovered.py": {
                        "summary": {"num_statements": 500, "covered_lines": 100}
                    },
                },
                "totals": {"num_statements": 700, "covered_lines": 300},
            }

            baseline_path = str(Path(tmpdir) / "baseline.json")
            with open(baseline_path, "w") as f:
                json.dump(baseline_data, f)

            # Run enforcement - should detect regression
            result = enforce_coverage(
                current_path, tests_failed=False, strict_mode=False, baseline_path=baseline_path
            )

            # Should fail because overall coverage regressed
            assert result == 1

    def test_enforce_coverage_strict_mode(self, sample_coverage_data: dict) -> None:
        """Test enforce_coverage in strict mode (absolute thresholds)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            coverage_path = str(Path(tmpdir) / "coverage.json")
            with open(coverage_path, "w") as f:
                json.dump(sample_coverage_data, f)

            # Run in strict mode - should pass as sample data meets thresholds
            result = enforce_coverage(
                coverage_path, tests_failed=False, strict_mode=True
            )

            assert result == 0

    def test_enforce_coverage_strict_mode_fails_below_threshold(
        self, low_domain_coverage_data: dict
    ) -> None:
        """Test enforce_coverage in strict mode fails below threshold."""
        with tempfile.TemporaryDirectory() as tmpdir:
            coverage_path = str(Path(tmpdir) / "coverage.json")
            with open(coverage_path, "w") as f:
                json.dump(low_domain_coverage_data, f)

            # Run in strict mode - should fail as domain is below 100%
            result = enforce_coverage(
                coverage_path, tests_failed=False, strict_mode=True
            )

            assert result == 1
