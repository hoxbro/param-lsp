# Parameter Type Detection Plan

**Goal**: Replace hardcoded `PARAM_TYPES` with static analysis that detects Parameter subclasses, similar to how we detect Parameterized subclasses.

**Key Benefit**: Eliminates need for runtime introspection of param types and automatically supports custom Parameter types from Panel, HoloViews, and other libraries.

---

## Current State Analysis

### How Parameterized Detection Works

1. **Round 0**: Find root class (`param.Parameterized`) by name/path matching
2. **Round 1**: Find direct subclasses by checking inheritance_map
3. **Round 2+**: Iterative propagation through inheritance hierarchy
4. **Helper methods**: `_is_parameterized_base()` checks if a path is the root class

### Current Parameter Detection Problem

- Uses hardcoded `PARAM_TYPES` set in `constants.py` (String, Integer, List, etc.)
- Only recognizes `param.*` types via string checking
- Misses custom Parameter types like `panel.viewable.Children`
- Requires runtime analysis to discover new types

---

## Implementation Plan

### ✅ Phase 0: Setup

- [x] Write plan to file
- [x] Create todo list for tracking

### ⏳ Phase 1: Add Helper Methods for Parameter Base Detection

**File**: `src/param_lsp/_analyzer/static_external_analyzer.py`

Add two helper methods (following the pattern of `_is_parameterized_base`):

```python
def _is_parameter_base(self, base_path: str, library_name: str | None = None) -> bool:
    """Check if a base class path is param.Parameter.

    Args:
        base_path: Base class path to check
        library_name: Name of library being analyzed

    Returns:
        True if base class is param.Parameter
    """
    # Common forms that work across all libraries
    if base_path in (
        "param.Parameter",
        "param.parameterized.Parameter",
    ):
        return True

    # Relative import form only valid within param library's own source
    if base_path == ".parameterized.Parameter":
        return library_name == "param"

    return False

def _base_matches_parameter_type(self, base: str, parameter_types: set[str]) -> bool:
    """Check if base matches any known Parameter type.

    Args:
        base: Base class name/path to check
        parameter_types: Set of known Parameter type paths

    Returns:
        True if base matches a Parameter type
    """
    # Direct match
    if base in parameter_types:
        return True

    # Check if base is a short form of a known parameter type
    # e.g., "Children" matches "panel.viewable.Children"
    for param_type in parameter_types:
        if param_type.endswith(f".{base}"):
            return True

    return False
```

**Status**: Pending

---

### Phase 2: Add Parameter Type Detection Loop

**File**: `src/param_lsp/_analyzer/static_external_analyzer.py`
**Location**: After Parameterized detection (around line 811), before topological sort

Add new detection phase:

```python
# Phase 1.5: Iterative Parameter type detection
logger.debug("Phase 1.5: Iterative Parameter type detection")
parameter_types: set[str] = set()

# Round 0: Find param.Parameter base class itself
for class_path in inheritance_map:
    if self._is_parameter_base(class_path, library_name):
        parameter_types.add(class_path)

logger.debug(f"Round 0: Found {len(parameter_types)} Parameter root classes")

# Round 1: Find direct Parameter subclasses
for class_path, bases in inheritance_map.items():
    if any(self._is_parameter_base(base, library_name) for base in bases):
        parameter_types.add(class_path)

logger.debug(f"Round 1: Found {len(parameter_types)} direct Parameter subclasses")

# Round 2+: Propagate iteratively through inheritance hierarchy
round_num = 2
changed = True
while changed:
    changed = False
    for class_path, bases in inheritance_map.items():
        if class_path not in parameter_types:
            # Check if any base class is already marked as Parameter type
            for base in bases:
                if self._base_matches_parameter_type(base, parameter_types):
                    parameter_types.add(class_path)
                    changed = True
                    break

    if changed:
        logger.debug(
            f"Round {round_num}: Total {len(parameter_types)} Parameter types"
        )
        round_num += 1

logger.debug(f"Final: Found {len(parameter_types)} total Parameter types")

# Store for use in parameter extraction
self.detected_parameter_types = parameter_types
```

**Status**: Pending

---

### Phase 3: Update ParameterDetector to Accept Parameter Types

**File**: `src/param_lsp/_analyzer/ast_navigator.py`

**3.1**: Update `__init__` method:

