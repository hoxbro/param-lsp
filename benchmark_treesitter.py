#!/usr/bin/env python3
"""Benchmark script for tree-sitter query optimization.

Measures performance improvements from query-based AST pattern matching
vs manual tree walking.
"""

from __future__ import annotations

import time
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


def benchmark_query_vs_walk(test_files: list[tuple[str, str]]) -> dict:
    """Benchmark query-based vs manual tree walking.

    Args:
        test_files: List of (filepath, content) tuples

    Returns:
        Dictionary with benchmark results
    """
    print("\n" + "=" * 70)
    print("BENCHMARK: Query-based vs Manual Tree Walking")
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


def print_summary(query_results: dict):
    """Print overall summary of benchmarks."""
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    print("\n📊 Query-based AST Pattern Matching Performance:")
    print(f"  • Average speedup:     {query_results['avg_speedup']:.2f}x faster")
    print(f"    - Classes:           {query_results['class_speedup']:.2f}x")
    print(f"    - Imports:           {query_results['import_speedup']:.2f}x")
    print(f"    - Function calls:    {query_results['call_speedup']:.2f}x")

    print(f"\n  • Total manual time:   {query_results['manual_time'] * 1000:.2f}ms")
    print(f"  • Total query time:    {query_results['query_time'] * 1000:.2f}ms")

    # Determine if improvements are significant
    if query_results["avg_speedup"] > 1.5:
        print("\n✅ SIGNIFICANT IMPROVEMENT - Queries are much faster than manual walking!")
    elif query_results["avg_speedup"] > 1.2:
        print("\n⚠️  MODERATE IMPROVEMENT - Queries provide some benefit")
    else:
        print("\n❌ MINIMAL IMPROVEMENT - Query optimization not effective")


def main():
    """Run all benchmarks."""
    print("=" * 70)
    print("Tree-sitter Query Optimization Benchmark")
    print("=" * 70)

    # Load test files
    print("\nLoading test files from codebase...")
    test_files = load_test_files()
    print(f"Loaded {len(test_files)} Python files for testing")

    total_lines = sum(len(content.splitlines()) for _, content in test_files)
    print(f"Total lines of code: {total_lines}")

    # Run benchmarks
    query_results = benchmark_query_vs_walk(test_files)

    # Print summary
    print_summary(query_results)


if __name__ == "__main__":
    main()
