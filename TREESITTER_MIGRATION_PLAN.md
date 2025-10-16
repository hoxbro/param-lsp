# Tree-sitter Migration Plan

## Overview

Migrating param-lsp from parso AST parser to tree-sitter for better performance, error recovery, and incremental parsing support.

## Migration Status

###  Completed (Phase 1)

#### Core Infrastructure

- [x] **ts_parser.py** - Tree-sitter Python parser singleton
  - Singleton pattern for parser reuse
  - Error recovery enabled by default
  - Returns `Tree` objects with `.root_node` access

- [x] **ts_utils.py** - Tree-sitter utility functions (318 lines)
  - `get_value()` - Extract text from nodes
  - `get_children()` - Get child nodes
  - `walk_tree()` - Recursive traversal
  - `get_class_name()` - Extract class names
  - `get_class_bases()` - Extract base classes
  - `is_assignment_stmt()` - Check for assignments
  - `is_function_call()` - Check for function calls
  - `find_all_parameter_assignments()` - Find param assignments
  - And many more helpers

#### Analyzer Files

- [x] **validation.py** - Parameter validation (900+ lines)
  - Updated `_check_parameter_constraints()` for tree-sitter
  - Fixed bounds parsing to use "tuple" instead of "atom"
  - Updated all node type checks
  - Bounds validation tests passing 

- [x] **static_external_analyzer.py** - External class analysis (1782 lines)
  - Replaced all `NodeOrLeaf` � `Node` type annotations
  - Changed `parso.parse()` � `ts_parser.parse()`
  - Updated all node type strings
  - Simplified using ts_utils helpers
  - Fixed `_process_import_from_for_reexport()` for tree-sitter structure
  - **Impact**: Removed 172 lines, added 120 lines

#### Tests

- [x] **test_ts_utils.py** - Comprehensive utility tests (17 tests)
  - Basic utils (get_value, get_children, walk_tree)
  - Class utils (get_class_name, get_class_bases, find_class_suites)
  - Assignment utils (is_assignment_stmt, get_assignment_target_name)
  - Function call utils (is_function_call, find_function_call_trailers)
  - Parameter assignment utils
  - Edge cases (empty code, malformed classes, None values)

- [x] **test_ast_navigator.py** - Migrated (23 tests passing)
- [x] **test_parameter_extractor.py** - Migrated (35 tests passing)
- [x] **test_bounds_validation.py** - Fixed (9 tests passing)

### Completed (Phase 2 - Test Migration)

#### Test Files Migrated

All major test files have been migrated to tree-sitter:

- `test_validation.py` - ✅ 31/31 tests passing
- `test_import_resolver.py` - ✅ 21/21 tests passing
- `test_inheritance_resolver.py` - ✅ 12/12 tests passing
- `test_static_external_analyzer.py` - ✅ 17/17 tests passing
- `test_ast_navigator.py` - ✅ 23/23 tests passing
- `test_parameter_extractor.py` - ✅ 35/35 tests passing
- `test_bounds_validation.py` - ✅ 9/9 tests passing
- `test_ts_utils.py` - ✅ 17/17 tests passing

#### Bug Fixes

- ✅ Fixed `import_resolver.py` to handle `dotted_name` nodes in from imports
- ✅ Fixed validation.py helper methods (\_infer_value_type, \_is_boolean_literal, etc.)

### ✅ Completed (Phase 3 - Validation Fixes)

All test failures have been resolved! The migration achieved 99.6% test success rate.

#### Fixed Test Files

- ✅ `test_container_validation.py` - 6/6 passing (all edge cases fixed)
- ✅ `test_inheritance.py` - 7/7 passing (all edge cases fixed)
- ✅ `test_server/test_validation/*` - 51/51 passing (all integration tests fixed)

#### Dependency Status

- ✅ Parso dependency completely removed from pyproject.toml
- ✅ Tree-sitter dependencies in place and working
- ✅ All parso code removed (parso_utils.py and test_parso_utils.py deleted in Phase 5)

### ✅ Issue Resolved: ERROR Node Handling

Previously there were 2 edge case failures with incomplete decorator syntax. These have been **fixed** by updating `find_class_suites()` to also process ERROR nodes.

#### Solution (ts_utils.py:212-237)

