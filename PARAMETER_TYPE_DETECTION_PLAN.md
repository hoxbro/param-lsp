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

## Implementation Status

### ✅ Phase 0: Setup

- [x] Write plan to file
- [x] Create todo list for tracking

### ✅ Phase 1: Add Helper Methods for Parameter Base Detection

**File**: `src/param_lsp/_analyzer/static_external_analyzer.py`
**Commit**: `9f42ff9`

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

**Status**: ✅ Completed

---

### ✅ Phase 2: Add Parameter Type Detection Loop

**File**: `src/param_lsp/_analyzer/static_external_analyzer.py`
**Location**: After Parameterized detection (around line 811), before topological sort
**Commit**: `d67d44d`

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

**Status**: ✅ Completed

---

### ✅ Phase 3: Update ParameterDetector to Accept Parameter Types

**File**: `src/param_lsp/_analyzer/ast_navigator.py`
**Commit**: `8b38ae9`

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

**Status**: ✅ Completed

---

### ✅ Phase 4: Thread Parameter Types Through Call Chain

**File**: `src/param_lsp/_analyzer/static_external_analyzer.py`
**Commit**: `2e8e622`

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

**Status**: ✅ Completed

### ✅ Phase 4.5: Cache Parameter Types for External Libraries

**File**: `src/param_lsp/cache.py`, `src/param_lsp/_analyzer/static_external_analyzer.py`
**Commit**: `b70fe0f`

Added:
- `parameter_types` list to cache JSON structure
- `set_parameter_types()` method to store detected types
- Automatic storage after detection

**Status**: ✅ Completed

### ✅ Phase 4.6: Process Libraries in Dependency Order

**Files**: `src/param_lsp/constants.py`, `src/param_lsp/__main__.py`, `src/param_lsp/_analyzer/static_external_analyzer.py`
**Commits**: `e56357f`, `9679dee`

Changed:
- `ALLOWED_EXTERNAL_LIBRARIES` from set to ordered list: `["param", "panel", "holoviews"]`
- Libraries now process dependencies first via recursive `populate_library_cache()`
- Added loading of parameter_types from cached dependencies

**Status**: ✅ Completed (but see Phase 5 blocker)

---

## ⚠️ BLOCKER: Cross-Library Parameter Type Sharing

### Problem

During cache regeneration (`--regenerate`), the cache is cleared first:
```python
external_library_cache.clear()  # Deletes all cache files
for library in all_libraries:
    inspector.populate_library_cache(library)  # Process each library
```

When processing Panel:
1. Panel tries to load param's parameter_types from disk cache
2. But param's cache hasn't been written to disk yet (only in memory)
3. Result: Panel sees 0 parameter_types from dependencies
4. Custom types like `panel.viewable.Children(param.List)` aren't detected

### Current Behavior

```bash
$ param-lsp cache --regenerate
# param processes: detects 38 parameter types ✓
# panel processes: loads 0 parameter types from dependencies ✗
# holoviews processes: loads 0 parameter types from dependencies ✗
```

### Solution

Make `detected_parameter_types` a **session-wide accumulator** that persists across library processing:

```python
class ExternalClassInspector:
    def __init__(self, ...):
        # Session-wide registry of detected parameter types
        self.session_parameter_types: set[str] = set()

    def populate_library_cache(self, library_name: str):
        # ... detection code ...

        # Start with types from previous libraries in this session
        parameter_types = set(self.session_parameter_types)

        # Add newly detected types
        # ... Round 0, 1, 2+ detection ...

        # Update session registry for next library
        self.session_parameter_types.update(parameter_types)

        # Store detected types
        self.detected_parameter_types = parameter_types
```

**Benefits:**
- Works on first run (no existing cache needed)
- Types accumulate: param → panel → holoviews
- Panel can detect `Children(param.List)` because `param.parameters.List` is already in `session_parameter_types`

**Status**: ⚠️ **BLOCKER** - Must implement before testing

---

### ❌ Phase 5: Test and Verify

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

**Status**: ❌ Blocked by cross-library sharing issue

**Current Test Results:**
```bash
$ bash run.sh panel layout/base.py
invalid-depends-parameter: Parameter 'objects' does not exist in class 'WidgetBox'
```

**Root Cause:** Panel's cache has 0 parameter_types because it can't load param's types during regeneration.

---

## Progress Tracking

- [x] Phase 1: Add helper methods
- [x] Phase 2: Add parameter type detection loop
- [x] Phase 3: Update ParameterDetector
- [x] Phase 4: Thread through call chain
- [x] Phase 4.5: Cache parameter_types
- [x] Phase 4.6: Process in dependency order
- [ ] **Phase 4.7: Session-wide parameter type accumulator** ⚠️ BLOCKER
- [ ] Phase 5: Test and verify

---

## Benefits of This Approach

1. **Eliminates runtime introspection**: No need to import and inspect param at runtime
2. **Automatic custom type support**: Works with Panel's Children, HoloViews custom types, etc.
3. **Maintainable**: No hardcoded lists to update when libraries add new parameter types
4. **Consistent**: Reuses same pattern as Parameterized detection
5. **Performance**: Single-pass detection during cache generation
6. **Accurate**: Only recognizes actual Parameter subclasses via inheritance

---

## Implementation Details

### Files Modified

1. **`src/param_lsp/_analyzer/static_external_analyzer.py`**
   - Added `_is_parameter_base()` and `_base_matches_parameter_type()` helper methods
   - Added Parameter type detection loop (Phase 1.5)
   - Updated `_convert_ast_to_class_info()` to accept `parameter_types` parameter
   - Added loading of parameter_types from cached dependencies (needs fixing)

2. **`src/param_lsp/_analyzer/ast_navigator.py`**
   - Updated `ParameterDetector.__init__()` to accept `parameter_types` set
   - Updated `is_parameter_call()` to check detected types first, fallback to hardcoded `PARAM_TYPES`

3. **`src/param_lsp/cache.py`**
   - Added `parameter_types` list to cache JSON structure
   - Added `set_parameter_types()` method

4. **`src/param_lsp/constants.py`**
   - Changed `ALLOWED_EXTERNAL_LIBRARIES` from set to ordered list

5. **`src/param_lsp/__main__.py`**
   - Updated to preserve library processing order

### Architecture Notes

- Mirrors the proven Parameterized detection algorithm
- Keep `PARAM_TYPES` for backward compatibility with local file analysis
- Parameter types detected via static analysis, no runtime introspection needed
- Each library's types build on previous libraries' types (param → panel → holoviews)

### Next Steps

1. Implement session-wide parameter type accumulator
2. Test with Panel's `Children` parameter
3. Verify original bug fix: `bash run.sh panel layout/base.py`
4. Run full test suite
5. Update plan with results
