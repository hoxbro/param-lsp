"""
Minimal reproducible example for 'objects' parameter inheritance bug.

This reproduces the issue where @param.depends references an inherited parameter
but the analyzer doesn't find it.
"""

from __future__ import annotations

import param


class ParentClass(param.Parameterized):
    """Parent class with 'objects' parameter."""

    objects = param.List(default=[])


class ChildClass(ParentClass):
    """Child class that depends on inherited 'objects' parameter."""

    disabled = param.Boolean(default=False)

    @param.depends("disabled", "objects", watch=True)
    def _update_state(self) -> None:
        """Method that depends on both local and inherited parameters."""
