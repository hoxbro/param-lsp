# Installation

This guide covers installing param-lsp and configuring it for your development environment.

## Installing param-lsp

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

## Verification

Once installed and configured, verify param-lsp is working:

1. **Check installation**: Run `param-lsp --version` in terminal
2. **Open a Python file** with Param classes
3. **Test autocompletion** by typing parameter names
4. **Verify error checking** with invalid parameter values

## Next Steps

- [Getting Started](getting-started.md) - Learn basic usage with examples
- [Configuration](configuration.md) - Advanced configuration options
- [Installation Issues](installation-issues.md) - Troubleshoot installation problems
