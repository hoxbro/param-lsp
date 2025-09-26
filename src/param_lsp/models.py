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
    """Wrapper for external class parameter information.

    This class provides a clean interface for working with external Param classes
    using structured dataclass models.
    """

    class_name: str
    param_class_info: ParamClassInfo

    @classmethod
    def from_param_class_info(cls, param_class_info: ParamClassInfo) -> ExternalClassInfo:
        """Create from a ParamClassInfo object."""
        return cls(class_name=param_class_info.name, param_class_info=param_class_info)

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
