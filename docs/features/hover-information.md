# Hover Information

Rich documentation appears when hovering over parameters, classes, and methods in your code.

## Parameter Documentation

Hover over any parameter to see comprehensive information:

=== "Screenshot"

    <!-- TODO: Add screenshot showing hover tooltip for 'volume' parameter with:
    - Type: param.Number
    - Default: 0.5
    - Bounds: (0.0, 1.0)
    - Doc: "Audio volume level from 0.0 (mute) to 1.0 (maximum)"
    Suggested filename: parameter-hover-tooltip.png -->

    **Screenshot needed:** Hover tooltip showing parameter type, default, bounds, and documentation

=== "Code"

    ```python
    import param

    class VideoPlayer(param.Parameterized):
        volume = param.Number(
            default=0.5,
            bounds=(0.0, 1.0),
            doc="Audio volume level from 0.0 (mute) to 1.0 (maximum)"
        )

        quality = param.Selector(
            default="720p",
            objects=["480p", "720p", "1080p", "4K"],
            doc="Video quality setting"
        )

    # Hover over 'volume' or 'quality' to see:
    player = VideoPlayer(volume=0.8, quality="1080p")
    ```

**Hover information includes:**

- **Parameter type** (e.g., `param.Number`)
- **Default value**
- **Bounds/constraints**
- **Documentation string**
- **Current value** (if available)

## Class Documentation

Hover over Parameterized class names for class-level information:

```python
import param

class MediaProcessor(param.Parameterized):
    """
    A media processing pipeline with configurable parameters.

    This class handles various media formats and provides
    real-time processing capabilities.
    """

    input_format = param.Selector(default="mp4", objects=["mp4", "avi", "mov"])

# Hover over 'MediaProcessor' to see class docstring and parameter summary
processor = MediaProcessor()
```

**Class hover shows:**

- **Class docstring**
- **Parameter summary**
- **Inheritance hierarchy**
- **Available methods**

## Parameter Types and Constraints

Different parameter types show relevant constraint information:

### Numeric Parameters

```python
import param

class Calculator(param.Parameterized):
    value = param.Number(
        default=0.0,
        bounds=(-100, 100),
        step=0.1,
        doc="Calculation input value"
    )

    count = param.Integer(
        default=1,
        bounds=(1, 1000),
        doc="Number of iterations"
    )
```

**Hover shows:**

- **Type**: `param.Number` or `param.Integer`
- **Bounds**: Valid range `(-100, 100)`
- **Step**: Increment value `0.1`
- **Default**: `0.0`
- **Documentation**: Parameter description

### String Parameters

```python
import param

class FormData(param.Parameterized):
    name = param.String(
        default="",
        regex=r"^[A-Za-z\s]+$",
        doc="User's full name (letters and spaces only)"
    )

    email = param.String(
        default="user@example.com",
        regex=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
        doc="Valid email address"
    )
```

**Hover shows:**

- **Type**: `param.String`
- **Regex pattern**: Validation pattern
- **Default**: Default value
- **Documentation**: Usage description

### Selector Parameters

```python
import param

class AppSettings(param.Parameterized):
    theme = param.Selector(
        default="light",
        objects=["light", "dark", "auto"],
        doc="Application color theme"
    )

    log_level = param.Selector(
        default="INFO",
        objects=["DEBUG", "INFO", "WARNING", "ERROR"],
        doc="Logging verbosity level"
    )
```

**Hover shows:**

- **Type**: `param.Selector`
- **Choices**: Available options `["light", "dark", "auto"]`
- **Default**: Current default selection
- **Documentation**: Parameter purpose

## Method Dependencies

Hover over methods with `@param.depends` to see dependency information:

```python
import param

class DataAnalyzer(param.Parameterized):
    data_file = param.String(default="data.csv")
    threshold = param.Number(default=0.5, bounds=(0, 1))

    @param.depends('data_file', 'threshold')
    def analyze(self):
        """Analyze data with current threshold."""
        return f"Analyzing {self.data_file} with threshold {self.threshold}"

    # Hover over 'analyze' shows:
    # - Method documentation
    # - Parameter dependencies: data_file, threshold
    # - Return type information
```

**Method hover shows:**

- **Method signature**
- **Docstring**
- **Parameter dependencies**
- **Watch status** (if applicable)

## Inheritance Information

Hover over inherited parameters shows inheritance chain:

