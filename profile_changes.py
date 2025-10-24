#!/usr/bin/env python
"""Profile the external analyzer performance."""

from __future__ import annotations

import cProfile
import pstats
import sys
import tempfile
from io import StringIO
from pathlib import Path

from param_lsp._analyzer.static_external_analyzer import ExternalClassInspector
from param_lsp.cache import external_library_cache


def profile_cache_population():
    """Profile the cache population for a library."""
    # Use a small library for testing
    inspector = ExternalClassInspector()

    # Profile panel library population
    print("Profiling panel library cache population...")
    count = inspector.populate_library_cache("panel")
    print(f"Populated {count} classes")

    return inspector


def profile_class_analysis():
    """Profile individual class analysis."""
    inspector = ExternalClassInspector()

    # Analyze a few specific classes
    test_classes = [
        "panel.widgets.IntSlider",
        "panel.layout.Row",
        "panel.pane.Markdown",
    ]

    print("\nProfiling individual class analysis...")
    for class_path in test_classes:
        result = inspector.analyze_external_class(class_path)
        print(f"Analyzed {class_path}: {result is not None}")

    return inspector


def main():
    """Run profiling with different scenarios."""
    # Clear cache for clean profiling
    print("Clearing cache...")
    import os
    import shutil

    cache_dir = external_library_cache.cache_dir
    if cache_dir.exists():
        cleared_count = 0
        for cache_file in cache_dir.glob("*.json"):
            # Only clear panel cache for focused profiling
            if cache_file.name.startswith("panel"):
                cache_file.unlink()
                print(f"Cleared {cache_file.name}")
                cleared_count += 1
        print(f"Cleared {cleared_count} cache file(s)")
    else:
        print(f"Cache directory {cache_dir} does not exist")

    print("Cache cleared successfully")

    # Profile cache population
    print("\n" + "=" * 80)
    print("PROFILING CACHE POPULATION")
    print("=" * 80)

    profiler = cProfile.Profile()
    profiler.enable()

    inspector = profile_cache_population()

    profiler.disable()

    # Print profiling results
    s = StringIO()
    stats = pstats.Stats(profiler, stream=s)
    stats.strip_dirs()
    stats.sort_stats("cumulative")

    print("\n\nTop 30 functions by cumulative time:")
    print("-" * 80)
    stats.print_stats(30)
    print(s.getvalue())

    # Save detailed stats
    stats_file = Path("profile_stats.txt")
    with open(stats_file, "w") as f:
        stats = pstats.Stats(profiler, stream=f)
        stats.strip_dirs()
        stats.sort_stats("cumulative")
        f.write("\n\nCUMULATIVE TIME\n")
        f.write("=" * 80 + "\n")
        stats.print_stats(50)

        stats.sort_stats("time")
        f.write("\n\nTOTAL TIME\n")
        f.write("=" * 80 + "\n")
        stats.print_stats(50)

        stats.sort_stats("calls")
        f.write("\n\nCALL COUNT\n")
        f.write("=" * 80 + "\n")
        stats.print_stats(50)

    print(f"\nDetailed stats saved to {stats_file}")

    # Print summary statistics
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    total_time = sum(stat[2] for stat in stats.stats.values())
    print(f"Total profiled time: {total_time:.2f}s")

    # Find hotspots
    print("\nHotspot analysis:")
    stats.sort_stats("cumulative")

    # Get top functions
    top_funcs = []
    for func, stat in list(stats.stats.items())[:20]:
        filename, line, func_name = func
        cc, nc, tt, ct, callers = stat
        if "param_lsp" in filename:
            top_funcs.append((func_name, ct, cc))

    print("\nTop param_lsp functions by cumulative time:")
    for func_name, cum_time, calls in sorted(top_funcs, key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {func_name:50s} {cum_time:8.3f}s ({calls:6d} calls)")


if __name__ == "__main__":
    main()
