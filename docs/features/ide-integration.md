# IDE Integration

param-lsp provides enhanced editor experience with visual feedback, quick fixes, and performance optimizations.

## Error Indicators

Visual feedback directly in your editor:

=== "Screenshot"

    <!-- TODO: Add screenshot showing IDE with error indicators:
    Code editor showing red squiggly lines under invalid parameter values
    with error tooltips displaying specific constraint violations
    Suggested filename: ide-error-indicators.png -->

    **Screenshot needed:** IDE with error indicators showing red squiggly lines and error tooltips

=== "Code"

    ```python
    # Red squiggly lines under problematic code
    widget = MyWidget(
        width=2000,    # 🔴 Bounds violation highlighted
        invalid_param=True  # 🔴 Unknown parameter highlighted
    )
    ```

**Error indicator types:**

- **Red squiggly lines**: Syntax errors, type mismatches, bound violations
- **Yellow squiggly lines**: Warnings, deprecated parameters
- **Blue squiggly lines**: Information, suggestions, best practices

## Quick Fixes

Suggested fixes for common issues appear in context menus:

### Bound Violations

```python
import param

class Widget(param.Parameterized):
    width = param.Integer(bounds=(10, 500))

# Problem: Value exceeds bounds
widget = Widget(width=1000)  # 🔴 Error

# Quick fixes offered:
# ✅ Set to maximum value (500)
# ✅ Set to default value
# ✅ Remove parameter (use default)
```

### Type Errors

```python
import param

class Config(param.Parameterized):
    count = param.Integer(default=10)

# Problem: Wrong type
config = Config(count="not_a_number")  # 🔴 Error

# Quick fixes offered:
# ✅ Convert to integer: count=int("not_a_number")
# ✅ Use default value
# ✅ Use similar parameter (if available)
```

### Unknown Parameters

```python
import param

class MyClass(param.Parameterized):
    width = param.Integer(default=100)

# Problem: Typo in parameter name
instance = MyClass(widht=200)  # 🔴 Error should have been width

# Quick fixes offered:
# ✅ Fix typo: width=200
# ✅ Remove unknown parameter
# ✅ Add parameter to class definition
```

## Code Actions

Right-click context menu actions for common operations:

### Add Missing Parameters

```python
import param

class Button(param.Parameterized):
    text = param.String(default="Click")
    enabled = param.Boolean(default=True)

# Incomplete instance
button = Button(text="Submit")

# Code action: "Add missing parameters"
# Result:
button = Button(
    text="Submit",
    enabled=True  # ✅ Added with default value
)
```

### Generate Parameter Documentation

```python
import param

class Model(param.Parameterized):
    # Undocumented parameter
    threshold = param.Number(default=0.5, bounds=(0, 1))

# Code action: "Generate parameter documentation"
# Result:
class Model(param.Parameterized):
    threshold = param.Number(
        default=0.5,
        bounds=(0, 1),
        doc="Number parameter with bounds (0, 1)"  # ✅ Generated
    )
```

### Convert to Parameterized Class

```python
# Regular Python class
class MyClass:
    def __init__(self, width=100, height=50):
        self.width = width
        self.height = height

# Code action: "Convert to param class"
# Result:
import param

class MyClass(param.Parameterized):
    width = param.Integer(default=100)
    height = param.Integer(default=50)
```

## Syntax Highlighting

Enhanced syntax highlighting for param-specific constructs:

### Parameter Definitions

```python
import param

class Widget(param.Parameterized):
    # Different colors for different parameter types
    width = param.Integer(default=100)      # Blue for Integer
    name = param.String(default="widget")   # Green for String
    enabled = param.Boolean(default=True)   # Purple for Boolean
```

### Decorators

```python
import param

class DataProcessor(param.Parameterized):
    # Special highlighting for param decorators
    @param.depends('input_file', 'threshold')  # Orange highlighting
    def process(self):
        pass

    @param.output('results')  # Orange highlighting
    def analyze(self):
        pass
```

## IntelliSense Features

### Smart Suggestions

Context-aware suggestions based on parameter types:

```python
import param

class Config(param.Parameterized):
    mode = param.Selector(objects=["auto", "manual"])

# Typing 'Config(mode=' shows:
# ✅ "auto" (first in list)
# ✅ "manual" (second in list)
# ❌ Other strings not suggested
```

### Parameter Snippets

Code snippets for common parameter patterns:

```python
# Typing 'param.Number' + Tab expands to:
param.Number(
    default=${1:0.0},
    bounds=(${2:0}, ${3:1}),
    doc="${4:Description}"
)

# Typing 'param.Selector' + Tab expands to:
param.Selector(
    default="${1:option1}",
    objects=[${2:"option1", "option2"}],
    doc="${3:Description}"
)
```

## Outline and Navigation

### Class Outline

Structured view of Parameterized classes:

```
📁 MyWidget (param.Parameterized)
├── 📊 Parameters
│   ├── width: Integer (default=100, bounds=(1,1000))
│   ├── height: Integer (default=50, bounds=(1,1000))
│   └── title: String (default="Widget")
├── 🔗 Dependencies
│   └── area() depends on [width, height]
└── 📝 Methods
    ├── area()
    └── resize()
```

### Go to Definition

Navigate between related elements:

