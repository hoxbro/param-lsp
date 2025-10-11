# Editor Configuration

This guide covers configuring param-lsp for various editors and development environments.

## VS Code

1. Open VS Code
2. Go to Extensions (Ctrl+Shift+X / Cmd+Shift+X)
3. Search for "hoxbro.param-lsp" or install from [here](https://marketplace.visualstudio.com/items?itemName=hoxbro.param-lsp)
4. Click Install
5. Make sure you have param-lsp installed in your environment

The extension will automatically configure param-lsp for Python files in your workspace.

## Neovim

For Neovim users, add this to your Neovim configuration, requires version 0.11 or higher.

```lua
vim.lsp.config("param-lsp", {
	cmd = { "param-lsp" },
	filetypes = { "python" },
	root_markers = { ".git", "setup.py", "pyproject.toml" },
})

vim.lsp.enable("param-lsp")
```

## JupyterLab

To use param-lsp in JupyterLab, install param-lsp with the jupyter extra in the same environment where JupyterLab is installed.

=== "pip"

    ```bash
    pip install param-lsp[jupyter]
    ```

=== "uv"

    ```bash
    uv pip install param-lsp[jupyter]
    ```

After installation, restart JupyterLab to activate the language server. Once configured, param-lsp will provide autocompletion, validation, and hover information directly in JupyterLab notebooks for Python cells using Param.

!!! note

    The `[jupyter]` extra installs jupyterlab-lsp along with param-lsp in the same Python environment that runs your JupyterLab instance.
