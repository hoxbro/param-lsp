# param-lsp

A Language Server Protocol (LSP) implementation for the HoloViz Param library, providing intelligent IDE support for Python codebases using Param.

## Demo

<!-- Video placeholder - replace with actual video URL or embed code -->

_Demo video coming soon_

## Features

- **Autocompletion**: Context-aware completions for Param class constructors, parameter definitions, and @param.depends decorators
- **Parameter checking**: Real-time validation of parameter types, bounds, and constraints with error diagnostics
- **Hover information**: Rich documentation for Param parameters including types, bounds, descriptions, and default values
- **Cross-file analysis**: Intelligent parameter inheritance tracking across local and external Param classes (Panel, HoloViews, etc.)

## Installation

```bash
pip install param-lsp
```

## Usage

Configure your IDE to use param-lsp as the language server for Python files containing Param code.

### VS Code

Install the param-lsp VS Code extension from the marketplace.

#### Configuration

The extension provides simple configuration options:

- **`param-lsp.enable`**: Enable/disable the extension (default: `true`)
- **`param-lsp.pythonPath`**: Path to Python interpreter with param-lsp installed (optional)

**Auto-detection:** If `pythonPath` is not specified, the extension automatically detects param-lsp from:

1. Active virtual environment (`VIRTUAL_ENV`)
2. Active conda environment (`CONDA_PREFIX`)
3. Direct `param-lsp` command in PATH
4. System `python` or `python3` with param-lsp installed

**Example configuration:**

```json
{
  "param-lsp.pythonPath": "/path/to/python"
}
```

Most users won't need any configuration - the extension automatically finds param-lsp in your active environment.

### Other IDEs

Configure your IDE's LSP client to use `param-lsp` as the language server command.

## Development

```bash
# Clone the repository
git clone https://github.com/your-username/param-lsp.git
cd param-lsp

# Install dependencies
uv sync

# Run tests
pytest tests/

# Run linting
prek run --all-files
```
