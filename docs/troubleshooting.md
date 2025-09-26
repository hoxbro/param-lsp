# Troubleshooting & FAQ

This guide covers common issues and solutions when using param-lsp.

## Installation Issues

### "param-lsp command not found"

**Problem:** Your editor can't find the param-lsp executable.

**Solutions:**

1. **Check installation:**

   ```bash
   pip list | grep param-lsp
   ```

   If not installed, run:

   ```bash
   pip install param-lsp
   ```

2. **Check PATH:**

   ```bash
   which param-lsp
   ```

   If empty, the executable isn't in your PATH. Find your Python installation and add its scripts directory to PATH.

3. **Virtual environment issues:**
   Ensure you're installing param-lsp in the correct virtual environment:
   ```bash
   # Activate your environment first
   source venv/bin/activate  # or your activation command
   pip install param-lsp
   ```

### "Permission denied" errors

**Problem:** Permission issues when installing or running param-lsp.

**Solutions:**

1. **Use user installation:**

   ```bash
   pip install --user param-lsp
   ```

2. **Fix permissions on Unix systems:**

   ```bash
   chmod +x ~/.local/bin/param-lsp
   ```

3. **Use virtual environment:**
   ```bash
   python -m venv param_env
   source param_env/bin/activate
   pip install param-lsp
   ```

### Package conflicts

**Problem:** Dependency conflicts during installation.

**Solutions:**

1. **Create isolated environment:**

   ```bash
   python -m venv fresh_env
   source fresh_env/bin/activate
   pip install param-lsp
   ```

2. **Update pip and setuptools:**

   ```bash
   pip install --upgrade pip setuptools
   pip install param-lsp
   ```

3. **Use uv for faster, conflict-free installation:**
   ```bash
   pip install uv
   uv pip install param-lsp
   ```

## Editor-Specific Issues

### VS Code

#### Extension not working

**Problem:** param-lsp VS Code extension isn't providing features.

**Solutions:**

1. **Check extension status:**
   - Open Command Palette (Ctrl+Shift+P / Cmd+Shift+P)
   - Run "Python: Show Language Server Output"
   - Look for param-lsp related messages

2. **Restart language server:**
   - Command Palette → "Python: Restart Language Server"

3. **Check file associations:**

   ```json
   {
     "files.associations": {
       "*.py": "python"
     }
   }
   ```

4. **Manual LSP configuration:**
   Add to settings.json:
   ```json
   {
     "python.lsp.server": "param-lsp"
   }
   ```

#### Conflicting extensions

**Problem:** Multiple Python language servers active simultaneously.

**Solutions:**

1. **Disable conflicting extensions:**
   - Pylsp
   - Pyright
   - Other Python language servers

2. **Configure extension priority:**
   ```json
   {
     "python.languageServer": "param-lsp",
     "python.analysis.disabled": ["pylsp", "pyright"]
   }
   ```

### Neovim

#### LSP client not starting

**Problem:** Neovim LSP client doesn't connect to param-lsp.

**Solutions:**

1. **Check LSP logs:**

   ```vim
   :lua vim.lsp.set_log_level("debug")
   :lua print(vim.lsp.get_log_path())
   ```

2. **Verify configuration:**

   ```lua
   require'lspconfig'.param_lsp.setup{
       cmd = {"param-lsp", "--stdio"},  -- Add --stdio if needed
       on_attach = function(client, bufnr)
           print("param-lsp attached to buffer " .. bufnr)
       end
   }
   ```

3. **Manual server test:**
   ```bash
   param-lsp --stdio
   # Should start server and wait for input
   ```

#### Root directory detection issues

**Problem:** LSP server doesn't detect project root properly.

**Solutions:**

1. **Explicit root pattern:**

   ```lua
   root_dir = require'lspconfig.util'.root_pattern(
       ".git",
       "pyproject.toml",
       "setup.py",
       ".param-lsp.yaml"
   )
   ```

2. **Create project marker file:**
   ```bash
   touch .param-lsp.yaml
   ```

