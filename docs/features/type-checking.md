# Type Checking & Diagnostics

param-lsp provides real-time validation of parameter values, types, and constraints with immediate error feedback.

## Bounds Checking

Immediate feedback when parameter values violate bounds:

=== "Screenshot"

    <!-- TODO: Add screenshot showing error diagnostics for:
    widget = Widget(width=1000, opacity=1.5)
    with red squiggly lines under the invalid values and error tooltips
    -->

    **Screenshot needed:** Error diagnostics with red squiggly lines under invalid values and error tooltips

=== "Code"

    ```python
    import param

    class Widget(param.Parameterized):
        width = param.Integer(default=100, bounds=(10, 500))
        opacity = param.Number(default=1.0, bounds=(0.0, 1.0))

    # These will show error diagnostics:
    widget = Widget(
        width=1000,    # ❌ Error: Value 1000 exceeds upper bound 500
        opacity=1.5    # ❌ Error: Value 1.5 exceeds upper bound 1.0
    )

    # These are valid:
    widget = Widget(
        width=250,     # ✅ Valid: Within bounds (10, 500)
        opacity=0.8    # ✅ Valid: Within bounds (0.0, 1.0)
    )
    ```

**Error messages include:**

- Specific bound violation details
- Expected range information
- Suggested valid values

## Type Validation

Catch type mismatches before runtime:

```python
import param

class Config(param.Parameterized):
    name = param.String(default="app")
    count = param.Integer(default=10)
    enabled = param.Boolean(default=True)

# These will show error diagnostics:
config = Config(
    name=123,          # ❌ Error: Expected string, got integer
    count="not_int",   # ❌ Error: Expected integer, got string
    enabled="yes"      # ❌ Error: Expected boolean, got string
)
```

**Supported type validations:**

- **String**: Text values, optional regex patterns
- **Integer**: Whole numbers with optional bounds
- **Number**: Numeric values (int/float) with optional bounds
- **Boolean**: True/False values
- **List**: List objects with optional item type checking
- **Dict**: Dictionary objects
- **Tuple**: Tuple objects with optional element validation

## Selector Validation

Validation for parameter choices:

```python
import param

class Theme(param.Parameterized):
    style = param.Selector(
        default="light",
        objects=["light", "dark", "auto"]
    )
    size = param.Selector(
        default="medium",
        objects=["small", "medium", "large"]
    )

# This will show error diagnostics:
theme = Theme(
    style="blue",      # ❌ Error: 'blue' not in allowed objects
    size="tiny"        # ❌ Error: 'tiny' not in allowed objects
)

# This is valid:
theme = Theme(
    style="dark",      # ✅ Valid: In allowed objects
    size="large"       # ✅ Valid: In allowed objects
)
```

**Selector features:**

- Choice validation against allowed objects
- Suggestions for similar valid choices
- Case-sensitive matching
- Support for mixed-type choices

## Regular Expression Validation

String parameters with regex constraints:

```python
import param

class FormData(param.Parameterized):
    email = param.String(
        regex=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )
    phone = param.String(
        regex=r'^\+?1?[0-9]{10}$'
    )
    zip_code = param.String(
        regex=r'^\d{5}(-\d{4})?$'
    )

# These will show error diagnostics:
form = FormData(
    email="invalid-email",     # ❌ Error: Doesn't match email pattern
    phone="123",               # ❌ Error: Doesn't match phone pattern
    zip_code="invalid"         # ❌ Error: Doesn't match zip pattern
)
```

## List and Dict Validation

Complex type validation for collections:

```python
import param

class DataConfig(param.Parameterized):
    tags = param.List(
        default=["tag1", "tag2"],
        item_type=str  # Each item must be a string
    )

    metadata = param.Dict(
        default={"version": "1.0", "author": "user"}
    )

    coordinates = param.Tuple(
        default=(0, 0),
        length=2  # Must have exactly 2 elements
    )

# These will show error diagnostics:
config = DataConfig(
    tags=["tag1", 123],        # ❌ Error: Item 123 is not a string
    metadata="not-a-dict",     # ❌ Error: Expected dict, got string
    coordinates=(1, 2, 3)      # ❌ Error: Expected 2 elements, got 3
)
```

## Cross-Parameter Validation

Some validations check relationships between parameters:

```python
import param

class Range(param.Parameterized):
    min_value = param.Number(default=0)
    max_value = param.Number(default=100)

    @param.depends('min_value', 'max_value')
    def _validate_range(self):
        if self.min_value >= self.max_value:
            raise ValueError("min_value must be less than max_value")

# This will show error diagnostic:
range_obj = Range(
    min_value=50,
    max_value=30  # ❌ Error: min_value >= max_value
)
```

## Real-Time Validation

param-lsp provides validation as you type:

### Immediate Feedback

- **Red squiggly lines** under invalid values
- **Error tooltips** with detailed messages
- **Quick fixes** suggesting corrections

### Validation Timing

- **On save**: Full validation when file is saved
- **On type**: Basic validation while typing
- **On hover**: Detailed validation information

## Error Severity Levels

Different types of validation errors:

### Errors (Red)

```python
# Bound violations, type mismatches, invalid choices
widget = Widget(width=2000)  # ❌ Exceeds bounds
```

### Warnings (Yellow)

```python
# Deprecated parameters, unusual values
widget = Widget(width=999)   # ⚠️ Close to upper bound
```

### Information (Blue)

```python
# Suggestions, best practices
widget = Widget()  # ℹ️ Using default values
```

## Configuration Options

Customize type checking behavior:

```json
{
  "param-lsp": {
    "diagnostics": {
      "enable": true,
      "bounds_checking": true,
      "type_validation": true,
      "regex_validation": true,
      "unknown_parameters": "error"
    }
  }
}
```

**Options:**

- `enable` - Enable/disable all diagnostics
- `bounds_checking` - Validate numeric bounds
- `type_validation` - Check parameter types
- `regex_validation` - Validate regex patterns
- `unknown_parameters` - `"error"`, `"warning"`, or `"ignore"`

## Performance Considerations

Type checking is optimized for responsiveness:

- **Incremental validation**: Only re-check changed code
- **Background processing**: Heavy validation runs in background
- **Caching**: Results cached for unchanged code
- **Configurable limits**: Set maximum validation scope

## Troubleshooting Type Checking

If type checking isn't working:

1. **Check diagnostics enabled**: Verify settings allow error reporting
2. **Verify parameter definitions**: Ensure parameters have proper constraints
3. **Check editor support**: Confirm your editor displays LSP diagnostics
4. **Test with simple examples**: Use obvious errors to verify functionality

Common issues:

- **No error indicators**: Check editor LSP diagnostic display
- **Incorrect error messages**: Verify parameter definitions
- **Slow validation**: Adjust performance settings

## Advanced Validation

### Custom Validators

```python
import param

def positive_validator(value):
    if value <= 0:
        raise ValueError("Value must be positive")

class Model(param.Parameterized):
    value = param.Number(
        default=1.0,
        validator=positive_validator
    )
```

### Conditional Validation

```python
import param

class ConditionalWidget(param.Parameterized):
    mode = param.Selector(default="auto", objects=["auto", "manual"])
    manual_value = param.Number(default=0)

    @param.depends('mode')
    def _validate_manual_value(self):
        if self.mode == "manual" and self.manual_value == 0:
            raise ValueError("manual_value required when mode='manual'")
```

## Next Steps

- [Hover Information](hover-information.md) - Explore documentation features
- [Cross-File Analysis](cross-file-analysis.md) - Learn about inheritance tracking
- [Configuration](../configuration.md) - Customize validation behavior
