"""Data models for param-lsp analyzer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParameterInfo:
    """Information about a single parameter."""

    name: str
    param_type: str
    bounds: tuple | None = None
    doc: str | None = None
    allow_none: bool = False
    default: str | None = None
    location: dict[str, Any] | None = None


@dataclass
class ParamClassInfo:
    """Information about a Parameterized class."""

    name: str
    parameters: dict[str, ParameterInfo] = field(default_factory=dict)

    def get_parameter_names(self) -> list[str]:
        """Get list of parameter names."""
        return list(self.parameters.keys())

    def get_parameter(self, name: str) -> ParameterInfo | None:
        """Get parameter info by name."""
        return self.parameters.get(name)

    def add_parameter(self, param_info: ParameterInfo) -> None:
        """Add a parameter to this class."""
        self.parameters[param_info.name] = param_info

    def merge_parameters(self, other_params: dict[str, ParameterInfo]) -> None:
        """Merge parameters from another source, with current taking precedence."""
        for name, param_info in other_params.items():
            if name not in self.parameters:
                self.parameters[name] = param_info


def convert_to_legacy_format(result):
    """Convert new dataclass format to legacy dict format for tests."""
    param_classes_dict = result["param_classes"]

    return {
        "param_classes": set(param_classes_dict.keys()),
        "param_parameters": {
            name: info.get_parameter_names() for name, info in param_classes_dict.items()
        },
        "param_parameter_types": {
            name: {p.name: p.param_type for p in info.parameters.values()}
            for name, info in param_classes_dict.items()
        },
        "param_parameter_bounds": {
            name: {p.name: p.bounds for p in info.parameters.values() if p.bounds}
            for name, info in param_classes_dict.items()
        },
        "param_parameter_docs": {
            name: {p.name: p.doc for p in info.parameters.values() if p.doc is not None}
            for name, info in param_classes_dict.items()
        },
        "param_parameter_allow_none": {
            name: {p.name: p.allow_none for p in info.parameters.values()}
            for name, info in param_classes_dict.items()
        },
        "param_parameter_defaults": {
            name: {p.name: p.default for p in info.parameters.values() if p.default}
            for name, info in param_classes_dict.items()
        },
        "param_parameter_locations": {
            name: {p.name: p.location for p in info.parameters.values() if p.location}
            for name, info in param_classes_dict.items()
        },
        # Pass through other keys
        "imports": result.get("imports", {}),
        "type_errors": result.get("type_errors", []),
    }
