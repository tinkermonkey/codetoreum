"""Tests for RepairCycleAgentConfigModel and validation.

Verifies:
- RepairCycleAgentConfigModel can be instantiated with all field combinations
- RepairCycleAgentConfigModel.to_domain() produces valid domain objects
- ScenarioColumnConfig.repair_cycle_agents field accepts RepairCycleAgentConfigModel
- OrchestratorConfigModel validates repair_cycle_agents references
- Cross-field validation catches undefined agent references
- Backward compatibility: YAML without repair_cycle_agents parses correctly
"""

import pytest
from pydantic import ValidationError

from codetoreum.domain.repair_cycle_types import RepairCycleAgentConfig
from codetoreum.infrastructure.simulation.scenario_models import (
    RepairCycleAgentConfigModel,
    ScenarioAgentModel,
    ScenarioBoardPolicyModel,
    ScenarioColumnConfig,
    OrchestratorConfigModel,
)


class TestRepairCycleAgentConfigModel:
    """Test RepairCycleAgentConfigModel instantiation and conversion."""

    def test_empty_repair_cycle_config(self) -> None:
        """All fields default to None when not specified."""
        config = RepairCycleAgentConfigModel()
        assert config.test_execution is None
        assert config.code_fix is None
        assert config.systemic_analysis is None
        assert config.systemic_fix is None
        assert config.env_rebuild is None
        assert config.env_verification is None

    def test_partial_repair_cycle_config(self) -> None:
        """Some fields can be set while others remain None."""
        config = RepairCycleAgentConfigModel(
            test_execution="qa_engineer",
            code_fix="senior_software_engineer",
        )
        assert config.test_execution == "qa_engineer"
        assert config.code_fix == "senior_software_engineer"
        assert config.systemic_analysis is None
        assert config.systemic_fix is None
        assert config.env_rebuild is None
        assert config.env_verification is None

    def test_full_repair_cycle_config(self) -> None:
        """All fields can be set."""
        config = RepairCycleAgentConfigModel(
            test_execution="qa_engineer",
            code_fix="senior_software_engineer",
            systemic_analysis="architect",
            systemic_fix="platform_engineer",
            env_rebuild="devops_engineer",
            env_verification="qa_engineer",
        )
        assert config.test_execution == "qa_engineer"
        assert config.code_fix == "senior_software_engineer"
        assert config.systemic_analysis == "architect"
        assert config.systemic_fix == "platform_engineer"
        assert config.env_rebuild == "devops_engineer"
        assert config.env_verification == "qa_engineer"

    def test_to_domain_empty(self) -> None:
        """to_domain() produces valid RepairCycleAgentConfig with all None."""
        config = RepairCycleAgentConfigModel()
        domain = config.to_domain()

        assert isinstance(domain, RepairCycleAgentConfig)
        assert domain.test_execution is None
        assert domain.code_fix is None
        assert domain.systemic_analysis is None
        assert domain.systemic_fix is None
        assert domain.env_rebuild is None
        assert domain.env_verification is None

    def test_to_domain_partial(self) -> None:
        """to_domain() preserves partial field values."""
        config = RepairCycleAgentConfigModel(
            test_execution="qa_engineer",
            code_fix="senior_software_engineer",
        )
        domain = config.to_domain()

        assert isinstance(domain, RepairCycleAgentConfig)
        assert domain.test_execution == "qa_engineer"
        assert domain.code_fix == "senior_software_engineer"
        assert domain.systemic_analysis is None
        assert domain.systemic_fix is None
        assert domain.env_rebuild is None
        assert domain.env_verification is None

    def test_to_domain_full(self) -> None:
        """to_domain() converts all fields correctly."""
        config = RepairCycleAgentConfigModel(
            test_execution="qa_engineer",
            code_fix="senior_software_engineer",
            systemic_analysis="architect",
            systemic_fix="platform_engineer",
            env_rebuild="devops_engineer",
            env_verification="qa_engineer",
        )
        domain = config.to_domain()

        assert isinstance(domain, RepairCycleAgentConfig)
        assert domain.test_execution == "qa_engineer"
        assert domain.code_fix == "senior_software_engineer"
        assert domain.systemic_analysis == "architect"
        assert domain.systemic_fix == "platform_engineer"
        assert domain.env_rebuild == "devops_engineer"
        assert domain.env_verification == "qa_engineer"


