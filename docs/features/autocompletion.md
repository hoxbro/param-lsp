# Autocompletion

param-lsp offers context-aware autocompletion for Param classes, parameters, and decorators.

## Parameter Constructor Completion

When creating instances of Parameterized classes, param-lsp provides intelligent parameter name completion:

=== "Screenshot"

    <!-- TODO: Add screenshot showing autocompletion dropdown for:
    MyClass(w|  # cursor position, showing width, height completions
    ) -->

    **Screenshot needed:** Autocompletion dropdown showing parameter suggestions for MyClass constructor

=== "Code"

    ```python
    import param

    class MyClass(param.Parameterized):
        width = param.Integer(default=100, bounds=(1, 1000))
        height = param.Integer(default=50, bounds=(1, 1000))
        title = param.String(default="Widget")

    # Type 'MyClass(' and see parameter completions
    instance = MyClass(
        w  # <- Autocompletion suggests 'width'
        # Completion shows: width, height, title
    )
    ```

**What you'll see:**

- Immediate parameter name suggestions as you type
- Parameter type information in completion details
- Default values and bounds shown in completion documentation

## Parameter Definition Completion

When defining new Parameterized classes, get completions for parameter types:

=== "Screenshot"

    **Screenshot needed:** Parameter type completions when typing 'param.' in class definitions

=== "Code"

    ```python
    import param

    class NewWidget(param.Parameterized):
        # Type 'param.' to see all parameter types
        value = param.Num  # <- Completes to 'param.Number'
        text = param.Str   # <- Completes to 'param.String'
        flag = param.Bool  # <- Completes to 'param.Boolean'
    ```

**Available parameter types:**

- `param.Number` - Numeric values with optional bounds
- `param.Integer` - Integer values with optional bounds
- `param.String` - Text values with optional regex validation
- `param.Boolean` - True/False values
- `param.Selector` - Choice from predefined options
- `param.List` - List of values
- `param.Dict` - Dictionary objects
- And many more...

## @param.depends Completion

Smart completion for dependency decorators:

=== "Screenshot"

    **Screenshot needed:** Parameter name completions within @param.depends decorator strings

=== "Code"

    ```python
    import param

    class DataProcessor(param.Parameterized):
        input_file = param.String(default="data.csv")
        threshold = param.Number(default=0.5)

        @param.depends('inp  # <- Completes to 'input_file'
        def process_data(self):
            return f"Processing {self.input_file} with threshold {self.threshold}"

        @param.depends('input_file', 'thr  # <- Completes to 'threshold'
        def advanced_processing(self):
            pass
    ```

**Features:**

- Parameter name completion within dependency strings
- Multiple parameter dependency support
- Validation of parameter names
- Cross-object dependency completion

## Inheritance-Aware Completion

Autocompletion includes parameters from parent classes:

=== "Screenshot"

    **Screenshot needed:** Autocompletion showing both inherited and local parameters for Button class

=== "Code"

    ```python
    import param

    class BaseWidget(param.Parameterized):
        width = param.Integer(default=100)
        height = param.Integer(default=50)

    class Button(BaseWidget):
        text = param.String(default="Click me")
        disabled = param.Boolean(default=False)

    # Completion includes inherited parameters
    button = Button(
        width=200,    # From BaseWidget
        text="Submit", # From Button
        # All available: width, height, text, disabled
    )
    ```

## External Library Support

param-lsp provides intelligent completion for popular libraries:

### Panel Widgets

=== "Screenshot"

    **Screenshot needed:** Intelligent completion for Panel widget parameters with type validation

=== "Code"

    ```python
    import panel as pn

    # param-lsp knows Panel parameter APIs
    slider = pn.widgets.IntSlider(
        value=50,    # <- Autocompletion knows IntSlider parameters
        start=0,     # <- Parameter bounds checking
        end=100,     # <- Type validation
        step=5       # <- Hover shows parameter documentation
    )

    button = pn.widgets.Button(
        name="Process",         # <- String parameter
        button_type="primary"   # <- Selector validation
    )
    ```

### HoloViews Elements

=== "Screenshot"

    **Screenshot needed:** Smart completion for HoloViews elements with style options validation

=== "Code"

    ```python
    import holoviews as hv

    # Smart completion for HoloViews elements
    scatter = hv.Scatter(data).opts(
        size=10,           # <- Knows valid style options
        color='blue',      # <- Type checking for color values
        tools=['hover']    # <- Validates available tools
    )
    ```

## Completion Filtering

param-lsp intelligently filters completions based on context:

### Type-Based Filtering

```python
import param

class Config(param.Parameterized):
    count = param.Integer(bounds=(1, 100))
    name = param.String(default="test")
    flag = param.Boolean(default=True)

# Only shows parameters matching expected type
config = Config(
    count=  # <- Shows numeric completions first
    name=   # <- Shows string completions first
    flag=   # <- Shows boolean completions first
)
```

### Context-Aware Suggestions

```python
import param

class Model(param.Parameterized):
    learning_rate = param.Number(bounds=(0, 1))
    batch_size = param.Integer(bounds=(1, 1000))

# Completions prioritized by usage patterns
model = Model(
    learn  # <- 'learning_rate' suggested first
    batch  # <- 'batch_size' suggested first
)
```

## Configuration Options

Customize autocompletion behavior:

```json
{
  "param-lsp": {
    "completion": {
      "include_inherited": true,
      "show_parameter_docs": true,
      "external_libraries": ["panel", "holoviews"],
      "max_completions": 50,
      "sort_by_relevance": true
    }
  }
}
```

**Options:**

- `include_inherited` - Show parameters from parent classes
- `show_parameter_docs` - Include documentation in completion details
- `external_libraries` - Libraries to analyze for completions
- `max_completions` - Maximum number of completion items
- `sort_by_relevance` - Sort by usage frequency and context

## Troubleshooting Autocompletion

If autocompletion isn't working:

1. **Check file is Python**: Verify syntax highlighting and file association
2. **Verify param import**: Ensure `import param` is present
3. **Check class inheritance**: Class must inherit from `param.Parameterized`
4. **Restart language server**: Reload your editor or restart LSP client

See [Troubleshooting](../troubleshooting/) for more detailed solutions.

## Next Steps

- [Type Checking](type-checking.md) - Learn about error detection
- [Hover Information](hover-information.md) - Explore documentation features
- [Configuration](../configuration.md) - Customize completion behavior
