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

## Parameter Types and Constraints

Different parameter types show relevant constraint information:

### Numeric Parameters

```python
import param


class Calculator(param.Parameterized):
    value = param.Number(default=0.0, bounds=(-100, 100), step=0.1, doc="Calculation input value")

    count = param.Integer(default=1, bounds=(1, 1000), doc="Number of iterations")
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
        default="", regex=r"^[A-Za-z\s]+$", doc="User's full name (letters and spaces only)"
    )

    email = param.String(
        default="user@example.com",
        regex=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
        doc="Valid email address",
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
        default="light", objects=["light", "dark", "auto"], doc="Application color theme"
    )

    log_level = param.Selector(
        default="INFO",
        objects=["DEBUG", "INFO", "WARNING", "ERROR"],
        doc="Logging verbosity level",
    )
```

**Hover shows:**

- **Type**: `param.Selector`
- **Choices**: Available options `["light", "dark", "auto"]`
- **Default**: Current default selection
- **Documentation**: Parameter purpose

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
        """,
    )

    mode = param.Selector(
        default="auto",
        objects=["auto", "manual", "batch"],
        doc="""
        Processing mode selection.

        - auto: Automatic parameter selection
        - manual: User-defined parameters
        - batch: Optimized for batch processing
        """,
    )
```