class TestScenarioColumnConfigRepairCycleAgents:
    """Test ScenarioColumnConfig with repair_cycle_agents field."""

    def test_column_config_without_repair_cycle_agents(self) -> None:
        """repair_cycle_agents defaults to None when not specified."""
        col = ScenarioColumnConfig(
            name="Testing",
            type="automated",
            agent_id="qa_engineer",
        )
        assert col.repair_cycle_agents is None

    def test_column_config_with_empty_repair_cycle_agents(self) -> None:
        """repair_cycle_agents can be explicitly set to empty config."""
        col = ScenarioColumnConfig(
            name="Testing",
            type="automated",
            agent_id="qa_engineer",
            repair_cycle_agents=RepairCycleAgentConfigModel(),
        )
        assert col.repair_cycle_agents is not None
        assert col.repair_cycle_agents.test_execution is None

    def test_column_config_with_repair_cycle_agents(self) -> None:
        """repair_cycle_agents can be set with specific agents."""
        col = ScenarioColumnConfig(
            name="Testing",
            type="automated",
            agent_id="qa_engineer",
            repair_cycle_agents=RepairCycleAgentConfigModel(
                test_execution="qa_engineer",
                code_fix="senior_software_engineer",
            ),
        )
        assert col.repair_cycle_agents is not None
        assert col.repair_cycle_agents.test_execution == "qa_engineer"
        assert col.repair_cycle_agents.code_fix == "senior_software_engineer"