### Emacs

#### eglot connection failures

**Problem:** eglot can't connect to param-lsp server.

**Solutions:**

1. **Check server executable:**

   ```elisp
   (executable-find "param-lsp")
   ```

2. **Debug eglot:**

   ```elisp
   (setq eglot-events-buffer-size 2000000)
   M-x eglot-events-buffer
   ```

3. **Manual server configuration:**
   ```elisp
   (add-to-list 'eglot-server-programs
                '(python-mode . ("param-lsp" "--stdio")))
   ```

## Feature-Specific Issues

### Autocompletion not working

**Problem:** No parameter completions appear when typing.

**Diagnostic steps:**

1. **Check file is recognized as Python:**
   - Verify syntax highlighting
   - Check editor mode/language

2. **Verify param is imported:**

   ```python
   import param  # Required for param-lsp to activate
   ```

3. **Check class inheritance:**

   ```python
   # This will work:
   class MyClass(param.Parameterized):
       value = param.Number()

   # This won't work (not inheriting from Parameterized):
   class MyClass:
       value = param.Number()
   ```

4. **Test with simple example:**

   ```python
   import param

   class Test(param.Parameterized):
       x = param.Number(default=1.0)

   # Type 'Test(' and check for completions
   instance = Test()
   ```

### Hover information missing

**Problem:** No documentation appears when hovering over parameters.

**Solutions:**

1. **Check hover support in editor:**
   - Ensure hover feature is enabled
   - Test with standard Python code

2. **Verify parameter has documentation:**

   ```python
   # This will show hover info:
   value = param.Number(
       default=1.0,
       doc="This is a documented parameter"
   )

   # This will show minimal info:
   value = param.Number(default=1.0)
   ```

3. **Check external library support:**
   For Panel/HoloViews classes, ensure proper imports:
   ```python
   import panel as pn
   # Hover over 'name' should work:
   slider = pn.widgets.IntSlider(name="test")
   ```

### Error diagnostics not appearing

**Problem:** No error underlines for invalid parameter values.

**Diagnostic steps:**

1. **Check diagnostics are enabled:**

   ```json
   {
     "param-lsp": {
       "diagnostics.enable": true
     }
   }
   ```

2. **Test with obvious error:**

   ```python
   import param

   class Test(param.Parameterized):
       x = param.Integer(bounds=(1, 10))

   # This should show error diagnostic:
   Test(x=100)  # Value exceeds upper bound
   ```

3. **Verify parameter constraints:**
   ```python
   # These will trigger diagnostics:
   param.Integer(bounds=(1, 10))      # bounds checking
   param.Selector(objects=[1, 2, 3])  # choice validation
   param.String(regex=r'\d+')         # regex validation
   ```

## Performance Issues

### Slow startup

**Problem:** param-lsp takes a long time to start or analyze files.

**Solutions:**

1. **Check project size:**
   Large codebases may require more time for initial analysis.

2. **Reduce analysis scope:**

   ```json
   {
     "param-lsp": {
       "analysis.max_files": 1000,
       "analysis.exclude_patterns": ["*/venv/*", "*/node_modules/*"]
     }
   }
   ```

3. **Enable incremental analysis:**
   ```json
   {
     "param-lsp": {
       "analysis.incremental": true,
       "analysis.cache_enabled": true
     }
   }
   ```

### High memory usage

**Problem:** param-lsp consuming too much memory.

**Solutions:**

1. **Limit analysis depth:**

   ```json
   {
     "param-lsp": {
       "analysis.max_inheritance_depth": 3,
       "analysis.max_cross_file_references": 100
     }
   }
   ```

2. **Disable features if not needed:**

   ```json
   {
     "param-lsp": {
       "features.cross_file_analysis": false,
       "features.external_library_support": false
     }
   }
   ```

3. **Monitor memory usage:**
   ```bash
   # Check param-lsp process
   ps aux | grep param-lsp
   ```

## Network and Proxy Issues

### Corporate firewall blocking installation

