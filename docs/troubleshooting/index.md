# Troubleshooting Guide

This section covers common issues and solutions when using param-lsp.

## Quick Solutions

### Most Common Issues

1. **[param-lsp command not found](installation-issues.md#param-lsp-command-not-found)** - Installation and PATH problems
2. **[No autocompletion](usage-issues.md#autocompletion-not-working)** - Missing completions in editor
3. **[Extension not working](installation-issues.md#extension-not-working)** - VS Code extension issues
4. **[No error diagnostics](usage-issues.md#error-diagnostics-not-appearing)** - Missing error indicators

### By Category

## Installation & Setup

Common problems when installing and configuring param-lsp:

- **[Installation Issues](installation-issues.md)** - Problems installing param-lsp
- **[Editor Configuration](editor-configuration.md)** - Setting up your editor
- **[Permission Problems](installation-issues.md#permission-denied-errors)** - File and execution permissions

## Usage & Features

Issues with param-lsp features and functionality:

- **[Usage Issues](usage-issues.md)** - Feature-specific problems
- **[Performance Issues](performance.md)** - Slow startup, high memory usage
- **[Cross-File Analysis](usage-issues.md#cross-file-analysis-problems)** - Import and inheritance issues

## Advanced Troubleshooting

For complex issues and debugging:

- **[Debug Mode](debug.md)** - Enable logging and debugging
- **[Configuration Problems](configuration-issues.md)** - Settings and config files
- **[Network Issues](installation-issues.md#network-and-proxy-issues)** - Proxy and firewall problems

## Getting Help

If these guides don't solve your issue:

### Before Asking for Help

Collect this information:

1. **System info**: `python --version`, `pip show param-lsp`
2. **Editor info**: Editor name/version, relevant extensions
3. **Error messages**: Complete error text and logs
4. **Minimal example**: Code that reproduces the issue

### Where to Get Help

- **[GitHub Issues](https://github.com/hoxbro/param-lsp/issues)** - Bug reports and feature requests
- **[HoloViz Discord](https://discord.gg/UXdtYyC)** - Community support
- **[Stack Overflow](https://stackoverflow.com/questions/tagged/param-lsp)** - Q&A format

## FAQ

### General Questions

**Q: Does param-lsp work with all Python editors?**

A: param-lsp works with any editor that supports the Language Server Protocol (LSP), including VS Code, Neovim, Vim, Emacs, Sublime Text, and many others.

**Q: Can I use param-lsp with Panel and HoloViews?**

A: Yes! param-lsp has built-in support for Panel widgets and HoloViews elements, providing autocompletion and validation for their parameters.

**Q: Does param-lsp slow down my editor?**

A: param-lsp is designed to be lightweight and uses incremental analysis to minimize performance impact. Most users don't notice any slowdown.

### Feature Questions

**Q: Why isn't param-lsp detecting my custom Parameterized classes?**

A: Ensure your classes inherit from `param.Parameterized` and that the files containing them are in your Python path or project directory.

**Q: Can I use param-lsp in Jupyter notebooks?**

A: Currently, param-lsp is designed for Python files (.py). Jupyter notebook support is planned for future versions.

### Contribution Questions

**Q: How do I contribute to param-lsp?**

A: Visit our [GitHub repository](https://github.com/hoxbro/param-lsp) for contribution guidelines and development setup instructions.

**Q: Is param-lsp free to use?**

A: Yes, param-lsp is open-source and free for all use cases, including commercial projects.

## Quick Reference

### Verification Commands

```bash
# Check installation
param-lsp --version

# Test Python import
python -c "import param; print(param.__version__)"

# Check PATH
which param-lsp  # Unix
where param-lsp  # Windows
```

### Common Fix Commands

```bash
# Reinstall param-lsp
pip uninstall param-lsp
pip install param-lsp

# Fix permissions (Unix)
chmod +x ~/.local/bin/param-lsp

# Clear cache
rm -rf ~/.cache/param-lsp/  # Linux
rm -rf ~/Library/Caches/param-lsp/  # macOS
```

### Editor Restart Commands

```bash
# VS Code: Restart language server
# Ctrl+Shift+P → "Python: Restart Language Server"

# Neovim: Restart LSP
# :LspRestart

# Emacs: Restart eglot
# M-x eglot-shutdown → M-x eglot
```
