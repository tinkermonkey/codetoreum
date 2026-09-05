"""Test bootstrap degraded mode error handling.

This test module verifies that the bootstrap properly signals degraded mode
when critical phases fail, instead of silently swallowing errors.

Addresses issue #440: [PR Feedback] Bootstrap Error Handling
"""

from codetoreum.infrastructure.simulation.bootstrap import (
    BootstrapDegradedModeState,
    BootstrapPhase,
)


class TestBootstrapDegradedModeState:
    """Test the BootstrapDegradedModeState tracking."""

    def test_initial_state_is_healthy(self):
        """Test that a new state starts as healthy (not degraded)."""
        state = BootstrapDegradedModeState()
        assert not state.is_degraded
        assert len(state.failed_phases) == 0
        assert len(state.failed_phase_names) == 0

    def test_mark_failed_sets_degraded(self):
        """Test that marking a phase as failed sets degraded mode."""
        state = BootstrapDegradedModeState()
        state.mark_failed(BootstrapPhase.AUTO_ADVANCE, "Clock failed to start")
        assert state.is_degraded
        assert BootstrapPhase.AUTO_ADVANCE in state.failed_phases
        assert state.failed_phases[BootstrapPhase.AUTO_ADVANCE] == "Clock failed to start"

    def test_multiple_failures_tracked(self):
        """Test that multiple failures are all tracked."""
        state = BootstrapDegradedModeState()
        state.mark_failed(BootstrapPhase.AUTO_ADVANCE, "Clock error")
        state.mark_failed(BootstrapPhase.STALE_LOCK_WATCHDOG, "Watchdog error")
        state.mark_failed(BootstrapPhase.EXECUTION_TIMEOUT_WATCHDOG, "Timeout error")

        assert state.is_degraded
        assert len(state.failed_phases) == 3
        assert set(state.failed_phase_names) == {
            "auto_advance",
            "stale_lock_watchdog",
            "execution_timeout_watchdog",
        }

    def test_summary_for_healthy_state(self):
        """Test that healthy state provides appropriate summary."""
        state = BootstrapDegradedModeState()
        summary = state.get_summary()
        assert "successfully" in summary.lower()
        assert "degraded" not in summary.lower()

    def test_summary_for_degraded_state(self):
        """Test that degraded state provides detailed summary."""
        state = BootstrapDegradedModeState()
        state.mark_failed(BootstrapPhase.AUTO_ADVANCE, "Clock failed")
        state.mark_failed(BootstrapPhase.STALE_LOCK_WATCHDOG, "Watchdog failed")

        summary = state.get_summary()
        assert "degraded mode" in summary.lower()
        assert "auto_advance" in summary
        assert "stale_lock_watchdog" in summary
        assert "Clock failed" in summary
        assert "Watchdog failed" in summary

    def test_failed_phase_names_property(self):
        """Test that failed_phase_names returns correct values."""
        state = BootstrapDegradedModeState()
        assert state.failed_phase_names == []

        state.mark_failed(BootstrapPhase.AUTO_ADVANCE, "error1")
        state.mark_failed(BootstrapPhase.EXECUTION_TIMEOUT_WATCHDOG, "error2")

        names = state.failed_phase_names
        assert "auto_advance" in names
        assert "execution_timeout_watchdog" in names
        assert len(names) == 2

    def test_all_bootstrap_phases_defined(self):
        """Test that all critical bootstrap phases are defined in the enum."""
        # These are the phases that can fail and trigger degraded mode
        phases = [
            BootstrapPhase.AUTO_ADVANCE,
            BootstrapPhase.STALE_LOCK_WATCHDOG,
            BootstrapPhase.EXECUTION_TIMEOUT_WATCHDOG,
            BootstrapPhase.SLA_EXPIRY_WATCHDOG,
        ]
        assert len(phases) == 4
        assert all(isinstance(p, BootstrapPhase) for p in phases)

    def test_error_messages_preserved(self):
        """Test that error messages are preserved exactly as provided."""
        state = BootstrapDegradedModeState()
        error1 = "RuntimeError: Clock initialization failed on port 5000"
        error2 = "ValueError: Invalid speed multiplier: -1"

        state.mark_failed(BootstrapPhase.AUTO_ADVANCE, error1)
        state.mark_failed(BootstrapPhase.STALE_LOCK_WATCHDOG, error2)

        assert state.failed_phases[BootstrapPhase.AUTO_ADVANCE] == error1
        assert state.failed_phases[BootstrapPhase.STALE_LOCK_WATCHDOG] == error2

    def test_degraded_state_immutable_after_mark_failed(self):
        """Test that is_degraded becomes true and stays true after marking failures."""
        state = BootstrapDegradedModeState()
        assert not state.is_degraded

        state.mark_failed(BootstrapPhase.AUTO_ADVANCE, "error")
        assert state.is_degraded

        # Verify it remains degraded
        assert state.is_degraded

        # Mark another failure
        state.mark_failed(BootstrapPhase.STALE_LOCK_WATCHDOG, "error2")
        assert state.is_degraded