When tree-sitter encounters syntax errors (like missing closing parentheses in decorators), it places parameter assignments inside ERROR nodes during error recovery. The fix ensures parameter extraction works by:

1. Yielding the body node when it exists (normal case)
2. Also yielding ERROR nodes to capture parameters during error recovery
3. Avoiding duplicate processing by tracking what's been yielded

This enables robust parameter extraction even with syntax errors, which is crucial for providing code completion while users are actively typing.

## Node Type Mapping

### Tree-sitter � Parso Equivalents

| Parso Type      | Tree-sitter Type              | Notes                   |
| --------------- | ----------------------------- | ----------------------- |
| `classdef`      | `class_definition`            | Class definitions       |
| `import_name`   | `import_statement`            | Import statements       |
| `import_from`   | `import_from_statement`       | From imports            |
| `suite`         | `block`                       | Code blocks             |
| `simple_stmt`   | `expression_statement`        | Simple statements       |
| `expr_stmt`     | `assignment`                  | Assignment statements   |
| `funcdef`       | `function_definition`         | Function definitions    |
| `async_funcdef` | `async_function_definition`   | Async functions         |
| `name`          | `identifier`                  | Variable names          |
| `power`         | `call` or `attribute`         | Method calls/attributes |
| `atom_expr`     | `call` or `attribute`         | Expression atoms        |
| `atom`          | `tuple`, `list`, `dict`, etc. | Literal containers      |
| `testlist_comp` | Direct children               | Tuple/list elements     |
| `trailer`       | `argument_list`               | Function arguments      |

### Key Structural Differences

1. **Tree Access**
   - Parso: `tree` is the root node
   - Tree-sitter: `tree.root_node` is the root node

2. **Node Children**
   - Parso: `node.children`
   - Tree-sitter: `node.children` (same, but use `ts_utils.get_children()`)

3. **Node Text**
   - Parso: `node.get_code()`
   - Tree-sitter: `node.text.decode("utf-8")`

4. **Field Access**
   - Parso: Manual child iteration
   - Tree-sitter: `node.child_by_field_name("name")`, `node.child_by_field_name("body")`

5. **Class Bodies**
   - Parso: Look for `suite` node type
   - Tree-sitter: Use `class_node.child_by_field_name("body")` � returns `block`

6. **Import Structure**
   - Parso: Complex child iteration
   - Tree-sitter: Use `child_by_field_name("module_name")`, `child_by_field_name("name")`

## Test Results

### Current Status (After Phase 1)

- **360 tests passing** 
- **90 tests failing** (expected - test setup issues)

### Failure Categories

1. **Test setup** - Tests creating parso nodes instead of tree-sitter nodes
2. **Validation helpers** - Methods using parso-specific attributes
3. **Import handling** - Tests passing wrong node types

## Performance Improvements

Tree-sitter provides:

- **Incremental parsing** - Only reparse changed sections
- **Error recovery** - Continue parsing after syntax errors
- **Better performance** - Native C implementation
- **Memory efficiency** - More efficient AST representation

## Migration Complete! 🎉

### ✅ Phase 1: Core Infrastructure (Complete)

- Tree-sitter parser and utilities implemented
- Core analyzer files migrated
- Basic tests passing

### ✅ Phase 2: Test Migration (Complete)

- All test files migrated to tree-sitter
- Bug fixes for import resolution and validation
- 398/450 tests passing

### ✅ Phase 3: Validation Fixes (Complete)

- Fixed container validation for lists and tuples
- Fixed runtime assignment validation
- Fixed constructor call detection
- **448/450 tests passing (99.6% success rate)**

### ✅ Phase 4: Query-based Optimizations (Complete)

Achieved **~2x speedup** through query-based AST pattern matching!

1. ✅ **Query-based AST Pattern Matching** - 2x average speedup
   - Pre-compiled tree-sitter queries with caching
   - Classes: 1.91x faster
   - Imports: 2.10x faster
   - Function calls: 1.98x faster
   - Custom query support via `ts_queries.py`

2. ✅ **Performance Benchmarking** - Query optimization benchmark
   - Query vs manual tree walking comparisons
   - Consistent 2x speedup across different AST patterns
   - Total time: 15.75ms manual → 7.90ms queries

#### Performance Improvements Summary

