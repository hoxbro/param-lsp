# Features

param-lsp provides intelligent IDE support for Python codebases using the HoloViz Param library. This page demonstrates each feature with detailed examples.

## Autocompletion

param-lsp offers context-aware autocompletion for Param classes, parameters, and decorators.

### Parameter Constructor Completion

When creating instances of Parameterized classes, param-lsp provides intelligent parameter name completion:

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

<!-- TODO: Add screenshot showing autocompletion dropdown for:
MyClass(w|  # cursor position, showing width, height completions
) -->

**Screenshot needed:** Autocompletion dropdown showing parameter suggestions

### Parameter Definition Completion

When defining new Parameterized classes, get completions for parameter types:

```python
import param

class NewWidget(param.Parameterized):
    # Type 'param.' to see all parameter types
    value = param.Num  # <- Completes to 'param.Number'
    text = param.Str   # <- Completes to 'param.String'
    flag = param.Bool  # <- Completes to 'param.Boolean'
```

### @param.depends Completion

Smart completion for dependency decorators:

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

## Type Checking & Diagnostics

param-lsp provides real-time validation of parameter values, types, and constraints.

### Bounds Checking

Immediate feedback when parameter values violate bounds:

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

<!-- TODO: Add screenshot showing error diagnostics for:
widget = Widget(width=1000, opacity=1.5)
with red squiggly lines under the invalid values and error tooltips
-->

# These are valid:
widget = Widget(
    width=250,     # ✅ Valid: Within bounds (10, 500)
    opacity=0.8    # ✅ Valid: Within bounds (0.0, 1.0)
)
```

### Type Validation

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

### Selector Validation

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

## Hover Information

Rich documentation appears when hovering over parameters and classes.

### Parameter Documentation

Hover over any parameter to see comprehensive information:

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

<!-- TODO: Add screenshot showing hover tooltip for 'volume' parameter with:
- Type: param.Number
- Default: 0.5
- Bounds: (0.0, 1.0)
- Doc: "Audio volume level from 0.0 (mute) to 1.0 (maximum)"
-->
```

**Hover information includes:**

- Parameter type (e.g., `param.Number`)
- Default value
- Bounds/constraints
- Documentation string
- Current value (if available)

### Class Documentation

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

## Cross-File Analysis

param-lsp intelligently tracks parameter inheritance and usage across multiple files.

### Local Class Inheritance

Track parameters across class hierarchies:

**base.py:**

```python
import param

class BaseWidget(param.Parameterized):
    width = param.Integer(default=100, bounds=(1, 1000))
    height = param.Integer(default=50, bounds=(1, 1000))
    visible = param.Boolean(default=True)
```

**button.py:**

```python
from .base import BaseWidget
import param

class Button(BaseWidget):
    # Inherits: width, height, visible
    text = param.String(default="Click me")
    disabled = param.Boolean(default=False)

# Autocompletion includes inherited parameters:
button = Button(
    width=200,    # ✅ From BaseWidget
    text="Submit" # ✅ From Button
)

<!-- TODO: Add screenshot showing cross-file inheritance autocompletion for:
button = Button(|  # cursor showing completions including inherited params
with completions showing: width, height, visible (from BaseWidget) and text, disabled (from Button)
-->
```

### External Library Support

Smart completion and validation for popular libraries:

#### Panel Integration

```python
import panel as pn

# param-lsp knows Panel parameter APIs
widget = pn.widgets.IntSlider(
    value=50,       # ✅ Autocompletion knows IntSlider parameters
    start=0,        # ✅ Parameter bounds checking
    end=100,        # ✅ Type validation
    step=5          # ✅ Hover shows parameter documentation
)

button = pn.widgets.Button(
    name="Process",     # ✅ String parameter
    button_type="primary"  # ✅ Selector validation
)
```

#### HoloViews Integration

```python
import holoviews as hv

# Smart completion for HoloViews elements
scatter = hv.Scatter(data).opts(
    size=10,           # ✅ Knows valid style options
    color='blue',      # ✅ Type checking for color values
    tools=['hover']    # ✅ Validates available tools
)

curve = hv.Curve(data).opts(
    line_width=2,      # ✅ Number validation
    line_color='red'   # ✅ Color parameter support
)
```