```python
# Click on parameter usage
button = Button(width=200)  # Ctrl+Click on 'width'
                           # → Jumps to parameter definition

# Click on inherited parameter
class MyButton(Button):
    pass

button = MyButton(width=300)  # Ctrl+Click on 'width'
                             # → Jumps to Button.width definition
```

### Find All References

Find all usages of parameters across the project:

```python
# Right-click on parameter definition
class Widget(param.Parameterized):
    width = param.Integer(default=100)  # Right-click here
    #     ^^^^^^^^^^^^^^^^^^^^^^^^^
    #     Find all references shows:
    #     - Definition in Widget class
    #     - Usage in Widget(width=200)
    #     - Reference in @param.depends('width')
```

## Refactoring Support

### Rename Parameter

Safely rename parameters across the entire codebase:

```python
# Before: Rename 'width' parameter
class Widget(param.Parameterized):
    width = param.Integer(default=100)

    @param.depends('width')
    def area(self):
        return self.width * self.height

widget = Widget(width=200)

# After: All references updated automatically
class Widget(param.Parameterized):
    widget_width = param.Integer(default=100)  # ✅ Renamed

    @param.depends('widget_width')  # ✅ Updated
    def area(self):
        return self.widget_width * self.height  # ✅ Updated

widget = Widget(widget_width=200)  # ✅ Updated
```

### Extract Parameter

Extract hardcoded values to parameters:

```python
# Before: Hardcoded value
class Calculator(param.Parameterized):
    def calculate(self):
        return self.value * 2.5  # Hardcoded multiplier

# Select '2.5' → "Extract to parameter"
# After: New parameter created
class Calculator(param.Parameterized):
    multiplier = param.Number(default=2.5)  # ✅ New parameter

    def calculate(self):
        return self.value * self.multiplier  # ✅ Using parameter
```

## Debugger Integration

### Parameter Inspection

During debugging, inspect parameter values and metadata:

```python
# In debugger console
>>> obj.param.width
Integer(bounds=(1, 1000), default=100, name='width')

>>> obj.param.width.bounds
(1, 1000)

>>> obj.width
200  # Current value
```

### Breakpoints on Parameter Changes

Set breakpoints that trigger when parameters change:

```python
import param

class Model(param.Parameterized):
    threshold = param.Number(default=0.5)

    @param.depends('threshold', watch=True)
    def _on_threshold_change(self):
        # Breakpoint here triggers when threshold changes
        print(f"Threshold changed to {self.threshold}")
```

## Performance Features

### Background Analysis

param-lsp performs analysis in the background:

- **Non-blocking**: Editor remains responsive during analysis
- **Progressive**: Large projects analyzed incrementally
- **Prioritized**: Active files analyzed first

### Memory Management

Efficient memory usage for large projects:

- **Lazy loading**: Load analysis data on demand
- **Caching**: Cache frequently accessed information
- **Cleanup**: Automatic cleanup of unused data

### Incremental Updates

Fast response to code changes:

- **Changed lines only**: Re-analyze only modified code
- **Dependency tracking**: Update affected files automatically
- **Debouncing**: Avoid excessive re-analysis during typing

## Configuration Options

Customize IDE integration features:

```json
{
  "param-lsp": {
    "ide": {
      "show_parameter_outline": true,
      "enable_quick_fixes": true,
      "highlight_param_syntax": true,
      "show_type_hints": true,
      "enable_code_actions": true
    },
    "performance": {
      "background_analysis": true,
      "max_memory_mb": 512,
      "cache_size": 1000
    }
  }
}
```

## Editor-Specific Features

### VS Code

Special VS Code integration features:

- **Problem panel**: All param-lsp diagnostics in Problems view
- **Breadcrumbs**: Parameter hierarchy in breadcrumb navigation
- **Peek definition**: Inline parameter definition preview
- **Symbol search**: Find parameters across workspace

### Neovim

Neovim-specific enhancements:

- **Telescope integration**: Search parameters with Telescope
- **LSP commands**: Custom commands for param operations
- **Tree-sitter**: Enhanced syntax highlighting
- **Which-key**: Keybinding hints for param actions

### Emacs

Emacs integration features:

- **Company completion**: Advanced completion with Company mode
- **Flycheck**: Error checking with Flycheck
- **Helm/Ivy**: Parameter search with Helm or Ivy
- **Org-mode**: Documentation generation for Org-mode

## Troubleshooting IDE Features

Common issues and solutions:

### Missing Error Indicators

1. **Check diagnostics enabled**: Verify LSP diagnostics are enabled
2. **Restart language server**: Reload LSP client
3. **Check file associations**: Ensure Python files are recognized

### Slow Performance

1. **Reduce analysis scope**: Limit file count or inheritance depth
2. **Increase memory**: Raise memory limits
3. **Disable features**: Turn off unused features

### Quick Fixes Not Working

1. **Check code actions enabled**: Verify editor supports code actions
2. **Update editor**: Ensure recent editor version
3. **Check LSP client**: Verify code action support in LSP client

## Next Steps

- [Configuration](../configuration.md) - Optimize IDE integration
- [Troubleshooting](../troubleshooting/) - Solve IDE issues
- [Getting Started](../getting-started.md) - Basic usage examples
