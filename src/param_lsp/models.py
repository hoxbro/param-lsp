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


@dataclass
class ExternalClassInfo:
    """Wrapper for external class parameter information with conversion utilities.

    This class provides a clean interface for working with external Param classes,
    handling both dataclass and legacy format conversions seamlessly.
    """

    class_name: str
    param_class_info: ParamClassInfo

    @classmethod
    def from_param_class_info(cls, param_class_info: ParamClassInfo) -> ExternalClassInfo:
        """Create from a ParamClassInfo object."""
        return cls(class_name=param_class_info.name, param_class_info=param_class_info)

    @classmethod
    def from_legacy_dict(cls, class_name: str, legacy_data: dict) -> ExternalClassInfo:
        """Create from legacy dictionary format."""
        param_class_info = ParamClassInfo(name=class_name)

        # Extract parameter data from legacy format
        parameters = legacy_data.get("parameters", [])
        parameter_types = legacy_data.get("parameter_types", {})
        parameter_docs = legacy_data.get("parameter_docs", {})
        parameter_bounds = legacy_data.get("parameter_bounds", {})
        parameter_allow_none = legacy_data.get("parameter_allow_none", {})
        parameter_defaults = legacy_data.get("parameter_defaults", {})
        parameter_locations = legacy_data.get("parameter_locations", {})

        for param_name in parameters:
            param_info = ParameterInfo(
                name=param_name,
                param_type=parameter_types.get(param_name, "Unknown"),
                bounds=parameter_bounds.get(param_name),
                doc=parameter_docs.get(param_name),
                allow_none=parameter_allow_none.get(param_name, False),
                default=parameter_defaults.get(param_name),
                location=parameter_locations.get(param_name),
            )
            param_class_info.add_parameter(param_info)

        return cls(class_name=class_name, param_class_info=param_class_info)

    def to_legacy_dict(self) -> dict:
        """Convert to legacy dictionary format for compatibility."""
        return {
            "parameters": self.param_class_info.get_parameter_names(),
            "parameter_types": {
                p.name: p.param_type for p in self.param_class_info.parameters.values()
            },
            "parameter_docs": {
                p.name: p.doc
                for p in self.param_class_info.parameters.values()
                if p.doc is not None
            },
            "parameter_bounds": {
                p.name: p.bounds for p in self.param_class_info.parameters.values() if p.bounds
            },
            "parameter_allow_none": {
                p.name: p.allow_none for p in self.param_class_info.parameters.values()
            },
            "parameter_defaults": {
                p.name: p.default for p in self.param_class_info.parameters.values() if p.default
            },
            "parameter_locations": {
                p.name: p.location for p in self.param_class_info.parameters.values() if p.location
            },
        }

    def get_parameter_names(self) -> list[str]:
        """Get list of parameter names."""
        return self.param_class_info.get_parameter_names()

    @property
    def parameters(self) -> dict[str, ParameterInfo]:
        """Get parameters dict for direct access."""
        return self.param_class_info.parameters

    def get_parameter(self, name: str) -> ParameterInfo | None:
        """Get parameter info by name."""
        return self.param_class_info.get_parameter(name)
