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

### =� In Progress / Remaining

#### Test Files Needing Updates

Many test files still use parso nodes in their setup:

- `test_import_resolver.py` - Import resolver tests (12 failures)
- `test_inheritance_resolver.py` - Inheritance tests (10 failures)
- `test_validation.py` - Validation helper tests (12 failures)
- `test_static_external_analyzer.py` - External analyzer tests (6 failures)
- `test_container_validation.py` - Container validation (3 failures)
- Integration tests (50+ failures)

#### Validation.py Helpers

Some helper methods still need updates:

- `_infer_value_type()` - Type inference from AST nodes
- `_is_boolean_literal()` - Boolean literal detection
- `_has_attribute_target()` - Attribute target checking
- `_create_type_error()` - Error creation with positions

#### Files Not Yet Migrated

- `parso_utils.py` - Can be deprecated/removed after full migration
- Any remaining analyzer components using parso

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

## Next Steps

### Phase 2: Test Migration

1. Update test fixtures to use tree-sitter nodes
2. Create test helpers for common node creation patterns
3. Fix validation.py helper methods
4. Update import resolver tests

### Phase 3: Cleanup

1. Remove or deprecate `parso_utils.py`
2. Remove parso dependency from pyproject.toml
3. Update documentation
4. Final linting and type checking

### Phase 4: Optimization

1. Implement incremental parsing where beneficial
2. Add caching for parsed trees
3. Performance benchmarking
4. Memory usage optimization

## Dependencies

### Added

```toml
dependencies = [
    "tree-sitter>=0.25.0",
    "tree-sitter-python>=0.25.0",
]
```

### To Remove (Phase 3)

```toml
dependencies = [
    "parso",  # Can be removed after full migration
]
```

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

### Parsing Code

```python
# Parse Python source
tree = ts_parser.parse(source_code)

# Walk the tree
for node in ts_utils.walk_tree(tree.root_node):
    if node.type == "class_definition":
        class_name = ts_utils.get_class_name(node)
        # Process class...
```

### Common Patterns

#### Finding Classes

```python
class_nodes = [
    node for node in ts_utils.walk_tree(tree.root_node)
    if node.type == "class_definition"
]
```

#### Getting Class Body

```python
block_node = class_node.child_by_field_name("body")
if block_node:
    # Process class body
    for child in ts_utils.get_children(block_node):
        # Process statements
```

#### Checking Assignments

```python
if node.type == "assignment" or (
    node.type == "expression_statement"
    and any(child.type == "assignment" for child in ts_utils.get_children(node))
):
    # This is an assignment
```

## Migration Checklist

- [x] Create ts_parser.py
- [x] Create ts_utils.py with all utility functions
- [x] Migrate validation.py core functionality
- [x] Migrate static_external_analyzer.py
- [x] Create test_ts_utils.py
- [x] Fix bounds validation tests
- [x] Update test_ast_navigator.py
- [x] Update test_parameter_extractor.py
- [ ] Update test_import_resolver.py
- [ ] Update test_inheritance_resolver.py
- [ ] Update test_validation.py
- [ ] Update test_static_external_analyzer.py
- [ ] Update integration tests
- [ ] Fix validation.py helper methods
- [ ] Remove parso_utils.py
- [ ] Remove parso dependency
- [ ] Update documentation
- [ ] Performance benchmarking

## Lessons Learned

1. **Field names are your friend** - Tree-sitter's `child_by_field_name()` is much cleaner than manual child iteration
2. **Node types differ significantly** - Can't do 1:1 string replacement, need to understand structure
3. **Error recovery is built-in** - No need for try/catch around parsing
4. **Helper functions essential** - Create utilities early to avoid repetition
5. **Test incrementally** - Migrate and test one file at a time
6. **Type annotations help** - Using `Node` instead of `NodeOrLeaf` catches errors early

## References

- [Tree-sitter Python Grammar](https://github.com/tree-sitter/tree-sitter-python)
- [Tree-sitter API Docs](https://tree-sitter.github.io/tree-sitter/)
- [Parso Documentation](https://parso.readthedocs.io/)
