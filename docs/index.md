# param-lsp

A Language Server Protocol (LSP) implementation for the HoloViz Param library.

## Overview

param-lsp provides IDE support for Python codebases that use Param, offering:

- **Autocompletion**: Context-aware completions for Param class constructors, parameter definitions, and @param.depends decorators
- **Type checking**: Real-time validation of parameter types, bounds, and constraints with error diagnostics
- **Hover information**: Rich documentation for Param parameters including types, bounds, descriptions, and default values
- **Cross-file analysis**: Intelligent parameter inheritance tracking across local and external Param classes (Panel, HoloViews, etc.)

## Getting Started

New to param-lsp? Start with our comprehensive [User Guide](user-guide.md) that covers:

- Installation instructions for all major editors
- Step-by-step configuration examples
- Getting started tutorial with sample code
- Basic usage patterns

## Features

Explore param-lsp's powerful IDE features in our [Features documentation](features.md):

- **Autocompletion** - Context-aware parameter completions
- **Type Checking** - Real-time validation with error diagnostics
- **Hover Information** - Rich parameter documentation
- **Cross-File Analysis** - Intelligent inheritance tracking

## Need Help?

Having issues? Check our [Troubleshooting Guide](troubleshooting.md) for:

- Common installation problems and solutions
- Editor-specific configuration issues
- Performance optimization tips
- FAQ and community resources

## Quick Example

```python
import param

class MyWidget(param.Parameterized):
    width = param.Integer(default=100, bounds=(1, 1000))
    title = param.String(default="My Widget")

# Get autocompletion, hover docs, and error checking:
widget = MyWidget(width=200, title="Dashboard")
```

## Community & Support

- **GitHub**: [Report issues and contribute](https://github.com/hoxbro/param-lsp)
- **HoloViz Discord**: [Join the community](https://discord.gg/UXdtYyC)
- **Documentation**: You're reading it!