| Operation    | Manual Walking | Query-based | Speedup   |
| ------------ | -------------- | ----------- | --------- |
| Find classes | 5.25ms         | 2.75ms      | 1.91x     |
| Find imports | 5.42ms         | 2.58ms      | 2.10x     |
| Find calls   | 5.08ms         | 2.56ms      | 1.98x     |
| **Total**    | **15.75ms**    | **7.90ms**  | **2.00x** |

**Note on LSP optimization:** Parse tree caching was removed as it's not beneficial for LSP where files change constantly. The real LSP optimization would be incremental parsing (reusing old trees), which requires integration work with the LSP `textDocument/didChange` notifications.

All 450 tests passing - optimizations maintain full compatibility ✅

### ✅ Completed (Phase 5 - Code Organization & Cleanup)

Final cleanup phase to organize tree-sitter code into a proper submodule and remove all parso remnants.

#### Code Reorganization

1. ✅ **Created `_treesitter/` submodule** - Clean separation of tree-sitter utilities
   - Moved `ts_parser.py` → `_treesitter/parser.py`
   - Moved `ts_queries.py` → `_treesitter/queries.py`
   - Moved `ts_utils.py` → `_treesitter/utils.py`
   - Created comprehensive `__init__.py` with proper exports
   - Updated all imports to use `param_lsp._treesitter`

2. ✅ **Removed all parso code** - Complete cleanup
   - Deleted `parso_utils.py` (391 lines removed)
   - Deleted `test_parso_utils.py` (359 lines removed)
   - Removed `ParsoNode` type alias from `_types.py`
   - Cleaned up legacy parso comments in source files

3. ✅ **Updated all imports** - Consistent module structure
   - Source files: `from param_lsp._treesitter import ...`
   - Test files: `from param_lsp._treesitter import parser, queries, ...`
   - Analyzer: `from param_lsp import _treesitter`

#### Impact Summary

- **Lines removed**: 949 (parso code, redundant imports, legacy comments)
- **Lines added**: 247 (new `__init__.py`, updated imports)
- **Net improvement**: -702 lines of cleaner, more organized code
- **Tests passing**: 430/430 (100% compatibility maintained)

#### File Structure (After Phase 5)

```
src/param_lsp/
├── _analyzer/
│   ├── ast_navigator.py          # Uses _treesitter
│   ├── import_resolver.py        # Uses _treesitter
│   ├── inheritance_resolver.py   # Uses _treesitter
│   ├── parameter_extractor.py    # Uses _treesitter
│   ├── static_external_analyzer.py  # Uses _treesitter
│   └── validation.py             # Uses _treesitter
├── _treesitter/                  # NEW: Tree-sitter submodule
│   ├── __init__.py              # Public API exports
│   ├── parser.py                # Singleton parser (was ts_parser.py)
│   ├── queries.py               # Query-based utilities (was ts_queries.py)
│   └── utils.py                 # Helper functions (was ts_utils.py)
└── analyzer.py                   # Main analyzer, uses _treesitter
```

## Dependencies

### ✅ Migration Complete

**Added:**

```toml
dependencies = [
    "tree-sitter>=0.25.0",
    "tree-sitter-python>=0.25.0",
]
```

**Removed:**

```toml
# parso - Successfully removed, no longer needed
```

Current dependencies in `pyproject.toml`:

- `pygls` - Language Server Protocol implementation
- `lsprotocol` - LSP types and protocols
- `param` - The library we're providing LSP support for
- `platformdirs` - Cross-platform directory utilities
- `tree-sitter>=0.25.0` - Parser generator tool
- `tree-sitter-python>=0.25.0` - Python grammar for tree-sitter

## Implementation Notes

### Singleton Parser Pattern

```python
_parser: Parser | None = None

def _get_parser() -> Parser:
    """Get or create the tree-sitter Python parser singleton."""
    global _parser
    if _parser is None:
        _parser = Parser(Language(language()))
    return _parser
```

### Parsing Code (Updated for Phase 5)

```python
from param_lsp._treesitter import parser, queries, walk_tree, get_class_name

# Parse Python source
tree = parser.parse(source_code)

# Walk the tree
for node in walk_tree(tree.root_node):
    if node.type == "class_definition":
        class_name = get_class_name(node)
        # Process class...
```

### Common Patterns

#### Finding Classes (Query-based - Recommended)

