# Configuration

This guide covers advanced configuration options for param-lsp.

## Workspace Settings

param-lsp respects standard Python project configurations:

- `pyproject.toml` - Python project metadata
- `.git` - Git repository root
- `setup.py` - Legacy Python setup files

## Basic Configuration

### VS Code Settings

Add to your `settings.json`:

```json
{
  "param-lsp": {
    "trace.server": "verbose",
    "python.analysis.extraPaths": ["./src", "./lib"],
    "diagnostics.enable": true
  }
}
```

### Neovim Configuration

```lua
require'lspconfig'.param_lsp.setup{
    cmd = {"param-lsp"},
    settings = {
        ["param-lsp"] = {
            diagnostics = {
                enable = true,
                bounds_checking = true
            }
        }
    }
}
```

## Advanced Configuration Options

### Diagnostics Settings

Control error checking and validation:

```json
{
  "param-lsp": {
    "diagnostics": {
      "enable": true,
      "bounds_checking": true,
      "type_validation": true,
      "unknown_parameters": "warning"
    }
  }
}
```

**Options:**

- `enable` - Enable/disable all diagnostics
- `bounds_checking` - Validate parameter bounds
- `type_validation` - Check parameter types
- `unknown_parameters` - `"error"`, `"warning"`, or `"ignore"`

### Completion Settings

Customize autocompletion behavior:

```json
{
  "param-lsp": {
    "completion": {
      "include_inherited": true,
      "show_parameter_docs": true,
      "external_libraries": ["panel", "holoviews", "datashader"],
      "max_completions": 50
    }
  }
}
```

**Options:**

- `include_inherited` - Show parameters from parent classes
- `show_parameter_docs` - Include documentation in completions
- `external_libraries` - Libraries to analyze for parameter completion
- `max_completions` - Maximum number of completion items

### Analysis Settings

Control code analysis behavior:

```json
{
  "param-lsp": {
    "analysis": {
      "cross_file": true,
      "external_classes": true,
      "max_inheritance_depth": 5,
      "max_files": 1000,
      "exclude_patterns": ["*/venv/*", "*/node_modules/*"]
    }
  }
}
```

**Options:**

- `cross_file` - Analyze parameter inheritance across files
- `external_classes` - Support external library classes
- `max_inheritance_depth` - Maximum inheritance chain to follow
- `max_files` - Maximum number of files to analyze
- `exclude_patterns` - Glob patterns for files to exclude

### Performance Settings

Optimize param-lsp performance:

```json
{
  "param-lsp": {
    "performance": {
      "incremental": true,
      "cache_enabled": true,
      "max_memory_mb": 512,
      "background_analysis": true
    }
  }
}
```

**Options:**

- `incremental` - Use incremental analysis for faster updates
- `cache_enabled` - Cache analysis results
- `max_memory_mb` - Maximum memory usage limit
- `background_analysis` - Analyze files in background

## Project-Specific Configuration

### .param-lsp.yaml

Create a `.param-lsp.yaml` file in your project root:

```yaml
diagnostics:
  enable: true
  bounds_checking: true
  type_validation: true

completion:
  external_libraries:
    - panel
    - holoviews
    - bokeh

analysis:
  exclude_patterns:
    - "*/tests/*"
    - "*/build/*"
    - "*/dist/*"
```

### pyproject.toml Integration

Add param-lsp settings to your `pyproject.toml`:

```toml
[tool.param-lsp]
[tool.param-lsp.diagnostics]
enable = true
bounds_checking = true

[tool.param-lsp.completion]
external_libraries = ["panel", "holoviews"]

[tool.param-lsp.analysis]
cross_file = true
max_inheritance_depth = 3
```

## Editor-Specific Configuration

### VS Code Workspace Settings

Create `.vscode/settings.json` for project-specific settings:

```json
{
  "param-lsp": {
    "python.analysis.extraPaths": ["./src"],
    "completion.external_libraries": ["panel"]
  },
  "python.defaultInterpreterPath": "./venv/bin/python"
}
```

### Neovim Per-Project Config

Use `exrc` or project-specific configs:

```lua
-- In .nvim.lua or similar
require'lspconfig'.param_lsp.setup{
    root_dir = require'lspconfig.util'.root_pattern(".param-lsp.yaml", ".git"),
    settings = {
        ["param-lsp"] = {
            completion = {
                external_libraries = {"panel", "holoviews"}
            }
        }
    }
}
```

## Logging and Debugging

### Enable Debug Logging

For troubleshooting, enable verbose logging:

```json
{
  "param-lsp": {
    "trace.server": "verbose",
    "log.level": "debug",
    "log.file": "/tmp/param-lsp.log"
  }
}
```

### Log Locations

Default log locations:

- **Linux**: `~/.cache/param-lsp/param-lsp.log`
- **macOS**: `~/Library/Logs/param-lsp/param-lsp.log`
- **Windows**: `%LOCALAPPDATA%\param-lsp\Logs\param-lsp.log`

## Environment Variables

Configure param-lsp via environment variables:

```bash
# Enable debug logging
export PARAM_LSP_LOG_LEVEL=debug

# Set custom config file
export PARAM_LSP_CONFIG=/path/to/config.yaml

# Disable external library analysis
export PARAM_LSP_NO_EXTERNAL_LIBS=1
```

## Common Configuration Patterns

### Minimal Configuration

For basic usage with good performance:

```json
{
  "param-lsp": {
    "diagnostics.enable": true,
    "completion.include_inherited": true,
    "analysis.cross_file": false
  }
}
```

### Full-Featured Configuration

For maximum functionality:

```json
{
  "param-lsp": {
    "diagnostics": {
      "enable": true,
      "bounds_checking": true,
      "type_validation": true
    },
    "completion": {
      "include_inherited": true,
      "show_parameter_docs": true,
      "external_libraries": ["panel", "holoviews", "datashader"]
    },
    "analysis": {
      "cross_file": true,
      "external_classes": true,
      "max_inheritance_depth": 5
    }
  }
}
```

### Performance-Optimized Configuration

For large codebases:

```json
{
  "param-lsp": {
    "analysis": {
      "max_files": 500,
      "exclude_patterns": ["*/venv/*", "*/node_modules/*", "*/build/*"],
      "max_inheritance_depth": 3
    },
    "performance": {
      "incremental": true,
      "cache_enabled": true,
      "max_memory_mb": 256
    }
  }
}
```

## Troubleshooting Configuration

If your configuration isn't working:

1. **Check syntax**: Validate JSON/YAML syntax
2. **Check file location**: Ensure config files are in the right place
3. **Restart editor**: Some changes require editor restart
4. **Check logs**: Look for configuration errors in logs
5. **Test minimal config**: Start with basic settings and add incrementally

## Next Steps

- [Features](features/) - Learn about param-lsp capabilities
- [Troubleshooting](troubleshooting/) - Solve configuration issues
- [Installation Issues](installation-issues.md) - Fix installation problems
