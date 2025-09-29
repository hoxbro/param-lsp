# Features Overview

param-lsp provides intelligent IDE support for Python codebases using the HoloViz Param library.

## Core Features

### [Autocompletion](autocompletion.md)

Context-aware completions for Param classes, parameters, and decorators:

- Parameter constructor completion
- Parameter definition completion
- `@param.depends` decorator completion

### [Validation](validation.md)

Real-time validation with error diagnostics:

- Bounds checking for numeric parameters
- Type validation for all parameter types
- Selector choice validation

### [Hover Information](hover-information.md)

Rich documentation when hovering over code:

- Parameter type and bounds information
- Documentation strings and default values

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
