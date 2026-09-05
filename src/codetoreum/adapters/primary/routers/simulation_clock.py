"""
Simulation Clock Control REST API Router

Provides simulation-only endpoints for querying and controlling the simulation clock:
- GET /api/v2/sim/clock: Query current clock state
- POST /api/v2/sim/clock/advance: Manually advance the clock by N seconds
- POST /api/v2/sim/clock/pause: Pause automatic clock advancement
- POST /api/v2/sim/clock/resume: Resume automatic clock advancement

Race condition prevention:
- POST /advance returns HTTP 409 when auto-advance is active to prevent concurrent
  clock manipulation that could interleave callback execution unpredictably.

This router is ONLY mounted in SimulationApplicationBootstrap, never in production.
"""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from codetoreum.infrastructure.simulation.simulation_engine import SimulationEngine

logger = logging.getLogger(__name__)


# =========================================================================
# Request/Response DTOs
# =========================================================================


class AdvanceClockRequest(BaseModel):
    """Request to manually advance the simulation clock."""

    seconds: float = Field(..., description="Number of simulated seconds to advance", gt=0)


class ClockStateResponse(BaseModel):
    """Current state of the simulation clock."""

    current_time: datetime = Field(..., description="Current simulated time in UTC")
    speed_multiplier: float = Field(..., description="Speed multiplier (1.0 = real time)")
    auto_advance_active: bool = Field(..., description="Whether automatic clock advancement is active")


class AdvanceClockResponse(BaseModel):
    """Result of manually advancing the simulation clock."""

    previous_time: datetime = Field(..., description="Time before advancement")
    current_time: datetime = Field(..., description="Time after advancement")
    seconds_advanced: float = Field(..., description="Simulated seconds advanced")


class PauseClockResponse(BaseModel):
    """Result of pausing automatic clock advancement."""

    status: str = Field(..., description="Operation status")
    current_time: datetime = Field(..., description="Current time when paused")


class ResumeClockResponse(BaseModel):
    """Result of resuming automatic clock advancement."""

    status: str = Field(..., description="Operation status")
    current_time: datetime = Field(..., description="Current time when resumed")


# =========================================================================
# Router Factory
# =========================================================================


def create_simulation_clock_router(engine: SimulationEngine) -> APIRouter:
    """
    Create the simulation clock control router.

    This router provides simulation-only endpoints for controlling the simulation clock.
    It takes the SimulationEngine directly (not port interfaces) because this is
    simulation infrastructure, not production code.

    Args: engine: SimulationEngine instance managing the simulation clock

    Returns: Configured APIRouter for simulation clock control
    """
    router = APIRouter(
        prefix="/api/v2/sim/clock",
        tags=["simulation-clock"],
    )

    # =====================================================================
    # Clock State Endpoint
    # =====================================================================

    @router.get("/", response_model=ClockStateResponse)
    async def get_clock_state() -> ClockStateResponse:
        """
        Get current simulation clock state.

        Returns: Current time, speed multiplier, and auto-advance status
        """
        return ClockStateResponse(
            current_time=engine.now(),
            speed_multiplier=engine.get_speed_multiplier(),
            auto_advance_active=engine.is_auto_advancing(),
        )

    # =====================================================================
    # Manual Clock Advancement Endpoint
    # =====================================================================

    @router.post("/advance", response_model=AdvanceClockResponse, status_code=status.HTTP_200_OK)
    async def advance_clock(request: AdvanceClockRequest) -> AdvanceClockResponse:
        """
        Manually advance the simulation clock by N seconds.

        This endpoint is used to fast-forward the simulation without auto-advance.
        It rejects requests while auto-advance is active to prevent race conditions
        where concurrent clock manipulation would interleave callback execution.

        Caller must pause auto-advance first with POST /pause.

        Args: request: Contains seconds to advance

        Returns: Previous time, new time, and seconds advanced

        Raises: HTTPException(409): If auto-advance is currently active
        """
        # Race condition prevention: reject manual advance while auto-advance is running
        if engine.is_auto_advancing():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot manually advance while auto-advance is active. Call /pause first.",
            )

        previous_time = engine.now()
        await engine.advance(timedelta(seconds=request.seconds))
        current_time = engine.now()

        logger.debug(
            f"Advanced clock by {request.seconds} seconds",
            extra={"previous_time": previous_time.isoformat(), "current_time": current_time.isoformat()},
        )

        return AdvanceClockResponse(
            previous_time=previous_time,
            current_time=current_time,
            seconds_advanced=request.seconds,
        )

    # =====================================================================
    # Pause Auto-Advance Endpoint
    # =====================================================================

    @router.post("/pause", response_model=PauseClockResponse, status_code=status.HTTP_200_OK)
    async def pause_clock() -> PauseClockResponse:
        """
        Pause automatic clock advancement.

        Stops the background task that automatically advances the simulation clock
        in real time. After pausing, manual advancement via POST /advance is allowed.

        Returns: Status and current time
        """
        await engine.stop_auto_advance()
        current_time = engine.now()

        logger.info(
            "Paused simulation clock auto-advance",
            extra={"current_time": current_time.isoformat()},
        )

        return PauseClockResponse(
            status="paused",
            current_time=current_time,
        )

    # =====================================================================
    # Resume Auto-Advance Endpoint
    # =====================================================================

    @router.post("/resume", response_model=ResumeClockResponse, status_code=status.HTTP_200_OK)
    async def resume_clock() -> ResumeClockResponse:
        """
        Resume automatic clock advancement.

        Restarts the background task that automatically advances the simulation clock.
        Auto-advance will continue until paused again.

        Returns: Status and current time

        Raises: HTTPException(409): If auto-advance is already running
        """
        # Prevent attempting to resume when already running
        if engine.is_auto_advancing():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Auto-advance is already running. Call /pause first to stop it.",
            )

        await engine.start_auto_advance()
        current_time = engine.now()

        logger.info(
            "Resumed simulation clock auto-advance",
            extra={
                "current_time": current_time.isoformat(),
                "speed_multiplier": engine.get_speed_multiplier(),
            },
        )

        return ResumeClockResponse(
            status="running",
            current_time=current_time,
        )

    return router
