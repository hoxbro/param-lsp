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
    width = param.Integer(
        default=100,
        bounds=(1, 1000),
        doc="Width of the widget in pixels"
    )

    height = param.Integer(
        default=50,
        bounds=(1, 1000),
        doc="Height of the widget in pixels"
    )

    title = param.String(
        default="My Widget",
        doc="Title displayed on the widget"
    )

    enabled = param.Boolean(
        default=True,
        doc="Whether the widget is enabled"
    )

    @param.depends('width', 'height')
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

- **Autocompletion** when typing parameter names in constructor
- **Hover documentation** when hovering over parameter definitions
- **Error diagnostics** if you set values outside bounds (try `width=1500`)
- **Method dependency tracking** for `@param.depends` decorators

## Common Patterns

### Parameter Types

param-lsp supports all standard parameter types:

```python
import param

class DataConfig(param.Parameterized):
    # Numbers with bounds
    threshold = param.Number(default=0.5, bounds=(0, 1))
    count = param.Integer(default=10, bounds=(1, 100))

    # Strings with validation
    filename = param.String(default="data.csv")
    pattern = param.String(default=r"\d+", regex=r".*")

    # Choices
    mode = param.Selector(default="auto", objects=["auto", "manual", "debug"])

    # Boolean flags
    verbose = param.Boolean(default=False)

    # Lists and objects
    tags = param.List(default=["tag1", "tag2"])
    metadata = param.Dict(default={})
```

### Dependencies

Use `@param.depends` for reactive programming:

```python
import param

class Calculator(param.Parameterized):
    a = param.Number(default=1.0)
    b = param.Number(default=2.0)
    operation = param.Selector(default="add", objects=["add", "multiply"])

    @param.depends('a', 'b', 'operation')
    def result(self):
        if self.operation == "add":
            return self.a + self.b
        else:
            return self.a * self.b
```

### Class Inheritance

param-lsp tracks parameters across inheritance:

```python
import param

class BaseModel(param.Parameterized):
    name = param.String(default="Model")
    version = param.String(default="1.0")

class MLModel(BaseModel):
    # Inherits: name, version
    learning_rate = param.Number(default=0.01, bounds=(0, 1))
    epochs = param.Integer(default=100, bounds=(1, 1000))

# Autocompletion includes inherited parameters
model = MLModel(
    name="MyModel",        # From BaseModel
    learning_rate=0.001    # From MLModel
)
```

## Working with External Libraries

param-lsp has built-in support for popular libraries:

### Panel Widgets

```python
import panel as pn

# param-lsp knows Panel parameter APIs
slider = pn.widgets.IntSlider(
    value=50,
    start=0,
    end=100,
    step=5,
    name="Threshold"
)

button = pn.widgets.Button(
    name="Process",
    button_type="primary"
)
```

### HoloViews Elements

```python
import holoviews as hv

# Smart completion for HoloViews
scatter = hv.Scatter(data).opts(
    size=10,
    color='blue',
    tools=['hover']
)
```

## Testing Your Setup

To verify param-lsp is working correctly:

1. **Autocompletion Test**:

   ```python
   import param

   class Test(param.Parameterized):
       value = param.Number()

   # Type 'Test(' - should show 'value' completion
   instance = Test()
   ```

2. **Error Detection Test**:

   ```python
   import param

   class Test(param.Parameterized):
       bounded = param.Integer(bounds=(1, 10))

   # This should show error diagnostic
   Test(bounded=100)
   ```

3. **Hover Information Test**:

   ```python
   import param

   class Test(param.Parameterized):
       documented = param.String(
           default="test",
           doc="This parameter has documentation"
       )

   # Hover over 'documented' should show type and doc
   ```

## Next Steps

- [Features](features/) - Explore all param-lsp features in detail
- [Configuration](configuration.md) - Customize param-lsp for your workflow
- [Troubleshooting](troubleshooting/) - Solve common issues
