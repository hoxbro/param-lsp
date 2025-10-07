# Cache Population Plan - Fix Missing Classes

## Problem Statement

Current implementation finds only **57 classes** vs **253 classes** in v1.0.0.
Missing **224 classes** (88% coverage gap).

### Root Cause

Static analysis with `_inherits_from_parameterized()` only detects:

- Direct inheritance: `class Foo(param.Parameterized)`
- Simple imports: `class Foo(Parameterized)` where Parameterized is imported

It FAILS to detect:

- Transitive inheritance: `class ChatFeed(ListPanel)` where `ListPanel` itself inherits from `Parameterized`
- Cross-file inheritance chains
- Complex inheritance through intermediate Panel/HoloViews base classes

## Current Approach (Static Analysis Only)

```
panel.chat.feed.ChatFeed -> ListPanel -> ??? (chain broken, not detected)
```

## Solution: Pure Static with Iterative Resolution ⭐⭐ RECOMMENDED

**Build complete inheritance graph, then iteratively mark Parameterized classes**

Build a complete inheritance map from static analysis, then propagate Parameterized status iteratively.

### Algorithm:

```
Phase 1: Build Class Inheritance Map
------------------------------------
For each Python file in library:
    Parse AST
    For each class definition:
        Extract: class_name, base_classes (as strings)
        Store: inheritance_map[full_class_path] = [base_class_paths...]

Result: Complete inheritance graph
Example: {
    "panel.chat.feed.ChatFeed": ["panel.layout.base.ListPanel"],
    "panel.layout.base.ListPanel": ["panel.viewable.Viewable"],
    "panel.viewable.Viewable": ["param.Parameterized"],
}

Phase 2: Iterative Parameterized Detection
------------------------------------------
Round 1:
    For each class in inheritance_map:
        If any base is "param.Parameterized" (direct):
            Mark as Parameterized

Round 2...N:
    For each unmarked class in inheritance_map:
        If any base is already marked as Parameterized:
            Mark as Parameterized

    Repeat until no new classes marked

Result: Set of all Parameterized class paths

Phase 3: Extract Parameters
----------------------------
For each class marked as Parameterized:
    Use existing static analysis to extract parameter details
    Cache the result
```

### Why This Works:

1. **No imports needed** - Pure static analysis
2. **Handles transitive inheritance** - Iterative propagation catches all chains
3. **Simple logic** - Just string matching on base class names
4. **Efficient** - Each file parsed once, then simple graph traversal
5. **Complete coverage** - Will find all Parameterized subclasses

### Implementation Pseudocode:

```python
def populate_library_cache_iterative(self, library_name: str) -> int:
    """Use pure static analysis with iterative inheritance resolution."""

    # Phase 1: Build inheritance map
    inheritance_map = {}  # full_class_path -> [base_class_paths]
    class_ast_nodes = {}  # full_class_path -> (ast_node, imports, source_file)

    source_paths = self._discover_library_sources(library_name)

    for source_path in source_paths:
        tree = parso.parse(source_path.read_text())
        file_imports = self._extract_imports(tree)

        for class_node in self._find_all_classes(tree):
            class_name = get_class_name(class_node)
            full_path = self._get_full_class_path(source_path, class_name, library_name)

            # Get base classes as full paths
            bases = self._resolve_base_class_paths(class_node, file_imports, library_name)

            inheritance_map[full_path] = bases
            class_ast_nodes[full_path] = (class_node, file_imports, source_path)

    # Phase 2: Iterative Parameterized detection
    parameterized_classes = set()

    # Round 1: Find direct Parameterized subclasses
    for class_path, bases in inheritance_map.items():
        if any(self._is_parameterized_base(base) for base in bases):
            parameterized_classes.add(class_path)

    # Round 2+: Propagate iteratively
    changed = True
    while changed:
        changed = False
        for class_path, bases in inheritance_map.items():
            if class_path not in parameterized_classes:
                if any(base in parameterized_classes for base in bases):
                    parameterized_classes.add(class_path)
                    changed = True

    # Phase 3: Extract parameters for Parameterized classes
    count = 0
    for class_path in parameterized_classes:
        class_node, file_imports, source_path = class_ast_nodes[class_path]
        class_info = self._convert_ast_to_class_info(
            class_node, file_imports, class_path, source_path
        )
        if class_info:
            external_library_cache.set(library_name, class_path, class_info)
            count += 1

    return count

def _is_parameterized_base(self, base_path: str) -> bool:
    """Check if a base class path is param.Parameterized."""
    return base_path in (
        "param.Parameterized",
        "Parameterized",  # if imported as "from param import Parameterized"
    )

def _resolve_base_class_paths(self, class_node, file_imports, library_name):
    """Resolve base class names to full paths using imports."""
    bases = get_class_bases(class_node)  # ["ListPanel", "Mixin"]
    full_bases = []

    for base in bases:
        if "." in base:
            # Already qualified: "panel.layout.ListPanel"
            full_bases.append(base)
        elif base in file_imports:
            # Resolve via imports: ListPanel -> panel.layout.base.ListPanel
            full_bases.append(file_imports[base])
        else:
            # Assume same module
            full_bases.append(f"{library_name}.{base}")

    return full_bases
```

### Advantages:

✅ **No import side effects** - Pure static, no code execution
✅ **Faster** - No module loading overhead
✅ **Safer** - Can't break from import errors
✅ **Deterministic** - Same result every time
✅ **No dependency on library being importable**
✅ **Simple implementation** - Just iterative propagation through inheritance graph
✅ **Clear algorithm** - Easy to understand and debug
✅ **Complete coverage** - Handles transitive inheritance correctly

### Expected Outcome:

- Should find **250+ classes** (same as v1.0.0)
- Pure static analysis
- Handles transitive inheritance correctly

## Implementation Steps

The implementation follows the three-phase algorithm described above and integrates with the existing `StaticExternalAnalyzer.populate_library_cache()` method.

## Testing Strategy

1. Clear cache: `rm ~/.cache/param-lsp/*.json`
2. Run: Analyze a Panel class
3. Check: `panel-1_8_1-1_1_0.json` should have 200+ classes
4. Verify: Compare with v1.0.0 class list
5. Test: All existing tests still pass

## Expected Outcomes

- Coverage: 57 → 250+ classes (440% improvement)
- v1.0.0 parity: Should match or exceed original coverage
- Performance: Slightly slower initial population (one-time cost)
- Maintenance: Less complex than full static resolution

## Next Steps

1. Implement Phase 1: Build complete inheritance map
2. Implement Phase 2: Iterative Parameterized detection
3. Implement Phase 3: Extract parameters for marked classes
4. Replace current `populate_library_cache()` implementation
5. Test with panel library - verify 250+ classes found
6. Run all tests to ensure no regressions
7. Benchmark performance impact
