# Features Overview

param-lsp provides intelligent IDE support for Python codebases using the HoloViz Param library.

## Core Features

### [Autocompletion](autocompletion.md)

Context-aware completions for Param classes, parameters, and decorators:

- Parameter constructor completion
- Parameter definition completion
- `@param.depends` decorator completion

### [Type Checking](type-checking.md)

Real-time validation with error diagnostics:

- Bounds checking for numeric parameters
- Type validation for all parameter types
- Selector choice validation

### [Hover Information](hover-information.md)

Rich documentation when hovering over code:

- Parameter type and bounds information
- Documentation strings and default values
- Class-level documentation

### [Cross-File Analysis](cross-file-analysis.md)

Intelligent tracking across your codebase:

- Parameter inheritance across files
- External library support (Panel, HoloViews)
- Dependency relationship tracking

## Advanced Features

### [IDE Integration](ide-integration.md)

Enhanced editor experience:

- Error indicators and diagnostics
- Quick fixes and code actions
- Performance optimizations

### [Configuration](../configuration.md)

Customize param-lsp for your workflow:

- Diagnostics settings
- Completion preferences
- Performance tuning

## Quick Example

```python
import param

class MyWidget(param.Parameterized):
    width = param.Integer(default=100, bounds=(1, 1000))
    title = param.String(default="My Widget")

# Get autocompletion, hover docs, and error checking:
widget = MyWidget(width=200, title="Dashboard")
```

## Getting Started

New to param-lsp? Start with:

1. [Installation](../installation.md) - Set up param-lsp for your editor
2. [Getting Started](../getting-started.md) - Learn basic usage with examples
3. [Configuration](../configuration.md) - Customize for your needs

## Need Help?

- [Troubleshooting](../troubleshooting/) - Common issues and solutions
- [GitHub Issues](https://github.com/hoxbro/param-lsp/issues) - Report bugs
- [HoloViz Discord](https://discord.gg/UXdtYyC) - Community support
