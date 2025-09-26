# Installation Issues

Common problems when installing and setting up param-lsp.

## "param-lsp command not found"

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

## "Permission denied" errors

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

## Package conflicts

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

## Extension not working

### VS Code Extension Issues

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

### Conflicting Extensions

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

## Editor-Specific Setup Issues

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

## Platform-Specific Issues

### Windows

**Common Windows issues:**

1. **Python not in PATH:**

   ```cmd
   # Add Python to PATH in System Environment Variables
   C:\Python39\Scripts\
   ```

2. **Permission errors:**

   ```cmd
   # Run as administrator or use --user flag
   pip install --user param-lsp
   ```

3. **Long path issues:**

   ```cmd
   # Enable long paths in Windows 10/11
   # Group Policy: Computer Configuration > Administrative Templates > System > Filesystem
   ```

### macOS

**Common macOS issues:**

1. **Xcode command line tools:**

   ```bash
   xcode-select --install
   ```

2. **Homebrew Python conflicts:**

   ```bash
   # Use system Python or specific Python version
   /usr/bin/python3 -m pip install param-lsp
   ```

3. **Permission issues with system Python:**

   ```bash
   # Use --user installation
   python3 -m pip install --user param-lsp
   ```

### Linux

**Common Linux issues:**

1. **Missing Python development headers:**

   ```bash
   # Ubuntu/Debian
   sudo apt install python3-dev

   # Red Hat/CentOS
   sudo yum install python3-devel
   ```

2. **Alternative Python installations:**

   ```bash
   # Use specific Python version
   python3.9 -m pip install param-lsp
   ```

## Verification Steps

After resolving installation issues, verify param-lsp is working:

1. **Command line test:**

   ```bash
   param-lsp --version
   ```

2. **Python import test:**

   ```bash
   python -c "import param; print('Param version:', param.__version__)"
   ```

3. **LSP server test:**

   ```bash
   echo '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{"capabilities":{}}}' | param-lsp --stdio
   ```

4. **Editor integration test:**
   - Open a Python file with param code
   - Check for autocompletion when typing parameter names
   - Verify error diagnostics for invalid parameter values

## Getting Additional Help

If installation issues persist:

1. **Gather system information:**

   ```bash
   python --version
   pip --version
   echo $PATH
   which python
   which pip
   ```

2. **Check for conflicting packages:**

   ```bash
   pip list | grep -E "(lsp|language|server)"
   ```

3. **Create minimal test environment:**

   ```bash
   python -m venv test_env
   source test_env/bin/activate
   pip install param-lsp
   param-lsp --version
   ```

4. **Report issue with details:**
   - System information
   - Installation commands used
   - Complete error messages
   - Steps to reproduce

## Next Steps

- [Editor Configuration](editor-configuration.md) - Configure your specific editor
- [Usage Issues](usage-issues.md) - Troubleshoot feature problems
- [Debug Mode](debug.md) - Enable detailed logging
