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
