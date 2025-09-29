# Hover Information

Rich documentation appears when hovering over parameters, classes, and methods in your code.

## Parameter Documentation

Hover over any parameter to see comprehensive information:

=== "Screenshot"

    ![Parameter Hover Tooltip](../assets/parameter-hover-tooltip.png)

    Hover tooltip showing parameter type, default, bounds, and documentation

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
- **Parameter relevant**

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
