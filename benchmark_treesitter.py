#!/usr/bin/env python3
"""Benchmark script for tree-sitter optimizations.

Measures performance improvements from:
1. Parse tree caching
2. Query-based AST pattern matching vs manual tree walking
3. Memory usage optimization
"""

from __future__ import annotations

import time
import tracemalloc
from pathlib import Path

from src.param_lsp._analyzer import ts_parser, ts_queries, ts_utils


def load_test_files() -> list[tuple[str, str]]:
    """Load real Python files from the codebase for benchmarking.

    Returns:
        List of (filepath, content) tuples
    """
    test_files = []
    src_dir = Path("src/param_lsp")

    # Load various Python files with different sizes/complexity
    py_files = list(src_dir.rglob("*.py"))[:10]  # Sample 10 files

    for py_file in py_files:
        try:
            content = py_file.read_text()
            test_files.append((str(py_file), content))
        except Exception as e:
            print(f"Warning: Could not read {py_file}: {e}")

    return test_files


def benchmark_parsing_with_cache(test_files: list[tuple[str, str]]) -> dict:
    """Benchmark parsing performance with and without cache.

    Args:
        test_files: List of (filepath, content) tuples

    Returns:
        Dictionary with benchmark results
    """
    print("\n" + "=" * 70)
    print("BENCHMARK 1: Parse Tree Caching")
    print("=" * 70)

    # First, clear cache and benchmark without cache
    ts_parser.clear_cache()

    # Warm-up run
    for _, content in test_files:
        ts_parser.parse(content)

    # Cold cache (first parse)
    ts_parser.clear_cache()
    start_time = time.perf_counter()
    for _, content in test_files:
        ts_parser.parse(content)
    cold_time = time.perf_counter() - start_time

    # Warm cache (second parse - should use cache)
    start_time = time.perf_counter()
    for _, content in test_files:
        ts_parser.parse(content)
    warm_time = time.perf_counter() - start_time

    cache_stats = ts_parser.get_cache_stats()
    speedup = cold_time / warm_time if warm_time > 0 else 0

    print(f"\nParsed {len(test_files)} files:")
    print(f"  Cold cache (first parse):  {cold_time * 1000:.2f}ms")
    print(f"  Warm cache (cached parse): {warm_time * 1000:.2f}ms")
    print(f"  Speedup: {speedup:.2f}x faster with cache")
    print(f"  Cache stats: {cache_stats}")

    return {
        "cold_time": cold_time,
        "warm_time": warm_time,
        "speedup": speedup,
        "cache_stats": cache_stats,
    }


def benchmark_query_vs_walk(test_files: list[tuple[str, str]]) -> dict:
    """Benchmark query-based vs manual tree walking.

    Args:
        test_files: List of (filepath, content) tuples

    Returns:
        Dictionary with benchmark results
    """
    print("\n" + "=" * 70)
    print("BENCHMARK 2: Query-based vs Manual Tree Walking")
    print("=" * 70)

    # Parse all files once (with cache)
    trees = []
    for _, content in test_files:
        tree = ts_parser.parse(content)
        trees.append(tree)

    # Benchmark 1: Find all classes using manual walking
    start_time = time.perf_counter()
    manual_classes = [
        node
        for tree in trees
        for node in ts_utils.walk_tree(tree.root_node)
        if node.type == "class_definition"
    ]
    manual_time = time.perf_counter() - start_time

    # Benchmark 2: Find all classes using queries
    start_time = time.perf_counter()
    query_classes = []
    for tree in trees:
        results = ts_queries.find_classes(tree)
        query_classes.extend([node for node, _ in results])
    query_time = time.perf_counter() - start_time

    speedup = manual_time / query_time if query_time > 0 else 0

    print(f"\nFinding class definitions in {len(test_files)} files:")
    print(f"  Manual tree walk: {manual_time * 1000:.2f}ms ({len(manual_classes)} classes)")
    print(f"  Query-based:      {query_time * 1000:.2f}ms ({len(query_classes)} classes)")
    print(f"  Speedup: {speedup:.2f}x faster with queries")

    # Benchmark 3: Find all imports
    start_time = time.perf_counter()
    manual_imports = [
        node
        for tree in trees
        for node in ts_utils.walk_tree(tree.root_node)
        if node.type in ("import_statement", "import_from_statement")
    ]
    manual_import_time = time.perf_counter() - start_time

    start_time = time.perf_counter()
    query_imports = []
    for tree in trees:
        results = ts_queries.find_imports(tree)
        query_imports.extend([node for node, _ in results])
    query_import_time = time.perf_counter() - start_time

    import_speedup = manual_import_time / query_import_time if query_import_time > 0 else 0

    print(f"\nFinding import statements in {len(test_files)} files:")
    print(f"  Manual tree walk: {manual_import_time * 1000:.2f}ms ({len(manual_imports)} imports)")
    print(f"  Query-based:      {query_import_time * 1000:.2f}ms ({len(query_imports)} imports)")
    print(f"  Speedup: {import_speedup:.2f}x faster with queries")

    # Benchmark 4: Find all function calls
    start_time = time.perf_counter()
    manual_calls = [
        node
        for tree in trees
        for node in ts_utils.walk_tree(tree.root_node)
        if node.type == "call"
    ]
    manual_call_time = time.perf_counter() - start_time

    start_time = time.perf_counter()
    query_calls = []
    for tree in trees:
        results = ts_queries.find_calls(tree)
        query_calls.extend([node for node, _ in results])
    query_call_time = time.perf_counter() - start_time

    call_speedup = manual_call_time / query_call_time if query_call_time > 0 else 0

    print(f"\nFinding function calls in {len(test_files)} files:")
    print(f"  Manual tree walk: {manual_call_time * 1000:.2f}ms ({len(manual_calls)} calls)")
    print(f"  Query-based:      {query_call_time * 1000:.2f}ms ({len(query_calls)} calls)")
    print(f"  Speedup: {call_speedup:.2f}x faster with queries")

    avg_speedup = (speedup + import_speedup + call_speedup) / 3

    return {
        "class_speedup": speedup,
        "import_speedup": import_speedup,
        "call_speedup": call_speedup,
        "avg_speedup": avg_speedup,
        "manual_time": manual_time + manual_import_time + manual_call_time,
        "query_time": query_time + query_import_time + query_call_time,
    }