```python
def __init__(self, imports: dict[str, str], parameter_types: set[str] | None = None):
    """Initialize parameter detector.

    Args:
        imports: Dictionary mapping import aliases to full module names
        parameter_types: Set of detected Parameter type paths from static analysis
    """
    self.imports = imports
    self.parameter_types = parameter_types or set()
```

**3.2**: Update `is_parameter_call` method:

```python
def is_parameter_call(self, node: Node) -> bool:
    """Check if a tree-sitter call node represents a parameter type call.

    Uses both statically detected parameter types and hardcoded PARAM_TYPES
    for backward compatibility.
    """
    if node.type != "call":
        return False

    func_node = node.child_by_field_name("function")
    if not func_node:
        return False

    # Extract function name
    func_name = None
    if func_node.type == "identifier":
        func_name = _treesitter.get_value(func_node)
    elif func_node.type == "attribute":
        attr_node = func_node.child_by_field_name("attribute")
        if attr_node:
            func_name = _treesitter.get_value(attr_node)

    if func_name:
        # Check hardcoded PARAM_TYPES (for backward compatibility)
        if func_name in PARAM_TYPES:
            return True

        # Check if it's an imported type
        if func_name in self.imports:
            imported_full_name = self.imports[func_name]

            # PRIMARY CHECK: Use statically detected parameter types
            if self.parameter_types and imported_full_name in self.parameter_types:
                return True

            # FALLBACK: Check if it's from param module (for local analysis)
            if imported_full_name.startswith("param."):
                param_type = imported_full_name.split(".")[-1]
                return param_type in PARAM_TYPES

    return False
```

**Status**: Pending

---

### Phase 4: Thread Parameter Types Through Call Chain

**File**: `src/param_lsp/_analyzer/static_external_analyzer.py`

**4.1**: Store parameter_types as instance variable (add in detection loop):

```python
# After detection loop completes:
self.detected_parameter_types = parameter_types
```

**4.2**: Update `_convert_ast_to_class_info` signature:

```python
def _convert_ast_to_class_info(
    self,
    class_node: Node,
    imports: dict[str, str],
    full_class_path: str,
    file_path: Path,
    inheritance_map: dict[str, list[str]] | None = None,
    class_ast_nodes: dict[str, tuple[Node, dict[str, str], Path]] | None = None,
    parameter_types: set[str] | None = None,  # NEW
) -> ParameterizedInfo:
```

**4.3**: Update ParameterDetector instantiation in `_convert_ast_to_class_info`:

```python
parameter_detector = ParameterDetector(imports, parameter_types)
```

**4.4**: Update all calls to `_convert_ast_to_class_info` to pass parameter_types:

```python
# Around line 900
class_info = self._convert_ast_to_class_info(
    class_node,
    file_imports,
    class_path,
    source_path,
    inheritance_map,
    class_ast_nodes,
    self.detected_parameter_types,  # NEW
)
```

**Status**: Pending

---

### Phase 5: Test and Verify

**5.1**: Test with Panel's custom types:

```bash
param-lsp cache --regenerate
python3 -c "
import json
with open('~/.cache/param-lsp/panel-*.json') as f:
    data = json.load(f)
    ll = data['classes']['panel.layout.base.ListLike']
    print('Has objects?', 'objects' in ll['parameters'])
"
```

**5.2**: Test original bug case:

```bash
bash run.sh panel layout/base.py
# Should NOT show error about 'objects' parameter
```

**5.3**: Run tests:

```bash
pytest tests/
```

**5.4**: Run linting:

```bash
prek run --all-files
```

**5.5**: Run type checking:

```bash
basedpyright src tests
```

**Status**: Pending

---

## Benefits of This Approach

1. **Eliminates runtime introspection**: No need to import and inspect param at runtime
2. **Automatic custom type support**: Works with Panel's Children, HoloViews custom types, etc.
3. **Maintainable**: No hardcoded lists to update when libraries add new parameter types
4. **Consistent**: Reuses same pattern as Parameterized detection
5. **Performance**: Single-pass detection during cache generation
6. **Accurate**: Only recognizes actual Parameter subclasses via inheritance

---

## Progress Tracking

- [ ] Phase 1: Add helper methods
- [ ] Phase 2: Add parameter type detection loop
- [ ] Phase 3: Update ParameterDetector
- [ ] Phase 4: Thread through call chain
- [ ] Phase 5: Test and verify

---

## Notes

- Keep `PARAM_TYPES` for backward compatibility with local file analysis (where we don't have inheritance_map)
- Consider caching detected parameter_types per library in future optimization
- This approach mirrors the proven Parameterized detection algorithm
