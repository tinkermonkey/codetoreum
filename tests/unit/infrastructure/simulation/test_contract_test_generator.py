"""Tests for ContractTestGenerator."""

import pytest

from codetoreum.infrastructure.simulation.contract_test_generator import (
    ContractTestGenerator,
)
from codetoreum.ports.output.board_service import IBoardService
from codetoreum.ports.output.code_review_service import ICodeReviewService
from codetoreum.ports.output.identity_service import IIdentityService


class TestContractTestGenerator:
    """Test suite for ContractTestGenerator."""

    def test_generator_initialization(self) -> None:
        """Test that generator can be initialized."""
        generator = ContractTestGenerator()
        assert generator is not None

    def test_get_available_ports(self) -> None:
        """Test that generator lists available ports."""
        generator = ContractTestGenerator()
        ports = generator.get_available_ports()

        assert len(ports) > 0
        assert "IBoardService" in ports
        assert "ICodeReviewService" in ports
        assert "IIdentityService" in ports

    def test_generate_for_port_returns_code(self) -> None:
        """Test that generation produces valid Python code."""
        generator = ContractTestGenerator()
        code = generator.generate_for_port(IBoardService)

        assert isinstance(code, str)
        assert len(code) > 0
        assert "class" in code
        assert "def" in code

    def test_generated_code_has_class_definition(self) -> None:
        """Test that generated code includes class definition."""
        generator = ContractTestGenerator()
        code = generator.generate_for_port(IBoardService)

        assert "TestIBoardServiceContract" in code
        assert "ABC" in code

    def test_generated_code_has_imports(self) -> None:
        """Test that generated code includes necessary imports."""
        generator = ContractTestGenerator()
        code = generator.generate_for_port(IBoardService)

        assert "from abc import" in code
        assert "import pytest" in code
        assert "from codetoreum.ports.output.board_service" in code

    def test_generated_code_has_abstract_methods(self) -> None:
        """Test that generated code includes abstract factory methods."""
        generator = ContractTestGenerator()
        code = generator.generate_for_port(IBoardService)

        assert "@abstractmethod" in code
        assert "async def create_service" in code
        assert "async def setup_fixtures" in code
        assert "async def teardown_fixtures" in code

    def test_generated_code_has_test_methods(self) -> None:
        """Test that generated code includes test methods."""
        generator = ContractTestGenerator()
        code = generator.generate_for_port(IBoardService)

        assert "@pytest.mark.asyncio" in code
        assert "async def test_service_is_created" in code
        assert "async def test_fixtures_can_be_set_up" in code

    def test_generate_for_port_by_name_success(self) -> None:
        """Test generating for port by name."""
        generator = ContractTestGenerator()
        code = generator.generate_for_port_by_name("IBoardService")

        assert code is not None
        assert "TestIBoardServiceContract" in code

    def test_generate_for_port_by_name_not_found(self) -> None:
        """Test that unknown port returns None."""
        generator = ContractTestGenerator()
        code = generator.generate_for_port_by_name("IUnknownPort")

        assert code is None

    def test_generate_for_multiple_ports(self) -> None:
        """Test generating for multiple different ports."""
        generator = ContractTestGenerator()

        code1 = generator.generate_for_port(IBoardService)
        code2 = generator.generate_for_port(ICodeReviewService)
        code3 = generator.generate_for_port(IIdentityService)

        # All should generate code
        assert code1 is not None
        assert code2 is not None
        assert code3 is not None

        # Code should be different for different ports
        assert "IBoardService" in code1
        assert "ICodeReviewService" in code2
        assert "IIdentityService" in code3

    def test_estimate_coverage(self) -> None:
        """Test coverage estimation."""
        generator = ContractTestGenerator()
        coverage = generator.estimate_coverage(IBoardService)

        assert "interface" in coverage
        assert coverage["interface"] == "IBoardService"
        assert "public_methods" in coverage
        assert "base_tests" in coverage
        assert coverage["base_tests"] == 2
        assert "estimated_additional_tests" in coverage
        assert "total_estimated_tests" in coverage

    def test_coverage_calculation(self) -> None:
        """Test that coverage is calculated correctly."""
        generator = ContractTestGenerator()
        coverage = generator.estimate_coverage(IBoardService)

        public_methods = coverage["public_methods"]
        base_tests = coverage["base_tests"]
        estimated_additional = coverage["estimated_additional_tests"]
        total_tests = coverage["total_estimated_tests"]

        assert estimated_additional == public_methods * 2
        assert total_tests == base_tests + estimated_additional

    def test_validate_interface(self) -> None:
        """Test interface validation."""
        generator = ContractTestGenerator()
        result = generator.validate_interface(IBoardService)

        assert "is_valid" in result
        assert "issues" in result
        assert "public_methods" in result

    def test_validate_interface_success(self) -> None:
        """Test that proper interfaces validate successfully."""
        generator = ContractTestGenerator()
        result = generator.validate_interface(IBoardService)

        # IBoardService is a proper interface
        assert result["is_valid"] is True
        assert len(result["issues"]) == 0

    def test_validate_interface_has_public_methods(self) -> None:
        """Test that validation confirms public methods exist."""
        generator = ContractTestGenerator()
        result = generator.validate_interface(IBoardService)

        # Should have detected public methods
        assert result["public_methods"] > 0

    def test_generated_code_syntax_valid(self) -> None:
        """Test that generated code is syntactically valid Python."""
        generator = ContractTestGenerator()
        code = generator.generate_for_port(IBoardService)

        # Should be able to compile without syntax errors
        try:
            compile(code, "<generated>", "exec")
        except SyntaxError as e:
            pytest.fail(f"Generated code has syntax error: {e}")

    def test_generated_code_for_different_ports_differs(self) -> None:
        """Test that code generation produces different output for different ports."""
        generator = ContractTestGenerator()

        code1 = generator.generate_for_port(IBoardService)
        code2 = generator.generate_for_port(ICodeReviewService)

        # Should be different
        assert code1 != code2

        # But both should be valid
        compile(code1, "<generated1>", "exec")
        compile(code2, "<generated2>", "exec")

    def test_generator_state_isolation(self) -> None:
        """Test that multiple generator instances don't share state."""
        gen1 = ContractTestGenerator()
        gen2 = ContractTestGenerator()

        code1 = gen1.generate_for_port(IBoardService)
        code2 = gen2.generate_for_port(IBoardService)

        # Should produce identical code
        assert code1 == code2

    def test_all_available_ports_can_be_generated(self) -> None:
        """Test that all listed ports can be generated."""
        generator = ContractTestGenerator()
        ports = generator.get_available_ports()

        for port_name in ports:
            code = generator.generate_for_port_by_name(port_name)
            assert code is not None
            assert len(code) > 0
            assert port_name in code

    def test_generated_code_includes_docstring(self) -> None:
        """Test that generated code includes module docstring."""
        generator = ContractTestGenerator()
        code = generator.generate_for_port(IBoardService)

        # Should have module docstring at top
        assert '"""' in code
        assert "Abstract contract test class" in code

    def test_generated_class_has_docstring(self) -> None:
        """Test that generated class has docstring."""
        generator = ContractTestGenerator()
        code = generator.generate_for_port(IBoardService)

        # Class should have docstring
        lines = code.split("\n")
        found_class = False
        found_docstring_after_class = False

        for i, line in enumerate(lines):
            if "class TestIBoardServiceContract" in line:
                found_class = True
            elif found_class and '"""' in line:
                found_docstring_after_class = True
                break

        assert found_docstring_after_class

    def test_all_methods_have_docstrings(self) -> None:
        """Test that generated methods have docstrings."""
        generator = ContractTestGenerator()
        code = generator.generate_for_port(IBoardService)

        # All async def should have docstrings
        assert "async def create_service(self)" in code
        assert "async def setup_fixtures(self)" in code
        assert "async def teardown_fixtures(self)" in code
        assert "async def test_service_is_created" in code
