# Getting Started

This guide will help you start using param-lsp with practical examples.

## Basic Usage

Once configured, param-lsp will automatically provide IDE features for Python files containing Param code:

1. **Open a Python file** with Param classes
2. **Start typing** to see autocompletions
3. **Hover over parameters** to see documentation
4. **Watch for error diagnostics** for type and constraint violations

## Your First Param File

Create a new Python file with this example to test param-lsp features:

```python
import param


class MyWidget(param.Parameterized):
    """A simple parameterized widget."""

    # Try hovering over these parameters
    width = param.Integer(default=100, bounds=(1, 1000), doc="Width of the widget in pixels")
    height = param.Integer(default=50, bounds=(1, 1000), doc="Height of the widget in pixels")
    title = param.String(default="My Widget", doc="Title displayed on the widget")
    enabled = param.Boolean(default=True, doc="Whether the widget is enabled")

    @param.depends("width", "height")
    def area(self):
        """Calculate the area of the widget."""
        return self.width * self.height


# Try autocompletion when creating instances
widget = MyWidget(
    # Type 'w' and see width parameter completion
    # Type 'width=1500' and see bounds violation error
)
```

## What to Expect

With the example above, you should see:

- **[Autocompletion](features/autocompletion.md)** when typing parameter names in constructor
- **[Hover documentation](features/hover-information.md)** when hovering over parameter definitions
- **[Error diagnostics](features/validation.md)** if you set values outside bounds (try `width=1500`)
