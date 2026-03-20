"""
Tests for adapter registry signature validation.

Tests the _validate_adapter_implements_interface function which validates that
adapters implement all required interface methods with matching signatures.
"""

import inspect
from abc import ABC, abstractmethod
from typing import Any

import pytest

from codetoreum.infrastructure.adapters.registries import (
    _get_interface_signature,
    _get_return_type_name,
    _is_mock_or_test_adapter,
    _validate_adapter_implements_interface,
)
from codetoreum.ports.output.board_service import IBoardService


class ISimplePort(ABC):
    """Test interface with simple methods."""

    @abstractmethod
    def simple_method(self, param1: str, param2: int) -> bool:
        """A simple method."""
        pass

    @abstractmethod
    def method_with_defaults(self, param1: str, param2: int = 10) -> None:
        """Method with default parameters."""
        pass


class IMockPortInTestModule(ABC):
    """Test interface in a mock module."""

    @abstractmethod
    def test_method(self) -> str:
        """Test method."""
        pass


class ValidAdapterImpl:
    """Valid adapter with correct signature."""

    def simple_method(self, param1: str, param2: int) -> bool:
        return True

    def method_with_defaults(self, param1: str, param2: int = 10) -> None:
        pass


class WrongParameterCountAdapter:
    """Adapter with wrong parameter count."""

    __module__ = "codetoreum.adapters.testing.mock"  # Mark as test adapter for strict validation

    def simple_method(self, param1: str) -> bool:
        return True

    def method_with_defaults(self, param1: str, param2: int = 10) -> None:
        pass


class WrongParameterNameAdapter:
    """Adapter with wrong parameter name."""

    __module__ = "codetoreum.adapters.testing.mock"  # Mark as test adapter for strict validation

    def simple_method(self, param1: str, wrong_name: int) -> bool:
        return True

    def method_with_defaults(self, param1: str, param2: int = 10) -> None:
        pass


class MissingMethodAdapter:
    """Adapter missing a required method."""

    __module__ = "codetoreum.adapters.testing.mock"  # Mark as test adapter for strict validation

    def simple_method(self, param1: str, param2: int) -> bool:
        return True


class TestGetInterfaceSignature:
    """Tests for _get_interface_signature function."""

    def test_extracts_method_signature(self):
        """Test that signature is correctly extracted from interface."""
        sig = _get_interface_signature(ISimplePort, "simple_method")
        assert isinstance(sig, inspect.Signature)
        assert len(sig.parameters) == 3  # self, param1, param2

    def test_raises_on_missing_method(self):
        """Test that ValueError is raised for missing method."""
        with pytest.raises(ValueError, match="Method nonexistent not found"):
            _get_interface_signature(ISimplePort, "nonexistent")

    def test_signature_includes_annotations(self):
        """Test that signature includes parameter annotations."""
        sig = _get_interface_signature(ISimplePort, "simple_method")
        params = list(sig.parameters.values())
        assert params[1].annotation == str  # param1
        assert params[2].annotation == int  # param2


class TestIsMockOrTestAdapter:
    """Tests for _is_mock_or_test_adapter function."""

    def test_identifies_mock_adapters(self):
        """Test that mock adapters are identified."""
        # Create a class in a mock module context
        class MockAdapter:
            pass

        MockAdapter.__module__ = "codetoreum.adapters.testing.mock_board"
        assert _is_mock_or_test_adapter(MockAdapter) is True

    def test_identifies_testing_adapters(self):
        """Test that testing adapters are identified."""

        class TestAdapter:
            pass

        TestAdapter.__module__ = "codetoreum.infrastructure.adapters.testing"
        assert _is_mock_or_test_adapter(TestAdapter) is True

    def test_identifies_in_memory_adapters(self):
        """Test that in-memory adapters are identified."""

        class InMemoryAdapter:
            pass

        InMemoryAdapter.__module__ = "codetoreum.adapters.testing.in_memory_board"
        assert _is_mock_or_test_adapter(InMemoryAdapter) is True

    def test_non_test_adapters_not_identified_as_test(self):
        """Test that production adapters are not identified as test adapters."""

        class ProductionAdapter:
            pass

        ProductionAdapter.__module__ = "codetoreum.adapters.secondary.github"
        assert _is_mock_or_test_adapter(ProductionAdapter) is False


