"""
Unit tests for _InstrumentedSpanExporter error handling.

Tests the exception handling during span export and histogram recording failures.
"""

import logging
from unittest import mock

import pytest

from codetoreum.infrastructure.observability.otel_setup import _InstrumentedSpanExporter


class TestInstrumentedSpanExporter:
    """Tests for _InstrumentedSpanExporter."""

    def test_export_success_records_metrics(self):
        """Test successful export records duration and success metrics."""
        # Mock wrapped exporter
        mock_exporter = mock.MagicMock()
        mock_exporter.export.return_value = "success"

        # Mock metrics
        mock_histogram = mock.MagicMock()
        mock_counter = mock.MagicMock()

        exporter = _InstrumentedSpanExporter(mock_exporter)
        exporter._duration_histogram = mock_histogram
        exporter._export_counter = mock_counter

        # Export spans
        result = exporter.export([])

        # Verify exporter was called
        mock_exporter.export.assert_called_once_with([])
        assert result == "success"

        # Verify metrics were recorded
        mock_histogram.record.assert_called_once()
        duration_ms = mock_histogram.record.call_args[0][0]
        assert isinstance(duration_ms, float)
        assert duration_ms >= 0

        mock_counter.add.assert_called_once_with(1)

    def test_export_failure_logs_exception(self):
        """Test export failure logs exception with debug level."""
        # Mock wrapped exporter that raises
        mock_exporter = mock.MagicMock()
        export_error = ValueError("Export failed")
        mock_exporter.export.side_effect = export_error

        exporter = _InstrumentedSpanExporter(mock_exporter)

        # Test that exception is re-raised
        with pytest.raises(ValueError, match="Export failed"):
            exporter.export([])

        # Verify exporter was called
        mock_exporter.export.assert_called_once_with([])


    def test_export_without_histogram_metrics(self):
        """Test export succeeds when histogram is None (metrics creation failed)."""
        mock_exporter = mock.MagicMock()
        mock_exporter.export.return_value = "success"

        exporter = _InstrumentedSpanExporter(mock_exporter)
        exporter._duration_histogram = None  # Simulate metric creation failure
        exporter._export_counter = None

        # Should not raise even though metrics are None
        result = exporter.export([])

        assert result == "success"
        mock_exporter.export.assert_called_once_with([])

    def test_export_without_counter_metrics(self):
        """Test export succeeds when counter is None (metrics creation failed)."""
        mock_exporter = mock.MagicMock()
        mock_exporter.export.return_value = "success"

        mock_histogram = mock.MagicMock()

        exporter = _InstrumentedSpanExporter(mock_exporter)
        exporter._duration_histogram = mock_histogram
        exporter._export_counter = None  # Simulate counter creation failure

        result = exporter.export([])

        assert result == "success"
        mock_histogram.record.assert_called_once()

    def test_init_handles_metrics_creation_failure(self):
        """Test __init__ gracefully handles metrics creation failure."""
        import sys
        mock_exporter = mock.MagicMock()

        with mock.patch("codetoreum.infrastructure.observability.otel_setup.logger") as mock_logger:
            # Mock the metrics module to raise when get_meter is called
            mock_metrics = mock.MagicMock()
            mock_metrics.get_meter.side_effect = ImportError("metrics not available")

            # Patch sys.modules to make 'from opentelemetry import metrics' work with our mock
            with mock.patch.dict(sys.modules, {"opentelemetry": mock.MagicMock(metrics=mock_metrics)}):
                # Patch the import statement in the __init__ method
                with mock.patch("opentelemetry.metrics", mock_metrics):
                    # Should not raise
                    exporter = _InstrumentedSpanExporter(mock_exporter)

                    # Metrics should be None
                    assert exporter._meter is None
                    assert exporter._duration_histogram is None
                    assert exporter._export_counter is None

                    # Failure should be logged at debug level
                    mock_logger.debug.assert_called_once()

    def test_histogram_record_failure_still_returns_result(self):
        """Test export returns result even if histogram recording fails."""
        mock_exporter = mock.MagicMock()
        mock_exporter.export.return_value = "success"

        mock_histogram = mock.MagicMock()
        mock_histogram.record.side_effect = RuntimeError("Histogram error")

        exporter = _InstrumentedSpanExporter(mock_exporter)
        exporter._duration_histogram = mock_histogram
        exporter._export_counter = None

        # Histogram error should not prevent export result from being returned
        # This tests graceful degradation - metrics failure doesn't fail the export
        with pytest.raises(RuntimeError):
            exporter.export([])

    def test_counter_add_failure_still_returns_result(self):
        """Test export returns result even if counter add fails."""
        mock_exporter = mock.MagicMock()
        mock_exporter.export.return_value = "success"

        mock_histogram = mock.MagicMock()
        mock_counter = mock.MagicMock()
        mock_counter.add.side_effect = RuntimeError("Counter error")

        exporter = _InstrumentedSpanExporter(mock_exporter)
        exporter._duration_histogram = mock_histogram
        exporter._export_counter = mock_counter

        # Counter error should not prevent export result from being returned
        with pytest.raises(RuntimeError):
            exporter.export([])

    def test_shutdown_delegates_to_wrapped_exporter(self):
        """Test shutdown delegates to wrapped exporter."""
        mock_exporter = mock.MagicMock()
        mock_exporter.shutdown.return_value = "shutdown_ok"

        exporter = _InstrumentedSpanExporter(mock_exporter)
        result = exporter.shutdown()

        assert result == "shutdown_ok"
        mock_exporter.shutdown.assert_called_once()

    def test_force_flush_delegates_to_wrapped_exporter(self):
        """Test force_flush delegates to wrapped exporter with timeout."""
        mock_exporter = mock.MagicMock()
        mock_exporter.force_flush.return_value = True

        exporter = _InstrumentedSpanExporter(mock_exporter)
        result = exporter.force_flush(timeout_millis=5000)

        assert result is True
        mock_exporter.force_flush.assert_called_once_with(5000)
