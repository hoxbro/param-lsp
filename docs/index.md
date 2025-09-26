# param-lsp

A Language Server Protocol (LSP) implementation for the HoloViz Param library.

## Overview

param-lsp provides IDE support for Python codebases that use Param, offering:

- **Autocompletion**: Context-aware completions for Param class constructors, parameter definitions, and @param.depends decorators
- **Type checking**: Real-time validation of parameter types, bounds, and constraints with error diagnostics
- **Hover information**: Rich documentation for Param parameters including types, bounds, descriptions, and default values
- **Cross-file analysis**: Intelligent parameter inheritance tracking across local and external Param classes (Panel, HoloViews, etc.)

## Getting Started

New to param-lsp? Follow our step-by-step guides:

- **[Installation](installation.md)** - Install and configure param-lsp for your editor
- **[Getting Started](getting-started.md)** - Learn basic usage with practical examples
- **[Configuration](configuration.md)** - Customize param-lsp for your workflow

## Features

Explore param-lsp's powerful IDE features:

- **[Autocompletion](features/autocompletion.md)** - Context-aware parameter completions
- **[Type Checking](features/type-checking.md)** - Real-time validation with error diagnostics
- **[Hover Information](features/hover-information.md)** - Rich parameter documentation
- **[Cross-File Analysis](features/cross-file-analysis.md)** - Intelligent inheritance tracking
- **[IDE Integration](features/ide-integration.md)** - Enhanced editor experience

## Need Help?

Having issues? Check our organized troubleshooting guides:

- **[Installation Issues](troubleshooting/installation-issues.md)** - Setup and installation problems
- **[Usage Issues](troubleshooting/usage-issues.md)** - Feature and functionality problems
- **[Troubleshooting Overview](troubleshooting/)** - Complete troubleshooting guide

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
