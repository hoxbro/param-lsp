# User Guide

This guide will help you install and configure param-lsp for your development environment.

## Installation

param-lsp can be installed via pip:

```bash
pip install param-lsp
```

Or using uv for faster installation:

```bash
uv add param-lsp
```

## Editor Configuration

### VS Code

#### Option 1: VS Code Extension (Recommended)

1. Open VS Code
2. Go to Extensions (Ctrl+Shift+X / Cmd+Shift+X)
3. Search for "param-lsp"
4. Click Install

The extension will automatically configure param-lsp for Python files in your workspace.

#### Option 2: Manual Configuration

If you prefer manual configuration or the extension isn't available:

1. Install param-lsp via pip (see Installation section above)
2. Install the "Python LSP" extension if not already installed
3. Add the following to your VS Code settings.json:

```json
{
  "python.lsp.server": "param-lsp",
  "python.analysis.extraPaths": ["./src"]
}
```

### Neovim

For Neovim users with LSP support:

#### Using nvim-lspconfig

Add this to your Neovim configuration:

```lua
require'lspconfig'.param_lsp.setup{
    cmd = {"param-lsp"},
    filetypes = {"python"},
    root_dir = require'lspconfig.util'.root_pattern(".git", "pyproject.toml", "setup.py"),
    settings = {}
}
```

#### Using coc.nvim

Add to your `coc-settings.json`:

```json
{
  "languageserver": {
    "param-lsp": {
      "command": "param-lsp",
      "filetypes": ["python"],
      "rootPatterns": [".git", "pyproject.toml", "setup.py"]
    }
  }
}
```

### Vim with vim-lsp

Add this to your vimrc:

```vim
if executable('param-lsp')
    au User lsp_setup call lsp#register_server({
        \ 'name': 'param-lsp',
        \ 'cmd': {server_info->['param-lsp']},
        \ 'whitelist': ['python'],
        \ })
endif
```

### Emacs

#### Using lsp-mode

Add to your Emacs configuration:

```elisp
(use-package lsp-mode
  :hook (python-mode . lsp-deferred)
  :custom
  (lsp-python-server-command '("param-lsp")))
```

#### Using eglot

```elisp
(use-package eglot
  :config
  (add-to-list 'eglot-server-programs '(python-mode . ("param-lsp"))))
```

### Sublime Text

#### Using LSP package

1. Install the LSP package via Package Control
2. Add this to your LSP settings:

```json
{
  "clients": {
    "param-lsp": {
      "enabled": true,
      "command": ["param-lsp"],
      "selector": "source.python"
    }
  }
}
```

## Getting Started

### Basic Usage

Once configured, param-lsp will automatically provide IDE features for Python files containing Param code:

1. **Open a Python file** with Param classes
2. **Start typing** to see autocompletions
3. **Hover over parameters** to see documentation
4. **Watch for error diagnostics** for type and constraint violations

### Example Param Code

Create a new Python file with this example to test param-lsp features:

```python
import param

class MyWidget(param.Parameterized):
    """A simple parameterized widget."""

    # Try hovering over these parameters
    width = param.Integer(
        default=100,
        bounds=(1, 1000),
        doc="Width of the widget in pixels"
    )

    height = param.Integer(
        default=50,
        bounds=(1, 1000),
        doc="Height of the widget in pixels"
    )

    title = param.String(
        default="My Widget",
        doc="Title displayed on the widget"
    )

    enabled = param.Boolean(
        default=True,
        doc="Whether the widget is enabled"
    )

    @param.depends('width', 'height')
    def area(self):
        """Calculate the area of the widget."""
        return self.width * self.height

# Try autocompletion when creating instances
widget = MyWidget(
    # Type 'w' and see width parameter completion
    # Type 'width=1500' and see bounds violation error
)
```

### What to Expect

With the example above, you should see:

- **Autocompletion** when typing parameter names in constructor
- **Hover documentation** when hovering over parameter definitions
- **Error diagnostics** if you set values outside bounds (try `width=1500`)
- **Method dependency tracking** for `@param.depends` decorators

## Configuration

### Workspace Settings

param-lsp respects standard Python project configurations:

- `pyproject.toml` - Python project metadata
- `.git` - Git repository root
- `setup.py` - Legacy Python setup files

### Advanced Configuration

For advanced users, param-lsp supports additional configuration options:

```json
{
  "param-lsp": {
    "trace.server": "verbose",
    "python.analysis.extraPaths": ["./src", "./lib"],
    "diagnostics.enable": true
  }
}
```

## Troubleshooting

If param-lsp isn't working as expected:

1. **Check installation**: Run `param-lsp --version` in terminal
2. **Verify Python path**: Ensure param-lsp can find your Python environment
3. **Check file associations**: Ensure your editor recognizes .py files
4. **Restart your editor** after configuration changes

For more detailed troubleshooting, see our [Troubleshooting Guide](troubleshooting.md).

## Next Steps

- Explore [Features](features.md) for detailed examples
- Check out [API Reference](api-reference.md) for technical details
- Join our community for support and discussions
