"""Test configuration and fixtures for param-lsp tests."""

from __future__ import annotations

import pytest

from param_lsp.analyzer import ParamAnalyzer
from param_lsp.server import ParamLanguageServer


@pytest.fixture(autouse=True)
def disable_cache_for_tests(monkeypatch):
    """Disable cache for all tests by default."""
    monkeypatch.setenv("PARAM_LSP_DISABLE_CACHE", "1")


@pytest.fixture
def analyzer():
    """Create a fresh ParamAnalyzer instance for testing."""
    return ParamAnalyzer()


@pytest.fixture
def lsp_server():
    """Create a fresh ParamLanguageServer instance for testing."""
    return ParamLanguageServer("test-param-lsp", "v0.1.0")


@pytest.fixture
def sample_param_code():
    """Sample param code for testing."""
    return """
import param

class TestClass(param.Parameterized):
    string_param = param.String(default="hello", doc="A string parameter")
    int_param = param.Integer(default=5, bounds=(0, 10), doc="An integer parameter")
    bool_param = param.Boolean(default=True, doc="A boolean parameter")
    number_param = param.Number(default=1.5, bounds=(0.0, 5.0), inclusive_bounds=(False, True))
"""


@pytest.fixture
def sample_runtime_assignment_code():
    """Sample code with runtime assignments for testing."""
    return """
import param

class TestClass(param.Parameterized):
    string_param = param.String(default="hello")
    int_param = param.Integer(default=5, bounds=(0, 10))
    bool_param = param.Boolean(default=True)

instance = TestClass()
instance.string_param = 123  # Type error
instance.int_param = -5      # Bounds error
instance.bool_param = "yes"  # Boolean type error
"""


@pytest.fixture
def sample_invalid_param_code():
    """Sample param code with various errors for testing."""
    return """
import param

class TestClass(param.Parameterized):
    # Type mismatches
    string_with_int = param.String(default=123)
    bool_with_int = param.Boolean(default=1)
    int_with_str = param.Integer(default="not_int")

    # Bounds violations
    int_outside_bounds = param.Integer(default=15, bounds=(0, 10))
    number_outside_bounds = param.Number(default=0, bounds=(1, 5), inclusive_bounds=(False, True))

    # Invalid bounds
    invalid_bounds = param.Integer(bounds=(10, 5))  # min > max
"""
