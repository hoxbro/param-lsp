# Check Command

The `param-lsp check` command provides command-line validation of Python files for Param-related errors and warnings.

## Overview

Run param-lsp's validation engine from the command line to check your Python files for type errors, bounds violations, and other Param-related issues without opening an editor.

## Usage

=== "Single File"

    ```bash
    param-lsp check myfile.py
    ```

=== "Multiple Files"

    ```bash
    param-lsp check file1.py file2.py file3.py
    ```

=== "Directory"

    ```bash
    param-lsp check src/
    ```

    Recursively checks all `.py` files in the directory, excluding `.venv`, `.pixi`, and `node_modules`.

=== "Current Directory"

    ```bash
    param-lsp check .
    ```

## Output Format

The check command uses a ruff-like format with colored output:

```
type-mismatch: Parameter 'value' of type String expects str but got int
  --> /path/to/file.py:4:5
   |
 2 |
 3 | class Widget(param.Parameterized):
 4 |     value = param.String(default=123)
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 5 |     count = param.Integer(default=42)
 6 |
   |

Found 1 error(s) and 0 warning(s) in 1 file(s)
```

**Output features:**

- **Error codes** (colored): `type-mismatch:`, `bounds-violation:`, etc.
- **Location pointer**: `-->` shows exact file, line, and column
- **Context lines**: Shows 2 lines before and after the error (dimmed)
- **Precise underlines**: Carets (`^`) highlight the exact error location
- **Color coding**:
  - Red for errors
  - Yellow for warnings
  - Cyan for location information

## Common Error Types

### Type Mismatches

Detect when parameter defaults don't match their declared types:

```python
import param

class Widget(param.Parameterized):
    title = param.String(default=123)  # ❌ Error: Expected str, got int
```

### Bounds Violations

Catch values outside defined bounds:

```python
import param

class Widget(param.Parameterized):
    opacity = param.Number(default=1.5, bounds=(0.0, 1.0))  # ❌ Error: 1.5 > 1.0
```

### Invalid Dependencies

Detect non-existent parameters in `@param.depends`:

```python
import param

class Widget(param.Parameterized):
    value = param.String(default="hello")

    @param.depends('nonexistent')  # ❌ Error: Parameter 'nonexistent' not found
    def compute(self):
        return self.value
```

## Options

### Log Level

Control verbosity with `--log-level`:

```bash
# Minimal output (default for check)
param-lsp check file.py

# Show debug information
param-lsp --log-level DEBUG check file.py
```

## Exit Codes

- **0**: No errors found
- **1**: One or more errors found

## Integration

### CI/CD Pipelines

Use in continuous integration to catch Param errors early:

```yaml
# GitHub Actions example
- name: Check Param types
  run: param-lsp check src/
```

### Pre-commit Hook

Add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: param-lsp-check
        name: param-lsp check
        entry: param-lsp check
        language: system
        types: [python]
        pass_filenames: true
```

## Performance

- Files are processed in **sorted order** for consistent output
- **Parallel processing** for multiple files
- **Caches** external library metadata for faster subsequent runs

## Limitations

- Only checks files that import `param`
- Does not execute code, only performs static analysis
- May not catch all runtime validation errors
