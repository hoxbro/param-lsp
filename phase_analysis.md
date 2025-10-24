# Phase Analysis and Optimization Plan

## Current Phase Structure

```
Phase -1: Parse all files (tree-sitter parsing)
  ├─ Read source_code from file
  ├─ Parse with tree-sitter
  └─ Store in parsed_files dict

[Build dependency graph - unlabeled]
  └─ Use parsed_files to extract imports

[Topological sort - unlabeled]

Phase 0: Extract classes and re-exports
  ├─ Re-read source_code from file (DUPLICATE!)
  ├─ Split into source_lines
  ├─ Extract imports
  ├─ Extract class names
  └─ Build inheritance_map

Phase 1: Iterative Parameterized detection
  ├─ Round 0: Find Parameterized root
  ├─ Round 1: Find direct subclasses
  └─ Round 2+: Propagate iteratively

[Resolve relative imports - unlabeled]

[Register wildcard aliases - unlabeled]

Phase 2: Extract parameters
  └─ For each class, extract parameter info
```

## Issues with Current Structure

### 1. **Inconsistent Naming**

- Phase -1, Phase 0, Phase 1, Phase 2 (confusing)
- Major steps unlabeled (dependency graph, sort, resolve)

### 2. **Duplicate File I/O** (PERFORMANCE)

- Phase -1 reads: `source_code = source_path.read_text()`
- Phase 0 re-reads: `source_code = source_path.read_text()`
- Could cache source_code in Phase -1

### 3. **Mixed Concerns in Phase 0**

- Extracts imports (already done for dependency graph)
- Extracts classes
- Processes re-exports
- All interleaved in one loop

### 4. **Unclear Phase Boundaries**

- When does "parsing" end and "analysis" begin?
- Hard to understand data flow

## Proposed New Phase Structure

```
Phase 1: File Discovery & Parsing
  ├─ Discover source files
  ├─ Parse with tree-sitter
  └─ Cache: parsed_files[path] = (tree, source_code, source_lines)
     [Single I/O read per file]

Phase 2: Import & Dependency Analysis
  ├─ Extract imports from cached trees
  ├─ Build file dependency graph
  └─ Topological sort files

Phase 3: Class Discovery & Mapping
  ├─ Extract all class definitions
  ├─ Build full class paths
  ├─ Build inheritance map
  └─ Process re-exports

Phase 4: Parameterized Identification
  ├─ Find Parameterized roots
  ├─ Propagate through inheritance
  ├─ Resolve relative imports
  └─ Topological sort classes

Phase 5: Parameter Extraction
  ├─ Extract parameters for each class
  ├─ Register aliases
  └─ Write to cache
```

## Optimization Opportunities

### A. Cache source_code in Phase 1 ✅ HIGH PRIORITY

**Impact**: Eliminate 187 file reads
**Change**: Store `(tree, source_code, source_lines)` in Phase 1
**Savings**: ~0.1-0.2s (187 reads × ~1ms each)

### B. Rename phases for clarity ✅ MEDIUM PRIORITY

**Impact**: Improve code maintainability
**Change**: Use consistent Phase 1-5 naming
**Benefit**: Easier to understand and debug

### C. Extract Phase 2 imports once ⚠️ LOW PRIORITY

**Note**: Imports are extracted twice (for dep graph + class analysis)
**Challenge**: Different data structures needed
**Recommendation**: Leave as-is for now (complexity not worth small gain)

### D. Combine Phase 4 steps ⚠️ LOW PRIORITY

**Note**: Multiple sub-steps in Parameterized detection
**Current**: Works well, clear logic
**Recommendation**: Leave as-is

## Implementation Priority

1. **Cache source_code in Phase 1** (High impact, easy)
2. **Rename phases 1-5** (Low cost, high clarity)
3. **Monitor other optimizations** (Revisit if needed)

## Expected Results

- **Performance**: +0.1-0.2s improvement (eliminate 187 file reads)
- **Clarity**: Much clearer phase boundaries
- **Maintainability**: Easier to understand data flow