```python
import param

class BaseWidget(param.Parameterized):
    """Base widget with common parameters."""
    width = param.Integer(default=100, doc="Widget width in pixels")
    height = param.Integer(default=50, doc="Widget height in pixels")

class Button(BaseWidget):
    """Interactive button widget."""
    text = param.String(default="Click me", doc="Button text")

# Hover over 'width' in Button instance shows:
# - Inherited from: BaseWidget
# - Type: param.Integer
# - Default: 100
# - Documentation: "Widget width in pixels"
button = Button()
```

## External Library Support

param-lsp provides hover information for external library parameters:

### Panel Widgets

```python
import panel as pn

# Hover over Panel widget parameters
slider = pn.widgets.IntSlider(
    name="Threshold",    # Hover shows: String parameter for widget title
    value=50,           # Hover shows: Integer value with bounds
    start=0,            # Hover shows: Minimum value
    end=100             # Hover shows: Maximum value
)
```

### HoloViews Elements

```python
import holoviews as hv

# Hover over HoloViews element options
scatter = hv.Scatter(data).opts(
    size=10,            # Hover shows: Point size in screen units
    color='blue',       # Hover shows: Point color specification
    tools=['hover']     # Hover shows: Available interactive tools
)
```

## Dynamic Parameter Information

For parameters that change based on context:

```python
import param

class AdaptiveWidget(param.Parameterized):
    mode = param.Selector(default="basic", objects=["basic", "advanced"])

    def __init__(self, **params):
        super().__init__(**params)
        if self.mode == "advanced":
            self.param.add_parameter(
                'advanced_option',
                param.Boolean(default=False, doc="Advanced feature toggle")
            )

# Hover information updates based on current parameter state
widget = AdaptiveWidget(mode="advanced")
```

## Configuration Options

Customize hover information display:

```json
{
  "param-lsp": {
    "hover": {
      "show_type_info": true,
      "show_bounds": true,
      "show_defaults": true,
      "show_documentation": true,
      "show_inheritance": true,
      "max_doc_length": 200
    }
  }
}
```

**Options:**

- `show_type_info` - Display parameter type information
- `show_bounds` - Show bounds and constraints
- `show_defaults` - Include default values
- `show_documentation` - Show docstrings
- `show_inheritance` - Display inheritance information
- `max_doc_length` - Maximum documentation length

## Formatting and Presentation

Hover information is formatted for readability:

### Rich Text Formatting

- **Bold** parameter names and types
- _Italic_ constraint information
- `Code` formatting for values
- **Syntax highlighting** for code examples

### Structured Layout

```
param.Number: volume
Default: 0.5
Bounds: (0.0, 1.0)
Step: 0.1

Audio volume level from 0.0 (mute) to 1.0 (maximum)

Inherited from: AudioMixin
```

### Interactive Elements

- **Links** to parameter definitions
- **Navigation** to related parameters
- **Quick actions** for common operations

## Troubleshooting Hover Information

If hover information isn't appearing:

1. **Check hover support**: Verify your editor supports LSP hover
2. **Verify parameter definitions**: Ensure parameters have documentation
3. **Check file analysis**: Confirm param-lsp is analyzing the file
4. **Test with examples**: Use well-documented parameters to verify

Common issues:

- **Empty hover tooltips**: Add documentation to parameters
- **Incomplete information**: Check parameter definition completeness
- **Slow hover response**: Adjust performance settings

## Best Practices

### Writing Good Parameter Documentation

```python
import param

class WellDocumented(param.Parameterized):
    """A well-documented parameterized class."""

    threshold = param.Number(
        default=0.5,
        bounds=(0, 1),
        doc="""
        Detection threshold for classification.

        Higher values increase precision but may reduce recall.
        Recommended range: 0.3-0.7 for most use cases.
        """
    )

    mode = param.Selector(
        default="auto",
        objects=["auto", "manual", "batch"],
        doc="""
        Processing mode selection.

        - auto: Automatic parameter selection
        - manual: User-defined parameters
        - batch: Optimized for batch processing
        """
    )
```

### Structured Documentation

Use consistent documentation patterns:

- **Purpose**: What the parameter controls
- **Valid values**: Acceptable range or choices
- **Effects**: How it impacts behavior
- **Examples**: Usage examples or recommendations

## Next Steps

- [Cross-File Analysis](cross-file-analysis.md) - Learn about inheritance tracking
- [IDE Integration](ide-integration.md) - Explore editor features
- [Configuration](../configuration.md) - Customize hover behavior
