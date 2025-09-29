# Param LSP Analyzer - Modular Architecture

This directory contains the modular components that power the Param Language Server's analysis capabilities. The architecture has been designed for maintainability, testability, and performance.

## Architecture Overview

The analyzer follows a modular design pattern where each component has a specific responsibility and can be tested independently. The main `analyzer.py` orchestrates these components to provide comprehensive analysis of Parameterized classes.

```
analyzer.py (orchestrator)
├── parso_utils.py         # AST navigation utilities
├── parameter_extractor.py # Parameter definition extraction
├── validation.py          # Type checking and validation
├── external_class_inspector.py # Runtime introspection
├── inheritance_resolver.py # Inheritance resolution
└── import_resolver.py     # Cross-file import resolution
```

## Component Descriptions

### parso_utils.py
**Purpose**: Low-level AST navigation and parsing utilities
**Key Functions**:
- `walk_tree()` - Recursive AST traversal
- `get_class_name()`, `get_class_bases()` - Class structure extraction
- `is_assignment_stmt()`, `is_function_call()` - Node type checking
- `find_all_parameter_assignments()` - Parameter discovery

**When to Use**: For low-level AST operations and tree traversal

### parameter_extractor.py
**Purpose**: Extract parameter definitions from AST nodes
**Key Functions**:
- `extract_parameter_info_from_assignment()` - Parse parameter assignments
- `resolve_parameter_class()` - Identify parameter types
- `get_keyword_arguments()` - Extract function call arguments
- `extract_numeric_value()`, `extract_boolean_value()` - Value extraction

**When to Use**: When you need to extract parameter metadata from code

### validation.py
**Purpose**: Comprehensive parameter validation
**Key Classes**:
- `ParameterValidator` - Main validation orchestrator

**Validation Types**:
- Type checking (ensuring values match parameter types)
- Bounds validation (numeric ranges)
- Constraint checking (parameter-specific rules)
- Runtime assignment validation (`obj.param = value`)
- Constructor validation (`MyClass(param=value)`)

**When to Use**: For real-time error checking and diagnostics

### external_class_inspector.py
**Purpose**: Runtime introspection of external library classes
**Key Classes**:
- `ExternalClassInspector` - Main introspection engine

**Capabilities**:
- Discovers Parameterized classes in external libraries
- Extracts parameter definitions via runtime introspection
- Caches results for performance
- Handles Panel, HoloViews, Bokeh, and other libraries

**When to Use**: When analyzing classes from external libraries

### inheritance_resolver.py
**Purpose**: Resolve parameter inheritance hierarchies
**Key Classes**:
- `InheritanceResolver` - Inheritance resolution engine

**Capabilities**:
- Identifies Parameterized base classes
- Collects inherited parameters from parents
- Handles multi-level inheritance
- Manages parameter overriding

**When to Use**: When dealing with class inheritance

### import_resolver.py
**Purpose**: Cross-file import and module resolution
**Key Classes**:
- `ImportResolver` - Import resolution engine

**Capabilities**:
- Parses import statements
- Resolves module paths
- Handles workspace-relative imports
- Caches analyzed modules
- Supports cross-file inheritance

**When to Use**: For multi-file analysis and import resolution

## Design Principles

### Separation of Concerns
Each module has a single, well-defined responsibility:
- **parso_utils**: Low-level AST operations
- **parameter_extractor**: Parameter parsing
- **validation**: Error checking
- **external_class_inspector**: External library support
- **inheritance_resolver**: Inheritance logic
- **import_resolver**: Import handling

### Dependency Management
Components are designed with minimal interdependencies:
- **parso_utils** has no dependencies (pure utility functions)
- **parameter_extractor** depends only on parso_utils
- **validation** uses parameter_extractor and parso_utils
- Higher-level components orchestrate lower-level ones

### Testability
Each component can be unit tested independently:
- Mock dependencies for isolation
- Clear input/output contracts
- Comprehensive test coverage for each module

### Performance
Caching and optimization strategies:
- **external_class_inspector** caches introspection results
- **import_resolver** caches analyzed modules
- **validation** reuses analyzer state

## Usage Examples

### Basic Parameter Extraction
```python
from _analyzer.parameter_extractor import extract_parameter_info_from_assignment
from _analyzer.parso_utils import walk_tree

# Parse and extract parameter info
tree = parso.parse("name = param.String(default='test')")
for node in walk_tree(tree):
    if is_assignment_stmt(node):
        param_info = extract_parameter_info_from_assignment(node, "name", {}, "")
```

### Validation
```python
from _analyzer.validation import ParameterValidator

validator = ParameterValidator(
    param_type_map=PARAM_TYPE_MAP,
    param_classes={},
    external_param_classes={},
    imports={},
    is_parameter_assignment_func=my_func
)

errors = validator.check_parameter_types(tree, source_lines)
```

### External Class Introspection
```python
from _analyzer.external_class_inspector import ExternalClassInspector

inspector = ExternalClassInspector()
class_info = inspector.analyze_external_class_ast("panel.widgets.IntSlider")
```

## Testing Strategy

Each module has comprehensive unit tests in `tests/test_analyzer/`:
- `test_parso_utils.py` - AST utility tests
- `test_parameter_extractor.py` - Parameter extraction tests
- `test_validation.py` - Validation logic tests
- `test_external_class_inspector.py` - External introspection tests
- `test_inheritance_resolver.py` - Inheritance tests
- `test_import_resolver.py` - Import resolution tests

Integration tests validate component interactions in `tests/test_integration/`.

## Performance Considerations

### Caching Strategy
- **External classes**: Cached in `external_library_cache` with TTL
- **Analyzed modules**: Cached in `module_cache` and `file_cache`
- **Parameter metadata**: Cached in component instances

### Optimization Opportunities
- Lazy loading of external libraries
- Incremental analysis for file changes
- Parallel processing for independent modules
- Memory usage optimization for large codebases

## Migration Guide

When modifying the analyzer:

1. **Adding new functionality**: Create focused functions in appropriate modules
2. **Modifying existing logic**: Update the relevant modular component
3. **Cross-cutting concerns**: Consider if a new module is needed
4. **Performance issues**: Check caching and add profiling

## Future Enhancements

Potential improvements to the modular architecture:
- Plugin system for custom parameter types
- Async analysis for better IDE responsiveness
- Enhanced caching with persistence
- Better error recovery and partial analysis
- Support for additional external libraries

---

*This modular architecture was established during Phase 2 of the analyzer refactoring (January 2025) to improve maintainability, testability, and performance while preserving all existing functionality.*