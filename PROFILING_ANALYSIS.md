# Profiling Analysis: improve_check Branch

## Test Setup

- Profiled `populate_library_cache("panel")` with cleared cache
- Populated 275 classes from panel library
- Total time: **4.44 seconds**

## Top Bottlenecks

### 1. Subprocess Calls (2.9s / 65% of total time)

```
191 calls to python_environment.py:55(user_site) - 2.908s
192 calls to python_environment.py:62(_query_python_exe) - 2.922s
193 subprocess.check_output calls - 2.958s
```

**Root Cause**: The `user_site` property calls `_query_python_exe()` which spawns a subprocess. Even though caching is implemented (`if self._user_site is None`), there's a bug when `user_site` doesn't exist - it gets set to `None` and is re-queried on every access.

**Impact**: 191 subprocess calls @ ~15ms each = ~2.9s wasted

**Fix**: Use a sentinel value to distinguish "not queried" from "queried but doesn't exist"

### 2. \_get_full_class_path Overhead (called 187 times)

```
187 calls @ 0.016s each = 2.905s total
```

**Root Cause**: Each call accesses `python_env.user_site` which triggers subprocess (see #1)

**Additional Issue**: The function recreates `search_dirs` list every time:

```python
search_dirs = list(self.python_env.site_packages)
if self.python_env.user_site:
    search_dirs.append(self.python_env.user_site)
```

**Fix**:

- Fix #1 above
- Pre-compute search_dirs once and cache it
- Use the cached `_get_full_class_path_cached` version more (only called 495 times vs 187 times for non-cached)

### 3. \_resolve_base_class_paths (called 495 times, 2.911s)

```
495 calls @ 0.006s each = 2.911s total
```

**Root Cause**: Calls `_get_full_class_path` which has the subprocess issue

**Fix**: Use cached version `_get_full_class_path_cached` which is already available

### 4. Tree-sitter Parsing (374 files, 0.37s)

```
374 parser.parse() calls = 0.372s (reasonable - ~1ms per file)
```

**Note**: This is acceptable and efficient

### 5. \_build_file_dependency_graph (0.307s)

```
Parses all 187 files again to build dependency graph
```

**Issue**: Files are parsed TWICE - once in Phase 0 and once here

**Fix**: Reuse the parsed trees from Phase 0 (already stored in `file_data`)

## Optimization Opportunities (Prioritized)

### High Priority (Easy Wins)

1. **Fix user_site caching bug** (~2.9s savings)
   - Use sentinel value for "not queried" state
   - Estimated savings: 2.5-2.9s (56-65%)

2. **Reuse dependency graph parsing** (~0.3s savings)
   - Pass parsed trees to `_build_file_dependency_graph`
   - Estimated savings: 0.3s (7%)

3. **Pre-compute search_dirs** (~0.1s savings)
   - Cache search_dirs list in **init** or as property
   - Estimated savings: 0.05-0.1s (1-2%)

### Medium Priority

4. **Optimize \_base_matches_parameterized_class**
   - Build index for O(1) lookups instead of O(n) string matching
   - Called frequently during iterative resolution

5. **Cache \_is_class_definition_in_file results**
   - Avoid re-parsing files for class definition checks

### Low Priority

6. **Reduce JSON encoding time** (0.2s for cache flush)
   - This is I/O bound and hard to optimize further

## Expected Total Speedup

- High priority fixes: **3.2-3.3s savings (72-74% faster)**
- With medium priority: **~3.5s savings (~79% faster)**
- Final time: **~0.9-1.2s** (down from 4.4s)

## Implementation Order

1. Fix `user_site` caching bug (biggest impact)
2. Reuse parsed trees in dependency graph building
3. Pre-compute and cache search_dirs
4. Optimize \_base_matches_parameterized_class
5. Cache class definition checks
