# Cross-File Analysis

param-lsp intelligently tracks parameter inheritance and usage across multiple files in your project.

## Local Class Inheritance

Track parameters across class hierarchies spanning multiple files:

=== "Screenshot"

    <!-- TODO: Add screenshot showing cross-file inheritance autocompletion for:
    button = Button(|  # cursor showing completions including inherited params
    with completions showing: width, height, visible (from BaseWidget) and text, disabled (from Button)
    -->

    **Screenshot needed:** Cross-file inheritance autocompletion showing inherited parameters

=== "Code"

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
    ```

**Features:**

- **Parameter inheritance tracking** across file boundaries
- **Autocompletion** includes inherited parameters
- **Type checking** validates inherited parameter constraints
- **Hover information** shows inheritance source

## External Library Support

param-lsp has built-in knowledge of popular HoloViz ecosystem libraries:

### Panel Integration

Smart completion and validation for Panel widgets:

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

**Supported Panel widgets:**

- `pn.widgets.IntSlider`, `FloatSlider`
- `pn.widgets.Button`, `Toggle`
- `pn.widgets.TextInput`, `TextAreaInput`
- `pn.widgets.Select`, `MultiSelect`
- And many more...

### HoloViews Integration

Intelligent support for HoloViews elements and options:

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

**Supported HoloViews features:**

- Element constructors (`Scatter`, `Curve`, `Image`, etc.)
- Style options (`size`, `color`, `alpha`, etc.)
- Plot options (`width`, `height`, `tools`, etc.)
- Backend-specific options

### Datashader Support

```python
import datashader as ds
import datashader.transfer_functions as tf

# Parameter completion for Datashader operations
canvas = ds.Canvas(
    plot_width=800,    # ✅ Integer parameter
    plot_height=600,   # ✅ Integer parameter
    x_range=(-1, 1),   # ✅ Tuple validation
    y_range=(-1, 1)    # ✅ Tuple validation
)
```

## Dependency Tracking

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

**Features:**

- **Cross-file dependency tracking**
- **Nested parameter dependencies** (`object.parameter`)
- **Validation** of dependency parameter names
- **Autocompletion** for dependency strings

## Project Structure Analysis

param-lsp analyzes your entire project structure:

### Package Discovery

```
my_project/
├── src/
│   ├── widgets/
│   │   ├── __init__.py
│   │   ├── base.py      # BaseWidget class
│   │   └── buttons.py   # Button, ToggleButton classes
│   └── models/
│       ├── __init__.py
│       └── data.py      # DataModel class
└── tests/
    └── test_widgets.py  # Test files also analyzed
```

param-lsp automatically discovers and analyzes:

- **All Python files** in the project
- **Package structures** and imports
- **Class hierarchies** across modules
- **Parameter inheritance chains**

### Import Resolution

Smart import resolution handles various import patterns:

```python
# Absolute imports
from src.widgets.base import BaseWidget

# Relative imports
from .base import BaseWidget
from ..models.data import DataModel

# Star imports (with limitations)
from src.widgets import *

# Aliased imports
from src.widgets.base import BaseWidget as Base
```

## Configuration Options

Control cross-file analysis behavior:

```json
{
  "param-lsp": {
    "analysis": {
      "cross_file": true,
      "external_classes": true,
      "max_inheritance_depth": 5,
      "max_files": 1000,
      "include_test_files": true,
      "scan_site_packages": false
    }
  }
}
```

**Options:**

- `cross_file` - Enable cross-file parameter tracking
- `external_classes` - Support external library classes
- `max_inheritance_depth` - Maximum inheritance chain to follow
- `max_files` - Maximum files to analyze
- `include_test_files` - Analyze test files for parameter usage
- `scan_site_packages` - Include installed packages in analysis

## Performance Optimization

Cross-file analysis is optimized for large projects:

### Incremental Analysis

- **Changed files only**: Re-analyze only modified files
- **Dependency tracking**: Update dependent files when imports change
- **Caching**: Cache analysis results for unchanged files

### Memory Management

- **Lazy loading**: Load file analysis on demand
- **Memory limits**: Configurable memory usage bounds
- **Cleanup**: Automatic cleanup of unused analysis data

### Background Processing

- **Non-blocking**: Analysis runs in background threads
- **Progressive loading**: Gradual project analysis on startup
- **Priority queues**: Prioritize active files for analysis

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

## Troubleshooting Cross-File Analysis

Common issues and solutions:

### Import Resolution Problems

```python
# Problem: Relative imports not resolving
from .base import BaseWidget  # ❌ Can't find base module

# Solutions:
# 1. Check project structure in LSP settings
# 2. Verify __init__.py files exist
# 3. Add project root to Python path
```

### Inheritance Not Detected

```python
# Problem: Inherited parameters not showing
class Button(BaseWidget):  # ❌ BaseWidget parameters not available
    pass

# Solutions:
# 1. Verify BaseWidget file is analyzed
# 2. Check import statement is correct
# 3. Restart language server
```

### Performance Issues

If cross-file analysis is slow:

1. **Reduce scope**: Limit `max_files` or `max_inheritance_depth`
2. **Exclude directories**: Add patterns to `exclude_patterns`
3. **Disable features**: Turn off `external_classes` if not needed
4. **Increase memory**: Raise memory limits for better caching

## Best Practices

### Project Organization

```
# Good: Clear module structure
src/
├── widgets/
│   ├── __init__.py
│   ├── base.py
│   └── controls.py
└── models/
    ├── __init__.py
    └── data.py

# Avoid: Deep nesting without clear purpose
src/widgets/ui/controls/buttons/basic/simple.py
```

### Import Patterns

```python
# Preferred: Explicit imports
from src.widgets.base import BaseWidget

# Acceptable: Relative imports in packages
from .base import BaseWidget

# Avoid: Star imports (limits analysis)
from src.widgets import *
```

### Documentation

```python
# Good: Document inheritance relationships
class Button(BaseWidget):
    """
    Interactive button widget.

    Inherits common widget parameters from BaseWidget:
    - width, height: Widget dimensions
    - visible: Widget visibility
    """
    pass
```

## Next Steps

- [IDE Integration](ide-integration.md) - Explore editor-specific features
- [Configuration](../configuration.md) - Optimize analysis settings
- [Troubleshooting](../troubleshooting/) - Solve analysis issues
