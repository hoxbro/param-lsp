# Param LSP - VS Code Extension

A Language Server Protocol (LSP) implementation for the HoloViz Param library, providing intelligent IDE support for Python codebases using Param.

## Features

- **Autocompletion**: Context-aware completions for Param class constructors, parameter definitions, and @param.depends decorators
- **Parameter checking**: Real-time validation of parameter types, bounds, and constraints with error diagnostics
- **Hover information**: Rich documentation for Param parameters including types, bounds, descriptions, and default values
- **Cross-file analysis**: Intelligent parameter inheritance tracking across local and external Param classes (Panel, HoloViews, etc.)

## Installation

1. Install the param-lsp package:

   ```bash
   pip install param-lsp
   ```

2. Install this VS Code extension from the marketplace.

## Configuration

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

## Troubleshooting

### Extension shows "param-lsp not found" error

1. **Check your environment**: Make sure param-lsp is installed in your active virtual environment or conda environment:

   ```bash
   pip install param-lsp
   ```

2. **Verify installation**: Test that param-lsp works from command line:

   ```bash
   param-lsp --version
   # or
   python -c "import param_lsp; print('param-lsp is installed')"
   ```

3. **Manual configuration**: If auto-detection fails, specify the Python path explicitly:
   ```json
   {
     "param-lsp.pythonPath": "/path/to/your/python"
   }
   ```

### Works in terminal but not in VS Code

This usually means VS Code is not using the same Python environment as your terminal. Make sure:

1. Your virtual environment is activated when you start VS Code
2. VS Code's Python interpreter is set to the same environment where param-lsp is installed
3. The `param-lsp.pythonPath` setting points to the correct Python interpreter

## Development

See the main [param-lsp repository](https://github.com/hoxbro/param-lsp) for development instructions.

## License

This extension is part of the param-lsp project. See the main repository for license information.
