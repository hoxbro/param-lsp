# Autocompletion

param-lsp offers context-aware autocompletion for Param classes, parameters, and decorators.

## Parameter Constructor Completion

When creating instances of Parameterized classes, param-lsp provides intelligent parameter name completion:

=== "Screenshot"

    ![Parameter Constructor Completion](../assets/parameter-constructor-completion.png)

    Autocompletion dropdown showing parameter suggestions for MyClass constructor

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

## `@param.depends` Completion

Smart completion for dependency decorators:

=== "Screenshot"

    ![Param Depends Completion](../assets/param-depends-completion.png)

    Parameter name completions within `@param.depends` decorator strings

=== "Code"

    ```python
    import pandas as pd
    import param

    class DataProcessor(param.Parameterized):
        input_file = param.String(default="data.csv")

        @param.depends('inp  # <- Completes to 'input_file'
        def process_data(self):
            return pd.read_csv(self.input_file)
    ```

**Features:**

- Parameter name completion within dependency strings
- Multiple parameter dependency support
- Validation of parameter names
- Cross-object dependency completion

## Inheritance-Aware Completion

Autocompletion includes parameters from parent classes:

=== "Screenshot"

    ![Inheritance Completion](../assets/inheritance-completion.png)

    Autocompletion showing both inherited and local parameters for Button class

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

```python
import panel as pn

# param-lsp knows Panel
slider = pn.widgets.IntSlider(
    value=50,  # <- Autocompletion knows IntSlider parameters
    start=0,  # <- Parameter bounds checking
    end=100,  # <- Type validation
    step=5,  # <- Hover shows parameter documentation
)
```
