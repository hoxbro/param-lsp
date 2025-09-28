"""
Analyzer module - refactored components of the main ParamAnalyzer.

This package contains the modular components that were extracted from the
monolithic analyzer.py file to improve maintainability and testability.
"""

from __future__ import annotations

from .external_class_inspector import ExternalClassInspector
from .import_resolver import ImportResolver
from .type_checker import TypeChecker

__all__ = [
    "ExternalClassInspector",
    "ImportResolver",
    "TypeChecker",
]