class TestGetReturnTypeName:
    """Tests for _get_return_type_name function."""

    def test_extracts_class_name_from_string(self):
        """Test extraction from string forward reference."""
        assert _get_return_type_name("ClassName") == "ClassName"

    def test_handles_generic_string_types(self):
        """Test handling of generic string types."""
        assert _get_return_type_name("list[str]") == "list"

    def test_extracts_name_from_type_object(self):
        """Test extraction from actual type object."""
        assert _get_return_type_name(str) == "str"
        assert _get_return_type_name(int) == "int"

    def test_handles_generic_type_objects(self):
        """Test handling of generic type objects."""
        from typing import List

        result = _get_return_type_name(List[str])
        assert result == "list"

    def test_handles_custom_class_types(self):
        """Test handling of custom class types."""

        class CustomClass:
            pass

        assert _get_return_type_name(CustomClass) == "CustomClass"


class TestValidateAdapterImplementsInterface:
    """Tests for _validate_adapter_implements_interface function."""

    def test_valid_adapter_passes_validation(self):
        """Test that valid adapter with matching signature passes."""
        result = _validate_adapter_implements_interface(ValidAdapterImpl, ISimplePort)
        assert result is True

    def test_missing_method_raises_error(self):
        """Test that missing method raises ValueError."""
        with pytest.raises(ValueError, match="missing methods"):
            _validate_adapter_implements_interface(MissingMethodAdapter, ISimplePort)

    def test_wrong_parameter_count_raises_error(self):
        """Test that wrong parameter count raises ValueError."""
        with pytest.raises(ValueError, match="expected 2 parameters"):
            _validate_adapter_implements_interface(
                WrongParameterCountAdapter, ISimplePort
            )

    def test_wrong_parameter_name_raises_error(self):
        """Test that wrong parameter name raises ValueError."""
        with pytest.raises(ValueError, match="parameter 'param2'"):
            _validate_adapter_implements_interface(
                WrongParameterNameAdapter, ISimplePort
            )

    def test_strict_mode_for_mock_adapters(self):
        """Test that mock adapters use strict validation."""

        class TestAdapter(ISimplePort):
            __module__ = "codetoreum.adapters.testing.mock"

            def simple_method(self, param1: str, param2: int) -> bool:
                return True

            def method_with_defaults(
                self, param1: str, param2: int = 10
            ) -> None:
                pass

        # Should be strict for mock adapters
        assert _is_mock_or_test_adapter(TestAdapter) is True

    def test_lenient_mode_for_production_adapters(self):
        """Test that production adapters use lenient validation."""

        class ProductionAdapter(ISimplePort):
            __module__ = "codetoreum.adapters.secondary.github"

            def simple_method(self, param1: str, param2: int) -> bool:
                return True

            def method_with_defaults(
                self, param1: str, param2: int = 10
            ) -> None:
                pass

        # Should be lenient for production adapters
        assert _is_mock_or_test_adapter(ProductionAdapter) is False

    def test_real_interface_board_service(self):
        """Test validation against real IBoardService interface."""
        from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter

        # Mock adapter should pass validation
        result = _validate_adapter_implements_interface(MockBoardAdapter, IBoardService)
        assert result is True

    def test_with_any_type_bypasses_strict_checking(self):
        """Test that Any type in adapter bypasses strict type checking."""

        class FlexibleAdapter(ISimplePort):
            __module__ = "codetoreum.adapters.testing.mock"

            def simple_method(self, param1: Any, param2: Any) -> Any:
                return True

            def method_with_defaults(self, param1: str, param2: int = 10) -> None:
                pass

        # Should pass despite type differences because adapter uses Any
        result = _validate_adapter_implements_interface(FlexibleAdapter, ISimplePort)
        assert result is True
