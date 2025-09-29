"""Constants and static configurations for the param-lsp package."""

from __future__ import annotations

# =============================================================================
# ANALYZER CONSTANTS
# =============================================================================

# Global configuration for allowed external libraries for runtime introspection
ALLOWED_EXTERNAL_LIBRARIES = {
    "panel",
    "holoviews",
    "param",
}

# Parameter type mapping for type checking and validation
PARAM_TYPE_MAP = {
    "Number": (int, float),
    "Integer": int,
    "String": str,
    "Boolean": bool,
    "List": list,
    "Tuple": tuple,
    "Dict": dict,
    "Array": (list, tuple),
    "Range": (int, float),
    "Date": str,
    "CalendarDate": str,
    "Filename": str,
    "Foldername": str,
    "Path": str,
    "Color": str,
    "Selector": object,
    "ObjectSelector": object,
    "ListSelector": list,
}

# Parameter types that are considered to be numeric
NUMERIC_PARAMETER_TYPES = {"Integer", "Number", "Float"}

# Parameter types that are considered containers
CONTAINER_PARAMETER_TYPES = {"List", "Tuple"}

# Common param parameter types
PARAM_TYPES = {
    "Parameter",
    "Number",
    "Integer",
    "String",
    "Boolean",
    "List",
    "Tuple",
    "Dict",
    "Array",
    "DataFrame",
    "Series",
    "Range",
    "Date",
    "CalendarDate",
    "Filename",
    "Foldername",
    "Path",
    "Color",
    "Composite",
    "Dynamic",
    "Event",
    "Action",
    "FileSelector",
    "ListSelector",
    "ObjectSelector",
    "Selector",
}

# Selector parameter types that support objects
SELECTOR_PARAM_TYPES = ("Selector", "ObjectSelector", "ListSelector")

# =============================================================================
# LSP SERVER CONSTANTS
# =============================================================================

# Parameter namespace methods documentation
PARAM_NAMESPACE_METHODS = {
    "values": {
        "signature": "values()",
        "description": "Returns a dictionary mapping parameter names to their current values for all parameters of this Parameterized object.",
        "example": "obj.param.values()\n# Output: {'x': 5, 'y': 'hello', 'z': True}",
        "returns": "Dict[str, Any] (actual parameter values)",
        "note": "Returns the actual current parameter values, not parameter names or objects",
    },
    "objects": {
        "signature": "objects()",
        "description": "Returns a dictionary mapping parameter names to their Parameter objects for all parameters of this Parameterized object.",
        "example": "obj.param.objects()\n# Output: {'x': Integer(default=5), 'y': String(default='hello'), 'z': Boolean(default=True)}",
        "returns": "Dict[str, Parameter] (parameter objects with metadata)",
        "note": "Returns the Parameter objects themselves (with metadata), not the current parameter values",
    },
    "update": {
        "signature": "update(**params)",
        "description": "Update multiple parameters at once by passing parameter names as keyword arguments.",
        "example": "obj.param.update(x=10, y='new_value')\n# Updates multiple parameters simultaneously",
        "returns": "None",
        "note": "Efficiently updates multiple parameters with validation and triggers watchers",
    },
}

# Reactive expression methods documentation
RX_METHODS_DOCS = {
    "and_": {
        "signature": "and_(other)",
        "description": "Returns a reactive expression that applies the `and` operator between this expression and another value.",
        "example": "param_rx.and_(other_value)",
    },
    "bool": {
        "signature": "bool()",
        "description": "Returns a reactive expression that applies the `bool()` function to this expression's value.",
        "example": "param_rx.bool()",
    },
    "in_": {
        "signature": "in_(container)",
        "description": "Returns a reactive expression that checks if this expression's value is in the given container.",
        "example": "param_rx.in_([1, 2, 3])",
    },
    "is_": {
        "signature": "is_(other)",
        "description": "Returns a reactive expression that checks object identity between this expression and another value using the `is` operator.",
        "example": "param_rx.is_(None)",
    },
    "is_not": {
        "signature": "is_not(other)",
        "description": "Returns a reactive expression that checks absence of object identity using the `is not` operator.",
        "example": "param_rx.is_not(None)",
    },
    "len": {
        "signature": "len()",
        "description": "Returns a reactive expression that applies the `len()` function to this expression's value.",
        "example": "param_rx.len()",
    },
    "map": {
        "signature": "map(func, *args, **kwargs)",
        "description": "Returns a reactive expression that maps a function over the collection items in this expression's value.",
        "example": "param_rx.map(lambda x: x * 2)",
    },
    "or_": {
        "signature": "or_(other)",
        "description": "Returns a reactive expression that applies the `or` operator between this expression and another value.",
        "example": "param_rx.or_(default_value)",
    },
    "pipe": {
        "signature": "pipe(func, *args, **kwargs)",
        "description": "Returns a reactive expression that pipes this expression's value into the given function.",
        "example": "param_rx.pipe(str.upper)",
    },
    "updating": {
        "signature": "updating()",
        "description": "Returns a boolean reactive expression indicating whether this expression is currently updating.",
        "example": "param_rx.updating()",
    },
    "when": {
        "signature": "when(*conditions)",
        "description": "Returns a reactive expression that only updates when the specified conditions are met.",
        "example": "param_rx.when(condition_rx)",
    },
    "where": {
        "signature": "where(condition, other)",
        "description": "Returns a reactive expression implementing a ternary conditional (like numpy.where).",
        "example": "param_rx.where(condition, true_value)",
    },
    "watch": {
        "signature": "watch(callback, onlychanged=True)",
        "description": "Triggers a side-effect callback when this reactive expression outputs a new event.",
        "example": "param_rx.watch(lambda x: print(f'Value changed to {x}'))",
    },
    "value": {
        "signature": "value",
        "description": "Property to get or set the current value of this reactive expression.",
        "example": "current_val = param_rx.value",
    },
}

