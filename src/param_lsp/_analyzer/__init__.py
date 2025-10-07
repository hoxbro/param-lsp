"""
Analyzer module - refactored components of the main ParamAnalyzer.

This package contains the modular components that were extracted from the
monolithic analyzer.py file to improve maintainability and testability.
"""

from __future__ import annotations

from .import_resolver import ImportResolver
from .static_external_analyzer import ExternalClassInspector
from .validation import ParameterValidator

__all__ = [
    "ExternalClassInspector",
    "ImportResolver",
    "ParameterValidator",
]