```python
# Using query-based approach (2x faster) - Updated for Phase 5
from param_lsp._treesitter import queries

results = queries.find_classes(tree)
for class_node, captures in results:
    class_name = captures["class_name"]  # identifier node
    class_body = captures["class_body"]  # block node
```

#### Finding Classes (Manual walking - Legacy)

```python
# Manual tree walking (slower, but still supported) - Updated for Phase 5
from param_lsp._treesitter import walk_tree

class_nodes = [
    node for node in walk_tree(tree.root_node)
    if node.type == "class_definition"
]
```

#### Using Query-based Utilities (Updated for Phase 5)

```python
from param_lsp._treesitter import queries

# Find imports (2.5x faster)
imports = queries.find_imports(tree)

# Find function calls (2.2x faster)
calls = queries.find_calls(tree)

# Find assignments
assignments = queries.find_assignments(tree)

# Find decorators
decorators = queries.find_decorators(tree)

# Custom queries
custom_results = queries.query_custom(tree, "(class_definition) @class")
```

#### Getting Class Body (Updated for Phase 5)

```python
from param_lsp._treesitter import get_children

block_node = class_node.child_by_field_name("body")
if block_node:
    # Process class body
    for child in get_children(block_node):
        # Process statements
```

#### Checking Assignments (Updated for Phase 5)

```python
from param_lsp._treesitter import get_children

if node.type == "assignment" or (
    node.type == "expression_statement"
    and any(child.type == "assignment" for child in get_children(node))
):
    # This is an assignment
```

## Migration Checklist

### Phase 1: Core Infrastructure

- [x] Create ts_parser.py
- [x] Create ts_utils.py with all utility functions
- [x] Migrate validation.py core functionality
- [x] Migrate static_external_analyzer.py
- [x] Create test_ts_utils.py
- [x] Fix bounds validation tests

### Phase 2: Test Migration

- [x] Update test_ast_navigator.py
- [x] Update test_parameter_extractor.py
- [x] Update test_import_resolver.py (21 tests passing)
- [x] Update test_inheritance_resolver.py (12 tests passing)
- [x] Update test_validation.py (31 tests passing)
- [x] Update test_static_external_analyzer.py (17 tests passing)
- [x] Fix validation.py helper methods (\_infer_value_type, \_is_boolean_literal, etc.)
- [x] Fix import_resolver.py to handle dotted_name nodes in from imports

### Phase 3: Validation Fixes

- [x] Update integration tests (all 51 test_server/test_validation/\* passing)
- [x] Fix test_analyzer failures (container_validation: 6/6, inheritance: 7/7)
- [x] Fix container validation (\_extract_list_items, \_extract_tuple_items)
- [x] Fix runtime assignment validation (\_check_runtime_parameter_assignment)
- [x] Fix constructor call detection (\_get_instance_class)

### Phase 4: Query Optimization

- [x] Implement query-based AST utilities
- [x] Create query optimization benchmarking
- [x] Achieve 2x speedup with queries
- [x] Document 2 edge case limitations (incomplete syntax completion)
- [x] Fix ERROR node handling for syntax error recovery

### Phase 5: Code Organization & Cleanup

- [x] Create `_treesitter/` submodule
- [x] Move ts_parser.py → \_treesitter/parser.py
- [x] Move ts_queries.py → \_treesitter/queries.py
- [x] Move ts_utils.py → \_treesitter/utils.py
- [x] Delete parso_utils.py
- [x] Delete test_parso_utils.py
- [x] Remove ParsoNode type alias
- [x] Update all imports to use param_lsp.\_treesitter
- [x] Clean up legacy parso comments
- [x] Confirm parso dependency removed
- [x] Update migration plan documentation

## Lessons Learned

1. **Field names are your friend** - Tree-sitter's `child_by_field_name()` is much cleaner than manual child iteration
2. **Node types differ significantly** - Can't do 1:1 string replacement, need to understand structure
3. **Error recovery is built-in** - No need for try/catch around parsing
4. **Helper functions essential** - Create utilities early to avoid repetition
5. **Test incrementally** - Migrate and test one file at a time
6. **Type annotations help** - Using `Node` instead of `NodeOrLeaf` catches errors early
7. **Queries beat manual walking** - Tree-sitter queries are ~2x faster than manual traversal
8. **Measure before optimizing** - Comprehensive benchmarks validate optimization choices
9. **LSP caching is different** - Parse tree caching doesn't help when files change constantly
10. **Incremental > caching** - For LSP, incremental parsing (reusing old trees) is the real win
11. **Code organization matters** - Creating the `_treesitter/` submodule improved clarity and maintainability
12. **Clean up as you go** - Removing legacy code (parso) prevents confusion and reduces maintenance burden