**Problem:** Cannot install param-lsp due to network restrictions.

**Solutions:**

1. **Configure pip proxy:**

   ```bash
   pip install --proxy http://proxy.company.com:8080 param-lsp
   ```

2. **Use trusted hosts:**

   ```bash
   pip install --trusted-host pypi.org --trusted-host pypi.python.org param-lsp
   ```

3. **Download and install offline:**

   ```bash
   # On machine with internet:
   pip download param-lsp

   # On restricted machine:
   pip install param-lsp-*.whl --no-index --find-links .
   ```

## Advanced Troubleshooting

### Enable debug logging

Get detailed information about param-lsp behavior:

1. **VS Code debug logging:**

   ```json
   {
     "param-lsp": {
       "trace.server": "verbose"
     }
   }
   ```

2. **Command line debug mode:**

   ```bash
   param-lsp --log-level debug --log-file /tmp/param-lsp.log
   ```

3. **Check LSP communication:**
   ```bash
   # Monitor LSP messages
   tail -f /tmp/param-lsp.log | grep -E "(request|response|notification)"
   ```

### Manual server testing

Test param-lsp server directly:

```bash
# Start server in stdio mode
param-lsp --stdio

# Send test request (in separate terminal):
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"capabilities":{}}}' | nc localhost 8080
```

### Reset configuration

If all else fails, reset to default configuration:

1. **Remove user config:**

   ```bash
   # VS Code
   rm -rf ~/.config/Code/User/settings.json  # Backup first!

   # Neovim
   rm -rf ~/.config/nvim/lua/lsp-config.lua  # Backup first!
   ```

2. **Reinstall param-lsp:**
   ```bash
   pip uninstall param-lsp
   pip install --force-reinstall param-lsp
   ```

## Getting Help

If these solutions don't resolve your issue:

### Information to gather

Before asking for help, collect:

1. **System information:**

   ```bash
   python --version
   pip show param-lsp
   echo $PATH
   ```

2. **Editor information:**
   - Editor name and version
   - Relevant extensions installed
   - Configuration files (anonymized)

3. **Error messages:**
   - Complete error messages
   - LSP server logs
   - Editor error logs

### Where to get help

1. **GitHub Issues:** [param-lsp issues](https://github.com/hoxbro/param-lsp/issues)
2. **HoloViz Discord:** [Discord invite](https://discord.gg/UXdtYyC)
3. **Stack Overflow:** Tag questions with `param-lsp`

### Bug reports

Include in your bug report:

- **Minimal reproducible example**
- **Expected behavior**
- **Actual behavior**
- **System information** (as gathered above)
- **Steps to reproduce**

## FAQ

### Q: Does param-lsp work with all Python editors?

**A:** param-lsp works with any editor that supports the Language Server Protocol (LSP), including VS Code, Neovim, Vim, Emacs, Sublime Text, and many others.

### Q: Can I use param-lsp with Panel and HoloViews?

**A:** Yes! param-lsp has built-in support for Panel widgets and HoloViews elements, providing autocompletion and validation for their parameters.

### Q: Why isn't param-lsp detecting my custom Parameterized classes?

**A:** Ensure your classes inherit from `param.Parameterized` and that the files containing them are in your Python path or project directory.

### Q: Does param-lsp slow down my editor?

**A:** param-lsp is designed to be lightweight and uses incremental analysis to minimize performance impact. Most users don't notice any slowdown.

### Q: Can I use param-lsp in Jupyter notebooks?

**A:** Currently, param-lsp is designed for Python files (.py). Jupyter notebook support is planned for future versions.

### Q: How do I contribute to param-lsp?

**A:** Visit our [GitHub repository](https://github.com/hoxbro/param-lsp) for contribution guidelines and development setup instructions.

### Q: Is param-lsp free to use?

**A:** Yes, param-lsp is open-source and free for all use cases, including commercial projects.

### Q: How often is param-lsp updated?

**A:** param-lsp follows semantic versioning and is updated regularly with bug fixes and new features. Check our releases page for the latest updates.
