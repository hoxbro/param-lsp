# Param LSP - VS Code Extension

A Language Server Protocol (LSP) implementation for the HoloViz Param library, providing intelligent IDE support for Python codebases using Param.

## Features

- **Autocompletion**: Context-aware completions for Param class constructors, parameter definitions, and @param.depends decorators
- **Parameter checking**: Real-time validation of parameter types, bounds, and constraints with error diagnostics
- **Hover information**: Rich documentation for Param parameters including types, bounds, descriptions, and default values
- **Cross-file analysis**: Intelligent parameter inheritance tracking across local and external Param classes (Panel, HoloViews, etc.)

## Installation

1. Install the param-lsp package, see more ways [here](https://param-lsp.readthedocs.io/en/latest/installation/#installing-param-lsp)

   ```bash
   pip install param-lsp
   ```

2. Ensure `param-lsp` is available to you:

   ```bash
   param-lsp --version
   ```

3. Install this VS Code extension from the marketplace.

## Configuration

The extension provides simple configuration options:

- **`param-lsp.enable`**: Enable/disable the extension (default: `true`)
- **`param-lsp.trace.server`**: Control communication logging between VS Code and the language server (default: `off`)

The extension automatically detects the `param-lsp` command from your PATH. No additional configuration is required.

## Troubleshooting

### Extension shows "param-lsp not found" error

1. **Check installation**: Make sure param-lsp is installed:

   ```bash
   pip install param-lsp
   ```

2. **Verify PATH**: Test that param-lsp is available in your PATH:

   ```bash
   param-lsp --version
   ```

3. **Check your shell configuration**: Ensure your PATH is correctly configured in your shell profile (`.bashrc`, `.zshrc`, etc.)

### Works in terminal but not in VS Code

VS Code may not be using the same environment as your terminal. Solutions:

1. **Restart VS Code**: After installing param-lsp, restart VS Code to pick up PATH changes
2. **Launch from terminal**: Start VS Code from your terminal where param-lsp works:
   ```bash
   code .
   ```
3. **Check VS Code PATH**: Verify VS Code can see param-lsp by running `param-lsp --version` in the VS Code integrated terminal

## Development

See the main [param-lsp repository](https://github.com/hoxbro/param-lsp) for development instructions.

## License

This extension is part of the param-lsp project. See the main repository for license information.
