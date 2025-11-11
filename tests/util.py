"""Utility functions for tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, overload

if TYPE_CHECKING:
    from param_lsp._analyzer.class_info import ParamClassInfo


@overload
def get_class(
    param_classes: dict[str, ParamClassInfo],
    base_name: str,
    raise_if_none: Literal[False] = False,
) -> ParamClassInfo | None: ...


@overload
def get_class(
    param_classes: dict[str, ParamClassInfo],
    base_name: str,
    raise_if_none: Literal[True],
) -> ParamClassInfo: ...


def get_class(
    param_classes: dict[str, ParamClassInfo],
    base_name: str,
    raise_if_none: bool = False,
) -> ParamClassInfo | None:
    """Get class by base name from param_classes dict with unique keys.

    Args:
        param_classes: Dictionary mapping unique keys (ClassName:LineNumber) to ParamClassInfo
        base_name: The base class name without line number suffix
        raise_if_none: If True, raise AssertionError when class not found. Defaults to False.

    Returns:
        ParamClassInfo if found, None otherwise (unless raise_if_none=True)

    Raises:
        AssertionError: If raise_if_none=True and class not found
    """
    for key, value in param_classes.items():
        if key.startswith(f"{base_name}:"):
            return value

    if raise_if_none:
        msg = f"Class '{base_name}' not found in param_classes"
        raise AssertionError(msg)

    return None
