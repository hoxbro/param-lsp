# Autocompletion

param-lsp offers context-aware autocompletion for Param classes, parameters, and decorators.

## Parameter Constructor Completion

When creating instances of Parameterized classes, param-lsp provides intelligent parameter name completion:

=== "Screenshot"

    <!-- TODO: Add screenshot showing autocompletion dropdown for:
    MyClass(w|  # cursor position, showing width, height completions
    )
    Suggested filename: parameter-constructor-completion.png -->

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

param-lsp provides intelligent completion for other HoloViz libraries, Panel and HoloViews.

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
