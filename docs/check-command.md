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

The check command uses a format with colored output:

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
