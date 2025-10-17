"""Test configuration and fixtures for param-lsp tests."""

from __future__ import annotations

from functools import cache
from unittest.mock import patch

import pytest

from param_lsp.analyzer import ParamAnalyzer
from param_lsp.server import ParamLanguageServer


@pytest.fixture(autouse=True)
def disable_cache_for_tests(monkeypatch):
    """Disable cache for all tests by default."""
    monkeypatch.setenv("PARAM_LSP_DISABLE_CACHE", "1")


@cache
def _get_library_version_from_env(library_name: str) -> str:
    """Return actual library version from current environment (cached)."""
    import importlib.metadata

    try:
        return importlib.metadata.version(library_name)
    except Exception:
        return "1.0.0"


@pytest.fixture(autouse=True)
def mock_get_library_version():
    """Mock _get_library_version to avoid slow subprocess calls in all tests."""
    with patch(
        "param_lsp._analyzer.static_external_analyzer.ExternalClassInspector._get_library_version"
    ) as mock:
        mock.side_effect = _get_library_version_from_env
        yield mock


@pytest.fixture
def analyzer():
    """Create a fresh ParamAnalyzer instance for testing."""
    return ParamAnalyzer()


@pytest.fixture
def lsp_server():
    """Create a fresh ParamLanguageServer instance for testing."""
    return ParamLanguageServer("test-param-lsp", "v0.1.0")