class TestOrchestratorConfigValidation:
    """Test cross-field validation on OrchestratorConfigModel."""

    def test_valid_config_without_repair_cycle_agents(self) -> None:
        """Config without repair_cycle_agents passes validation."""
        config = OrchestratorConfigModel(
            name="test",
            agents=[
                ScenarioAgentModel(name="coder"),
                ScenarioAgentModel(name="tester"),
            ],
            board_policies=[
                ScenarioBoardPolicyModel(
                    board_id="board-1",
                    column_configs=[
                        ScenarioColumnConfig(
                            name="In Progress",
                            type="automated",
                            agent_id="coder",
                        ),
                    ],
                ),
            ],
        )
        assert config is not None

    def test_valid_config_with_empty_repair_cycle_agents(self) -> None:
        """Config with empty repair_cycle_agents passes validation."""
        config = OrchestratorConfigModel(
            name="test",
            agents=[
                ScenarioAgentModel(name="coder"),
                ScenarioAgentModel(name="tester"),
            ],
            board_policies=[
                ScenarioBoardPolicyModel(
                    board_id="board-1",
                    column_configs=[
                        ScenarioColumnConfig(
                            name="Testing",
                            type="automated",
                            agent_id="tester",
                            repair_cycle_agents=RepairCycleAgentConfigModel(),
                        ),
                    ],
                ),
            ],
        )
        assert config is not None

    def test_valid_config_with_repair_cycle_agents(self) -> None:
        """Config with repair_cycle_agents referencing defined agents passes validation."""
        config = OrchestratorConfigModel(
            name="test",
            agents=[
                ScenarioAgentModel(name="qa_engineer"),
                ScenarioAgentModel(name="senior_software_engineer"),
                ScenarioAgentModel(name="devops_engineer"),
            ],
            board_policies=[
                ScenarioBoardPolicyModel(
                    board_id="board-1",
                    column_configs=[
                        ScenarioColumnConfig(
                            name="Testing",
                            type="automated",
                            agent_id="qa_engineer",
                            repair_cycle_agents=RepairCycleAgentConfigModel(
                                test_execution="qa_engineer",
                                code_fix="senior_software_engineer",
                                env_rebuild="devops_engineer",
                            ),
                        ),
                    ],
                ),
            ],
        )
        assert config is not None

    def test_invalid_config_unknown_agent_in_test_execution(self) -> None:
        """ValidationError raised when test_execution references undefined agent."""
        with pytest.raises(ValidationError) as exc_info:
            OrchestratorConfigModel(
                name="test",
                agents=[
                    ScenarioAgentModel(name="qa_engineer"),
                ],
                board_policies=[
                    ScenarioBoardPolicyModel(
                        board_id="board-1",
                        column_configs=[
                            ScenarioColumnConfig(
                                name="Testing",
                                type="automated",
                                agent_id="qa_engineer",
                                repair_cycle_agents=RepairCycleAgentConfigModel(
                                    test_execution="unknown_agent",
                                ),
                            ),
                        ],
                    ),
                ],
            )

        error_str = str(exc_info.value)
        assert "unknown_agent" in error_str
        assert "not defined" in error_str

    def test_invalid_config_unknown_agent_in_code_fix(self) -> None:
        """ValidationError raised when code_fix references undefined agent."""
        with pytest.raises(ValidationError) as exc_info:
            OrchestratorConfigModel(
                name="test",
                agents=[
                    ScenarioAgentModel(name="qa_engineer"),
                ],
                board_policies=[
                    ScenarioBoardPolicyModel(
                        board_id="board-1",
                        column_configs=[
                            ScenarioColumnConfig(
                                name="Testing",
                                type="automated",
                                agent_id="qa_engineer",
                                repair_cycle_agents=RepairCycleAgentConfigModel(
                                    code_fix="unknown_fixer",
                                ),
                            ),
                        ],
                    ),
                ],
            )

        error_str = str(exc_info.value)
        assert "unknown_fixer" in error_str
        assert "not defined" in error_str

    def test_invalid_config_unknown_agent_in_env_rebuild(self) -> None:
        """ValidationError raised when env_rebuild references undefined agent."""
        with pytest.raises(ValidationError) as exc_info:
            OrchestratorConfigModel(
                name="test",
                agents=[
                    ScenarioAgentModel(name="qa_engineer"),
                ],
                board_policies=[
                    ScenarioBoardPolicyModel(
                        board_id="board-1",
                        column_configs=[
                            ScenarioColumnConfig(
                                name="Testing",
                                type="automated",
                                agent_id="qa_engineer",
                                repair_cycle_agents=RepairCycleAgentConfigModel(
                                    env_rebuild="devops_unknown",
                                ),
                            ),
                        ],
                    ),
                ],
            )

        error_str = str(exc_info.value)
        assert "devops_unknown" in error_str
        assert "not defined" in error_str

    def test_invalid_config_multiple_undefined_agents(self) -> None:
        """ValidationError raised for first undefined agent (validation stops at first)."""
        with pytest.raises(ValidationError) as exc_info:
            OrchestratorConfigModel(
                name="test",
                agents=[
                    ScenarioAgentModel(name="qa_engineer"),
                ],
                board_policies=[
                    ScenarioBoardPolicyModel(
                        board_id="board-1",
                        column_configs=[
                            ScenarioColumnConfig(
                                name="Testing",
                                type="automated",
                                agent_id="qa_engineer",
                                repair_cycle_agents=RepairCycleAgentConfigModel(
                                    test_execution="unknown1",
                                    code_fix="unknown2",
                                ),
                            ),
                        ],
                    ),
                ],
            )

        error_str = str(exc_info.value)
        # Should catch at least one of the undefined agents
        assert "unknown1" in error_str or "unknown2" in error_str

    def test_invalid_config_undefined_agent_in_systemic_analysis(self) -> None:
        """ValidationError raised when systemic_analysis references undefined agent."""
        with pytest.raises(ValidationError) as exc_info:
            OrchestratorConfigModel(
                name="test",
                agents=[
                    ScenarioAgentModel(name="qa_engineer"),
                ],
                board_policies=[
                    ScenarioBoardPolicyModel(
                        board_id="board-1",
                        column_configs=[
                            ScenarioColumnConfig(
                                name="Testing",
                                type="automated",
                                agent_id="qa_engineer",
                                repair_cycle_agents=RepairCycleAgentConfigModel(
                                    systemic_analysis="architect_undefined",
                                ),
                            ),
                        ],
                    ),
                ],
            )

        error_str = str(exc_info.value)
        assert "architect_undefined" in error_str

    def test_valid_config_with_multiple_columns_repair_cycle_agents(self) -> None:
        """Multiple columns can each have their own repair_cycle_agents config."""
        config = OrchestratorConfigModel(
            name="test",
            agents=[
                ScenarioAgentModel(name="qa_engineer"),
                ScenarioAgentModel(name="coder"),
                ScenarioAgentModel(name="devops_engineer"),
            ],
            board_policies=[
                ScenarioBoardPolicyModel(
                    board_id="board-1",
                    column_configs=[
                        ScenarioColumnConfig(
                            name="Testing",
                            type="automated",
                            agent_id="qa_engineer",
                            repair_cycle_agents=RepairCycleAgentConfigModel(
                                test_execution="qa_engineer",
                            ),
                        ),
                        ScenarioColumnConfig(
                            name="Fix Code",
                            type="automated",
                            agent_id="coder",
                            repair_cycle_agents=RepairCycleAgentConfigModel(
                                code_fix="coder",
                            ),
                        ),
                        ScenarioColumnConfig(
                            name="Rebuild",
                            type="automated",
                            agent_id="devops_engineer",
                            repair_cycle_agents=RepairCycleAgentConfigModel(
                                env_rebuild="devops_engineer",
                            ),
                        ),
                    ],
                ),
            ],
        )
        assert config is not None

    def test_valid_all_repair_cycle_agent_fields(self) -> None:
        """Config with all repair_cycle_agents fields populated passes validation."""
        config = OrchestratorConfigModel(
            name="test",
            agents=[
                ScenarioAgentModel(name="qa_engineer"),
                ScenarioAgentModel(name="senior_software_engineer"),
                ScenarioAgentModel(name="architect"),
                ScenarioAgentModel(name="platform_engineer"),
                ScenarioAgentModel(name="devops_engineer"),
            ],
            board_policies=[
                ScenarioBoardPolicyModel(
                    board_id="board-1",
                    column_configs=[
                        ScenarioColumnConfig(
                            name="Testing",
                            type="automated",
                            agent_id="qa_engineer",
                            repair_cycle_agents=RepairCycleAgentConfigModel(
                                test_execution="qa_engineer",
                                code_fix="senior_software_engineer",
                                systemic_analysis="architect",
                                systemic_fix="platform_engineer",
                                env_rebuild="devops_engineer",
                                env_verification="qa_engineer",
                            ),
                        ),
                    ],
                ),
            ],
        )
        assert config is not None

    def test_error_message_includes_board_and_column_context(self) -> None:
        """Error message includes board_id and column name for context."""
        with pytest.raises(ValidationError) as exc_info:
            OrchestratorConfigModel(
                name="test",
                agents=[
                    ScenarioAgentModel(name="qa_engineer"),
                ],
                board_policies=[
                    ScenarioBoardPolicyModel(
                        board_id="board-production",
                        column_configs=[
                            ScenarioColumnConfig(
                                name="Test Stage",
                                type="automated",
                                agent_id="qa_engineer",
                                repair_cycle_agents=RepairCycleAgentConfigModel(
                                    code_fix="undefined_agent",
                                ),
                            ),
                        ],
                    ),
                ],
            )

        error_str = str(exc_info.value)
        assert "board-production" in error_str or "board_id" in error_str
        assert "Test Stage" in error_str or "column" in error_str
        assert "undefined_agent" in error_str