### Dependency Tracking

Track `@param.depends` relationships across files:

**models.py:**

```python
import param

class DataModel(param.Parameterized):
    filename = param.String(default="data.csv")
    threshold = param.Number(default=0.5, bounds=(0, 1))

    @param.depends('filename', 'threshold')
    def load_data(self):
        return f"Loading {self.filename} with threshold {self.threshold}"
```

**views.py:**

```python
from .models import DataModel
import param

class DataView(param.Parameterized):
    model = param.Parameter()

    @param.depends('model.filename')  # ✅ Cross-object dependency tracking
    def update_title(self):
        return f"Viewing: {self.model.filename}"
```

## Advanced Features

### Nested Parameter Access

Support for complex parameter hierarchies:

```python
import param

class DatabaseConfig(param.Parameterized):
    host = param.String(default="localhost")
    port = param.Integer(default=5432)

class AppConfig(param.Parameterized):
    database = param.Parameter(default=DatabaseConfig())
    debug = param.Boolean(default=False)

app = AppConfig()

# param-lsp understands nested access:
@param.depends('database.host', 'database.port')
def connect_db(self):
    return f"Connecting to {self.database.host}:{self.database.port}"
```

### Dynamic Parameter Creation

Intelligent handling of dynamically created parameters:

```python
import param

class DynamicClass(param.Parameterized):
    def __init__(self, **params):
        # Dynamic parameters based on config
        if params.get('enable_advanced'):
            self.param.add_parameter('advanced_option',
                                   param.Boolean(default=False))
        super().__init__(**params)

# param-lsp adapts to dynamic parameter creation
instance = DynamicClass(
    enable_advanced=True,
    advanced_option=True  # ✅ Recognized after dynamic creation
)
```

## Performance Features

### Incremental Analysis

param-lsp performs incremental analysis for optimal performance:

- **Fast startup**: Only analyzes files as needed
- **Incremental updates**: Re-analyzes only changed parts
- **Caching**: Intelligent caching of analysis results
- **Background processing**: Non-blocking analysis

### Large Codebase Support

Optimized for large projects with many Param classes:

- **Lazy loading**: Parameters loaded on-demand
- **Memory efficient**: Minimal memory footprint
- **Scalable**: Performance maintained with project size
- **Index-based**: Fast parameter lookup across files

## IDE Integration Examples

### Error Indicators

Visual feedback directly in your editor:

```python
# Red squiggly lines under problematic code
widget = MyWidget(
    width=2000,    # 🔴 Bounds violation highlighted
    invalid_param=True  # 🔴 Unknown parameter highlighted
)
```

<!-- TODO: Add screenshot showing IDE with error indicators:
Code editor showing red squiggly lines under invalid parameter values
with error tooltips displaying specific constraint violations
-->

### Quick Fixes

Suggested fixes for common issues:

- **Bound violations**: Suggest valid range values
- **Type errors**: Suggest correct type conversion
- **Unknown parameters**: Suggest similar parameter names
- **Missing imports**: Auto-import param modules

### Code Actions

Right-click context menu actions:

- **"Add missing parameters"**: Insert missing required parameters
- **"Fix parameter bounds"**: Adjust values to valid ranges
- **"Convert to param class"**: Convert regular class to Parameterized
- **"Generate parameter docs"**: Add documentation for parameters

## Configuration

Customize param-lsp behavior for your project needs:

```json
{
  "param-lsp": {
    "diagnostics": {
      "enable": true,
      "bounds_checking": true,
      "type_validation": true,
      "unknown_parameters": "warning"
    },
    "completion": {
      "include_inherited": true,
      "show_parameter_docs": true,
      "external_libraries": ["panel", "holoviews", "datashader"]
    },
    "analysis": {
      "cross_file": true,
      "external_classes": true,
      "max_inheritance_depth": 5
    }
  }
}
```

These features make param-lsp a powerful tool for working with Param-based codebases, providing the intelligence and safety of a dedicated language server while maintaining the flexibility and power of the Param library.
