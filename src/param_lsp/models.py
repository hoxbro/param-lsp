"""Data models for param-lsp analyzer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParameterInfo:
    """Information about a single parameter."""

    name: str
    cls: str
    bounds: tuple | None = None
    doc: str | None = None
    allow_None: bool = False
    default: str | None = None
    location: dict[str, Any] | None = None
    objects: list[Any] | None = None  # For Selector parameters
    item_type: type | None = None  # For List parameters
    length: int | None = None  # For Tuple parameters


@dataclass
class ParameterizedInfo:
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
