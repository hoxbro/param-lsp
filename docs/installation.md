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
3. Search for "hoxbro.param-lsp" or install from [here](https://marketplace.visualstudio.com/items?itemName=hoxbro.param-lsp)
4. Click Install
5. Make sure you have param-lsp installed in your environment

The extension will automatically configure param-lsp for Python files in your workspace.

### Neovim

For Neovim users, add this to your Neovim configuration, requires version 0.11 or higher.

```lua
vim.lsp.config("param-lsp", {
	cmd = { "param-lsp" },
	filetypes = { "python" },
	root_markers = { ".git", "setup.py", "pyproject.toml" },
})

vim.lsp.enable("param-lsp")
```

### JupyterLab

To use param-lsp in JupyterLab, you need to install jupyterlab-lsp in the same environment where JupyterLab is installed.

=== "pip"

    ```bash
    pip install jupyterlab-lsp param-lsp
    ```

=== "uv"

    ```bash
    uv pip install jupyterlab-lsp param-lsp
    ```

After installation, restart JupyterLab to activate the language server. Once configured, param-lsp will provide autocompletion, validation, and hover information directly in JupyterLab notebooks for Python cells using Param.

!!! note
Make sure both jupyterlab-lsp and param-lsp are installed in the same Python environment that runs your JupyterLab instance.

## Verification

Once installed and configured, verify param-lsp is working:

1. **Check installation**: Run `param-lsp --version` in terminal
2. **Open a Python file** with Param classes
3. **Test autocompletion** by typing parameter names
4. **Verify error checking** with invalid parameter values
