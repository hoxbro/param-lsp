"""Test configuration and fixtures for param-lsp tests."""

from __future__ import annotations

import logging
from functools import cache
from unittest.mock import patch

import pytest

from param_lsp.analyzer import ParamAnalyzer
from param_lsp.server import ParamLanguageServer

logger = logging.getLogger(__name__)


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


@cache
def _get_all_libraries_info_from_env(
    library_names: tuple[str, ...],
) -> dict[str, dict[str, str | list[str]]]:
    """Return actual library info from current environment (cached)."""
    import importlib.metadata

    results = {}
    for lib_name in library_names:
        try:
            version = importlib.metadata.version(lib_name)
            metadata = importlib.metadata.metadata(lib_name)
            requires = list(metadata.get_all("Requires-Dist") or [])
            results[lib_name] = {"version": version, "requires": requires}
        except Exception as e:
            # Skip libraries that don't exist
            logger.debug(f"Skipping library {lib_name}: {e}")
            continue
    return results


@pytest.fixture(autouse=True)
def mock_get_all_libraries_info():
    """Mock get_all_libraries_info to avoid slow subprocess calls in all tests."""

    def wrapper(library_names: list[str]) -> dict[str, dict[str, str | list[str]]]:
        return _get_all_libraries_info_from_env(tuple(library_names))

    with patch(
        "param_lsp._analyzer.python_environment.PythonEnvironment.get_all_libraries_info"
    ) as mock:
        mock.side_effect = wrapper
        yield mock


@pytest.fixture
def analyzer():
    """Create a fresh ParamAnalyzer instance for testing."""
    return ParamAnalyzer()


@pytest.fixture
def lsp_server():
    """Create a fresh ParamLanguageServer instance for testing."""
    return ParamLanguageServer("test-param-lsp", "v0.1.0")