def benchmark_memory_usage(test_files: list[tuple[str, str]]) -> dict:
    """Benchmark memory usage of different approaches.

    Args:
        test_files: List of (filepath, content) tuples

    Returns:
        Dictionary with memory usage results
    """
    print("\n" + "=" * 70)
    print("BENCHMARK 3: Memory Usage")
    print("=" * 70)

    # Benchmark 1: Memory usage without cache
    ts_parser.clear_cache()
    tracemalloc.start()

    for _, content in test_files:
        ts_parser.parse(content)
        # Force parse without using cache
        ts_parser.clear_cache()

    _, peak_no_cache = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Benchmark 2: Memory usage with cache
    ts_parser.clear_cache()
    tracemalloc.start()

    for _, content in test_files:
        ts_parser.parse(content)

    _, peak_with_cache = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(f"\nMemory usage for {len(test_files)} files:")
    print(f"  Without cache: {peak_no_cache / 1024 / 1024:.2f} MB (peak)")
    print(f"  With cache:    {peak_with_cache / 1024 / 1024:.2f} MB (peak)")
    print(f"  Cache overhead: {(peak_with_cache - peak_no_cache) / 1024 / 1024:.2f} MB")

    cache_stats = ts_parser.get_cache_stats()
    print(f"  Cached trees: {cache_stats['size']} / {cache_stats['capacity']}")

    return {
        "peak_no_cache_mb": peak_no_cache / 1024 / 1024,
        "peak_with_cache_mb": peak_with_cache / 1024 / 1024,
        "cache_overhead_mb": (peak_with_cache - peak_no_cache) / 1024 / 1024,
    }


def print_summary(cache_results: dict, query_results: dict, memory_results: dict):
    """Print overall summary of benchmarks."""
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    print("\n📊 Performance Improvements:")
    print(f"  • Cache speedup:       {cache_results['speedup']:.2f}x faster")
    print(f"  • Query avg speedup:   {query_results['avg_speedup']:.2f}x faster")
    print(f"    - Classes:           {query_results['class_speedup']:.2f}x")
    print(f"    - Imports:           {query_results['import_speedup']:.2f}x")
    print(f"    - Function calls:    {query_results['call_speedup']:.2f}x")

    print("\n💾 Memory Usage:")
    print(f"  • Peak without cache:  {memory_results['peak_no_cache_mb']:.2f} MB")
    print(f"  • Peak with cache:     {memory_results['peak_with_cache_mb']:.2f} MB")
    print(f"  • Cache overhead:      {memory_results['cache_overhead_mb']:.2f} MB")

    # Calculate overall improvement
    total_speedup = cache_results["speedup"] * query_results["avg_speedup"]
    print(f"\n✨ Combined optimization: ~{total_speedup:.1f}x faster (cache + queries)")

    # Determine if improvements are significant
    if cache_results["speedup"] > 1.5 and query_results["avg_speedup"] > 1.5:
        print("\n✅ SIGNIFICANT IMPROVEMENT - Ready to commit!")
    elif cache_results["speedup"] > 1.2 or query_results["avg_speedup"] > 1.2:
        print("\n⚠️  MODERATE IMPROVEMENT - Consider additional optimizations")
    else:
        print("\n❌ MINIMAL IMPROVEMENT - Further optimization needed")


def main():
    """Run all benchmarks."""
    print("=" * 70)
    print("Tree-sitter Performance Benchmark Suite")
    print("=" * 70)

    # Load test files
    print("\nLoading test files from codebase...")
    test_files = load_test_files()
    print(f"Loaded {len(test_files)} Python files for testing")

    total_lines = sum(len(content.splitlines()) for _, content in test_files)
    print(f"Total lines of code: {total_lines}")

    # Run benchmarks
    cache_results = benchmark_parsing_with_cache(test_files)
    query_results = benchmark_query_vs_walk(test_files)
    memory_results = benchmark_memory_usage(test_files)

    # Print summary
    print_summary(cache_results, query_results, memory_results)


if __name__ == "__main__":
    main()
