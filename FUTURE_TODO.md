# Future TODOs for convert_to_legacy_format Removal

## Overview

The `convert_to_legacy_format` function has been successfully removed from most of the test suite, but some complex integration tests still rely on it for backward compatibility.

## Current Status

- ✅ **Completed**: Removed from 13+ test files and main source code
- ✅ **Completed**: Updated completion.py to use new analyzer format directly
- ⚠️ **Remaining**: 7 complex test files still use legacy format wrapper

## Future Work Items

### 1. Complete Legacy Format Removal

**Priority: Medium**
**Effort: High**

Update remaining complex test files to use the new analyzer format directly:

- `tests/test_integration/test_cross_file_inheritance.py` (8 occurrences)
- `tests/test_server/test_validation/test_constructor_complex_scenarios.py` (12 occurrences)
- `tests/test_integration/test_integration.py` (5 occurrences)
- `tests/test_integration/test_user_example.py` (5 occurrences)
- `tests/test_integration/test_panel_widget_inheritance.py` (3 occurrences)

**Benefits:**

- Fully consistent data format across all tests
- Remove legacy compatibility layer entirely
- Simplify models.py by removing convert_to_legacy_format function

**Approach:**

1. Update tests one file at a time
2. Replace legacy format expectations (e.g., `result["param_parameters"]["ClassName"]`) with new format (`result["param_classes"]["ClassName"].parameters.keys()`)
3. Test thoroughly after each file conversion
4. Commit after each successful file update

### 2. Documentation Updates

**Priority: Low**
**Effort: Low**

- Update any remaining documentation that references the old format
- Add examples of the new analyzer format usage
- Document the new format structure clearly

### 3. Performance Optimization

**Priority: Low**
**Effort: Medium**

With legacy format removed, consider optimizations:

- Remove any remaining legacy format considerations from analyzer
- Optimize data structures now that only one format is used
- Review completion.py helper method for potential improvements

## Implementation Notes

### Pattern for Converting Tests

```python
# Old format:
result = convert_to_legacy_format(analyzer.analyze_file(code))
params = result["param_parameters"]["ClassName"]
types = result["param_parameter_types"]["ClassName"]["param_name"]

# New format:
result = analyzer.analyze_file(code)
class_info = result["param_classes"]["ClassName"]
params = list(class_info.parameters.keys())
types = class_info.parameters["param_name"].param_type
```

### Testing Strategy

- Run full test suite after each file conversion
- Focus on cross-file inheritance tests (most complex)
- Ensure external library integration still works

## Success Metrics

- All tests pass without convert_to_legacy_format function
- No performance regression
- Code is more maintainable and consistent
