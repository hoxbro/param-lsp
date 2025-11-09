from __future__ import annotations


def get_class(param_classes, base_name):
    """Get class by base name from param_classes dict with unique keys."""
    for key in param_classes:
        if key.startswith(f"{base_name}:"):
            return param_classes[key]
    return None