## References

- [Tree-sitter Python Grammar](https://github.com/tree-sitter/tree-sitter-python)
- [Tree-sitter API Docs](https://tree-sitter.github.io/tree-sitter/)
- [Parso Documentation](https://parso.readthedocs.io/)

## Detailed Test Results (Final - 100% Complete!)

### Overall Statistics

- **430 tests passing** (100% success rate) ✅✅✅
- **0 tests failing**
- **Net improvement from Phase 1: +90 tests fixed**
- **Net improvement from Phase 2: +50 tests fixed**
- **Net improvement from Phase 3: +2 tests fixed (ERROR node handling)**
- **Phase 5: 20 tests removed** (parso_utils tests no longer needed after cleanup)

### test_analyzer: 231/231 passing (100% ✅)

#### Fully Passing (15 files)

- test_validation.py: 31/31 ✅
- test_import_resolver.py: 21/21 ✅
- test_inheritance_resolver.py: 12/12 ✅
- test_static_external_analyzer.py: 17/17 ✅
- test_ast_navigator.py: 23/23 ✅
- test_parameter_extractor.py: 35/35 ✅
- test_bounds_validation.py: 9/9 ✅
- test_ts_utils.py: 17/17 ✅
- test_python_environment.py: 20/20 ✅
- test_type_checking.py: 9/9 ✅
- test_doc_extraction.py: 10/10 ✅
- test_deprecation_warnings.py: 4/4 ✅
- test_runtime_assignment.py: 10/10 ✅
- **test_container_validation.py: 6/6** ✅ _(fixed!)_
- **test_inheritance.py: 7/7** ✅ _(fixed!)_

#### Removed in Phase 5

- ~~test_parso_utils.py~~ - Deleted (parso code removed, tests no longer needed)

### test_integration: 7/7 passing (100% ✅)

### test_cache: 14/14 passing (100% ✅)

### test_server: 178/178 passing (100% ✅)

All test_server tests passing, including:

- test_param_depends_completion.py: 8/8 ✅ (fixed with ERROR node handling)
- All validation tests: 51/51 ✅
- All completion tests passing ✅
- All hover tests passing ✅

### Success Metrics

- **Core analyzer migration: 100% complete** ✅
- **All major test files migrated to tree-sitter** ✅
- **All constructor validation tests passing** ✅
- **All completion tests passing** ✅
- **Phase 2 objectives achieved** ✅
- **Phase 3 validation fixes complete** ✅
- **Phase 4 query optimization complete** ✅
- **Phase 5 code organization complete** ✅
- **100% test success rate (430/430)** ✅✅✅
- **MIGRATION COMPLETE!** 🎉

### Key Fixes in Phase 3

1. **Container Validation** (validation.py:1034-1054)
   - Fixed `_extract_list_items()` to use tree-sitter "list" node type
   - Fixed `_extract_tuple_items()` to use tree-sitter "tuple" node type
   - Updated to filter punctuation ("[", "]", ",", "(", ")") from children

2. **Constructor Call Detection** (validation.py:187-250)
   - Updated `_get_instance_class()` to handle tree-sitter "call" nodes
   - Added `_resolve_full_class_path_from_attribute()` for attribute nodes
   - Fixed detection of class names from constructor calls

3. **Runtime Assignment Validation** (validation.py:542-575)
   - Fixed `_check_runtime_parameter_assignment()` to detect call nodes in attribute objects
   - Updated to handle tree-sitter attribute structure with "object" and "attribute" fields
   - Properly extracts class name from patterns like `S().value = 123`

### Key Fix in Phase 4

1. **ERROR Node Handling** (ts_utils.py:212-237)
   - Updated `find_class_suites()` to process ERROR nodes in addition to body nodes
   - Enables parameter extraction even when syntax errors are present
   - Handles tree-sitter's error recovery where parameters end up in ERROR nodes
   - Critical for code completion while users are typing incomplete code
   - **Result:** Fixed last 2 failing tests, achieving 100% pass rate
