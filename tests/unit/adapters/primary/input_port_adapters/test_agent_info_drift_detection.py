"""Drift detection between ``Agent.invocation`` and ``AgentInfo``'s flat fields.

``AgentInfo`` (REST DTO) keeps a flat shape — ``model``, ``timeout_seconds``,
``requires_docker`` — for REST API stability. The domain ``Agent`` keeps the
canonical values inside ``invocation: AgentInvocationConfig``. The mapping
between the two lives in
``MockAgentQueryAdapter._convert_agent_to_info``.

The two surfaces can drift silently: if someone edits ``Agent.invocation``
semantics without updating the projection (or the other way around), the
flat fields will mean different things from the invocation block. These
tests assert the projection stays consistent for every combination that
matters (each ``InvocationMode``, varying model/timeout). They are the
safety net for "the day someone removes / renames a flat field" — when
that day comes, this file is the test that breaks loudly.

When ``AgentInfo`` finally drops the flat fields, delete this file along
with them.
"""

from __future__ import annotations

import pytest

from codetoreum.adapters.primary.input_port_adapters.mock.mock_agent_query_adapter import (
    MockAgentQueryAdapter,
)
from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.domain.coding_agent_types import AgentInvocationConfig, InvocationMode


def _build_agent(
    *,
    mode: InvocationMode,
    model: str,
    timeout_seconds: int,
) -> Agent:
    """Build an Agent with the given invocation block; everything else default."""
    return Agent.create(
        name="test-agent",
        display_name="Test Agent",
        agent_type=AgentType.MAKER,
        role_description="Drift-detection probe",
        capabilities={
            "skill": AgentCapability(
                skill="skill",
                proficiency=1.0,
                description="probe",
            ),
        },
        invocation=AgentInvocationConfig(
            mode=mode,
            model=model,
            timeout_seconds=timeout_seconds,
        ),
    )


@pytest.mark.parametrize(
    ("mode", "model", "timeout_seconds"),
    [
        (InvocationMode.CONTAINERIZED, "claude-sonnet-4-6", 300),
        (InvocationMode.CONTAINERIZED, "claude-opus-4-7", 600),
        (InvocationMode.HOST, "claude-sonnet-4-6", 120),
        (InvocationMode.HOST, "gpt-5", 900),
        (InvocationMode.API, "claude-haiku-4-5", 60),
    ],
)
def test_agent_info_flat_fields_track_invocation_block(
    mode: InvocationMode,
    model: str,
    timeout_seconds: int,
) -> None:
    """AgentInfo's flat fields must mirror Agent.invocation exactly.

    Drift here means a REST consumer reading ``model`` / ``timeout_seconds``
    / ``requires_docker`` will see different values than a domain consumer
    reading ``agent.invocation``.
    """
    agent = _build_agent(mode=mode, model=model, timeout_seconds=timeout_seconds)
    adapter = MockAgentQueryAdapter()

    info = adapter._convert_agent_to_info(agent)

    assert info.model == agent.invocation.model
    assert info.timeout_seconds == agent.invocation.timeout_seconds
    assert info.requires_docker == (agent.invocation.mode == InvocationMode.CONTAINERIZED)


def test_requires_docker_is_true_only_for_containerized_mode() -> None:
    """``requires_docker`` must be the literal projection of CONTAINERIZED mode.

    A future change that introduces a new invocation mode (e.g.,
    ``HOST_WITH_DOCKER`` or ``REMOTE``) needs to decide explicitly whether
    that mode requires Docker. This test will break and force that decision.
    """
    adapter = MockAgentQueryAdapter()

    containerized = adapter._convert_agent_to_info(
        _build_agent(mode=InvocationMode.CONTAINERIZED, model="m", timeout_seconds=1),
    )
    host = adapter._convert_agent_to_info(
        _build_agent(mode=InvocationMode.HOST, model="m", timeout_seconds=1),
    )
    api = adapter._convert_agent_to_info(
        _build_agent(mode=InvocationMode.API, model="m", timeout_seconds=1),
    )

    assert containerized.requires_docker is True
    assert host.requires_docker is False
    assert api.requires_docker is False

    # Sanity: confirm we covered every known mode. If a new InvocationMode
    # lands without an explicit branch here, this assertion catches it.
    assert {InvocationMode.CONTAINERIZED, InvocationMode.HOST, InvocationMode.API} == set(InvocationMode)


def test_known_invocation_modes_are_exhaustive() -> None:
    """If InvocationMode grows, this test breaks loudly.

    The flat-field projection (``requires_docker = mode == CONTAINERIZED``)
    implicitly handles every mode. If a new mode lands that *should* also
    require Docker (e.g. ``CONTAINERIZED_GPU``), the projection above
    silently classifies it as not requiring Docker. This test forces the
    new mode to be considered explicitly.
    """
    assert set(InvocationMode) == {
        InvocationMode.CONTAINERIZED,
        InvocationMode.HOST,
        InvocationMode.API,
    }, (
        "InvocationMode has changed. Update test_requires_docker_is_true_only_for_containerized_mode "
        "to cover the new mode(s) and decide explicitly whether they require Docker."
    )