# Parameter arguments for param class definitions
PARAM_ARGS = [
    ("default", "Default value for the parameter"),
    ("doc", "Documentation string describing the parameter"),
    ("label", "Human-readable name for the parameter"),
    ("precedence", "Numeric precedence for parameter ordering"),
    ("instantiate", "Whether to instantiate the default value per instance"),
    ("constant", "Whether the parameter value cannot be changed after construction"),
    ("readonly", "Whether the parameter value can be modified after construction"),
    ("allow_None", "Whether None is allowed as a valid value"),
    ("per_instance", "Whether the parameter is stored per instance"),
    ("bounds", "Tuple of (min, max) values for numeric parameters"),
    ("inclusive_bounds", "Tuple of (left_inclusive, right_inclusive) booleans"),
    ("softbounds", "Tuple of (soft_min, soft_max) for suggested ranges"),
]

# Parameter namespace methods for completions
PARAM_METHODS = [
    {
        "name": "objects",
        "insert_text": "objects()",
        "documentation": "Returns a dictionary of (parameter_name, parameter_object) pairs for all parameters of this Parameterized object.",
        "detail": "param.objects() method",
    },
    {
        "name": "values",
        "insert_text": "values()",
        "documentation": "Returns an iterator of parameter values for all parameters of this Parameterized object.",
        "detail": "param.values() method",
    },
    {
        "name": "update",
        "insert_text": "update($0)",
        "documentation": "Update multiple parameters at once by passing parameter names as keyword arguments.",
        "detail": "param.update() method",
    },
]

# Common Parameter attributes (available on all parameter types)
COMMON_PARAMETER_ATTRIBUTES = {
    "default": "Default value of the parameter",
    "doc": "Documentation string for the parameter",
    "name": "Name of the parameter",
    "label": "Human-readable label for the parameter",
    "owner": "The Parameterized class that owns this parameter",
    "allow_None": "Whether the parameter allows None values",
    "readonly": "Whether the parameter is read-only",
    "constant": "Whether the parameter is constant",
    "instantiate": "Whether to instantiate the default value",
    "per_instance": "Whether the parameter is per-instance",
    "precedence": "Precedence level for GUI ordering",
    "watchers": "Dictionary of parameter watchers",
    "rx": "Reactive expression property for this parameter",
}

# Type-specific parameter attributes
TYPE_SPECIFIC_PARAMETER_ATTRIBUTES = {
    "numeric": {
        "bounds": "Valid range for numeric values (min, max)",
        "inclusive_bounds": "Whether bounds are inclusive (bool, bool)",
        "softbounds": "Soft bounds for validation",
        "step": "Step size for numeric input",
    },
    "string": {
        "regex": "Regular expression pattern for validation",
    },
    "container": {
        "item_type": "Type of items in the container",
        "bounds": "Length bounds (min, max)",
    },
}

# Parameter methods (empty for now, but ready for future additions)
PARAMETER_METHODS = {}

# Reactive expression methods for completions
RX_METHODS = {
    "and_": "Applies the `and` operator",
    "bool": "Reactive version of `bool()`",
    "in_": "Checks if value is in a collection",
    "is_": "Checks object identity",
    "is_not": "Checks absence of object identity",
    "len": "Returns length of object",
    "map": "Maps a function to collection items",
    "or_": "Applies the `or` operator",
    "pipe": "Pipes value into a function",
    "updating": "Indicates if expression is currently updating",
    "when": "Updates only when specific conditions are met",
    "where": "Reactive ternary conditional",
    "watch": "Triggers side-effect when expression outputs a new event",
}

# Reactive expression properties
RX_PROPERTIES = {
    "value": "Retrieves or sets the current value of the reactive expression",
}

# =============================================================================
# DEPRECATION WARNINGS
# =============================================================================

# Configuration for deprecated parameter types
DEPRECATED_PARAMETER_TYPES = {
    "ObjectSelector": {
        "replacement": "Selector",
        "message": "ObjectSelector is deprecated, use Selector instead",
        "version": "param 2.0+",
    }
}
