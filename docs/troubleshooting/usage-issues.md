# Usage Issues

Problems with param-lsp features and functionality after successful installation.

## Autocompletion not working

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

**Solutions:**

1. **Restart language server**
2. **Check editor LSP settings**
3. **Verify param-lsp is running**: Check task manager/process list
4. **Try with new file**: Create fresh .py file and test

## Hover information missing

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

## Error diagnostics not appearing

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

**Solutions:**

1. **Enable diagnostics in editor settings**
2. **Check error display settings**: Ensure editor shows LSP diagnostics
3. **Restart language server**
4. **Verify parameter definitions have constraints**

## Cross-file analysis problems

### Import resolution issues

**Problem:** Parameters from imported classes not recognized.

```python
# Problem: Relative imports not resolving
from .base import BaseWidget  # ❌ Can't find base module

# Solutions:
# 1. Check project structure in LSP settings
# 2. Verify __init__.py files exist
# 3. Add project root to Python path
```

**Solutions:**

1. **Check project root detection:**

   ```bash
   # Ensure project has clear root markers
   ls -la  # Look for .git, pyproject.toml, setup.py
   ```

2. **Add project marker file:**

   ```bash
   touch .param-lsp.yaml
   ```

3. **Configure Python path:**

   ```json
   {
     "python.analysis.extraPaths": ["./src", "./lib"]
   }
   ```

### Inheritance not detected

**Problem:** Inherited parameters not showing in autocompletion.

```python
# Problem: Inherited parameters not available
class Button(BaseWidget):  # ❌ BaseWidget parameters not available
    pass
```

**Solutions:**

1. **Verify import statement:**

   ```python
   # Explicit import (preferred):
   from src.widgets.base import BaseWidget

   # Relative import:
   from .base import BaseWidget
   ```

2. **Check file analysis:**
   - Ensure BaseWidget file is in project
   - Verify file is being analyzed by param-lsp
   - Check for syntax errors in BaseWidget file

3. **Restart analysis:**
   - Restart language server
   - Reload workspace/project

## External library issues

### Panel widgets not recognized

**Problem:** Panel widget parameters don't show completions.

**Solutions:**

1. **Enable external library support:**

   ```json
   {
     "param-lsp": {
       "completion.external_libraries": ["panel"]
     }
   }
   ```

2. **Verify Panel installation:**

   ```bash
   python -c "import panel; print(panel.__version__)"
   ```

3. **Test with simple example:**

   ```python
   import panel as pn

   # Should show completions:
   slider = pn.widgets.IntSlider(
       # Type here and check for completions
   )
   ```

### HoloViews elements not recognized

**Problem:** HoloViews element options don't validate.

**Solutions:**

1. **Enable HoloViews support:**

   ```json
   {
     "param-lsp": {
       "completion.external_libraries": ["holoviews"]
     }
   }
   ```

2. **Check HoloViews installation:**

   ```bash
   python -c "import holoviews; print(holoviews.__version__)"
   ```

## Performance-related issues

### Slow autocompletion

**Problem:** Completions take a long time to appear.

**Solutions:**

1. **Reduce analysis scope:**

   ```json
   {
     "param-lsp": {
       "analysis.max_files": 500,
       "analysis.max_inheritance_depth": 3
     }
   }
   ```

2. **Exclude unnecessary directories:**

   ```json
   {
     "param-lsp": {
       "analysis.exclude_patterns": ["*/venv/*", "*/node_modules/*"]
     }
   }
   ```

3. **Enable incremental analysis:**

   ```json
   {
     "param-lsp": {
       "performance.incremental": true,
       "performance.cache_enabled": true
     }
   }
   ```

### High memory usage

**Problem:** param-lsp consuming too much memory.

**Solutions:**

1. **Limit memory usage:**

   ```json
   {
     "param-lsp": {
       "performance.max_memory_mb": 256
     }
   }
   ```

2. **Disable expensive features:**

   ```json
   {
     "param-lsp": {
       "features.cross_file_analysis": false,
       "features.external_library_support": false
     }
   }
   ```

## Debugging feature issues

### Check param-lsp is running

```bash
# Check process list
ps aux | grep param-lsp  # Unix
tasklist | findstr param-lsp  # Windows
```

### Test LSP communication

1. **Check LSP logs:**

   ```json
   {
     "param-lsp": {
       "trace.server": "verbose"
     }
   }
   ```

2. **Manual server test:**

   ```bash
   # Start server manually
   param-lsp --stdio

   # Send test request (in another terminal):
   echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"capabilities":{}}}' | nc localhost 8080
   ```

### Verify file analysis

**Test if file is being analyzed:**

1. **Add syntax error deliberately:**

   ```python
   import param

   class Test(param.Parameterized):
       x = param.Number(
       # Missing closing parenthesis - should show error
   ```

2. **Check for error diagnostic** - if no error appears, file isn't being analyzed

3. **Check file patterns:**

   ```json
   {
     "param-lsp": {
       "files.include": ["**/*.py"],
       "files.exclude": ["**/test_*.py"]
     }
   }
   ```

## Editor-specific issues

### VS Code

**Problem:** Features work in some files but not others.

**Solutions:**

1. **Check workspace settings vs user settings**
2. **Verify file is in workspace folder**
3. **Check Python interpreter selection**

### Neovim

**Problem:** LSP features inconsistent.

**Solutions:**

1. **Check buffer attachment:**

   ```vim
   :lua print(vim.inspect(vim.lsp.get_active_clients()))
   ```

2. **Verify filetype detection:**

   ```vim
   :set filetype?
   ```

### Emacs

**Problem:** eglot features not working.

**Solutions:**

1. **Check eglot status:**

   ```elisp
   M-x eglot-current-server
   ```

2. **Verify mode activation:**

   ```elisp
   M-x describe-mode
   ```

## Common fixes

### Reset language server

**VS Code:**

```
Ctrl+Shift+P → "Python: Restart Language Server"
```

**Neovim:**

```vim
:LspRestart
```

**Emacs:**

```elisp
M-x eglot-shutdown
M-x eglot
```

### Clear caches

```bash
# Clear param-lsp cache
rm -rf ~/.cache/param-lsp/  # Linux
rm -rf ~/Library/Caches/param-lsp/  # macOS

# Clear editor cache (varies by editor)
```

### Reinstall param-lsp

```bash
pip uninstall param-lsp
pip install --force-reinstall param-lsp
```

## Getting help with usage issues

When reporting usage issues, include:

1. **Minimal example** that reproduces the problem
2. **Expected behavior** vs actual behavior
3. **Editor and version** information
4. **param-lsp configuration** (sanitized)
5. **LSP logs** if available

## Next Steps

- [Performance Issues](performance.md) - Optimize param-lsp performance
- [Debug Mode](debug.md) - Enable detailed logging
- [Configuration Issues](configuration-issues.md) - Fix configuration problems
