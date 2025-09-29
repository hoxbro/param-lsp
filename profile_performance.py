#!/usr/bin/env python3
"""Performance profiling script for param-lsp analyzer."""

import time
from pathlib import Path

from src.param_lsp.analyzer import ParamAnalyzer


def profile_analyzer_performance():
    """Profile the performance of the ParamAnalyzer."""
    # Test content with various complexity levels
    simple_content = '''
import param

class SimpleClass(param.Parameterized):
    x = param.Number(default=1.0, bounds=(0, 10))
    name = param.String(default="test")
'''

    complex_content = '''
import param
from typing import Optional

class Parent(param.Parameterized):
    base_param = param.Integer(default=5, bounds=(1, 100))
    shared_name = param.String(default="parent")

class Child(Parent):
    child_param = param.Number(default=2.5, bounds=(0.0, 5.0))
    flag = param.Boolean(default=True)
    items = param.List(default=[], doc="List of items")

class GrandChild(Child):
    grand_param = param.Parameter(default=None, allow_None=True)
    number = param.Integer(default=42, bounds=(10, 100))

# Test various assignments for validation
obj = SimpleClass()
obj.x = 5.0  # Valid
obj.name = "hello"  # Valid

child = Child()
child.base_param = 50  # Valid inherited
child.child_param = 3.0  # Valid

# Create constructor calls
simple_instance = SimpleClass(x=3.0, name="constructed")
child_instance = Child(base_param=25, child_param=1.5, flag=False)
'''

    # Initialize analyzer
    analyzer = ParamAnalyzer()

    print("Performance Profiling for param-lsp Analyzer")
    print("=" * 50)

    # Profile simple content
    start_time = time.perf_counter()
    for i in range(100):
        analyzer.analyze_file(simple_content)
    simple_time = time.perf_counter() - start_time

    print(f"Simple analysis (100 iterations): {simple_time:.4f}s")
    print(f"Average per simple analysis: {simple_time/100*1000:.2f}ms")

    # Profile complex content
    start_time = time.perf_counter()
    for i in range(50):
        analyzer.analyze_file(complex_content)
    complex_time = time.perf_counter() - start_time

    print(f"Complex analysis (50 iterations): {complex_time:.4f}s")
    print(f"Average per complex analysis: {complex_time/50*1000:.2f}ms")

    # Single detailed analysis for insights
    start_time = time.perf_counter()
    result = analyzer.analyze_file(complex_content)
    single_time = time.perf_counter() - start_time

    print(f"\nSingle complex analysis: {single_time*1000:.2f}ms")
    print(f"Classes detected: {len(result['param_classes'])}")
    print(f"Imports detected: {len(result['imports'])}")
    print(f"Type errors found: {len(result['type_errors'])}")

    # Test with a real file if available
    test_files = [
        "tests/test_analyzer/test_validation.py",
        "src/param_lsp/analyzer.py",
        "src/param_lsp/models.py"
    ]

    for test_file in test_files:
        if Path(test_file).exists():
            with open(test_file) as f:
                content = f.read()

            start_time = time.perf_counter()
            result = analyzer.analyze_file(content, test_file)
            file_time = time.perf_counter() - start_time

            print(f"\nReal file analysis ({test_file}): {file_time*1000:.2f}ms")
            print(f"  Classes: {len(result['param_classes'])}")
            print(f"  Imports: {len(result['imports'])}")
            print(f"  Errors: {len(result['type_errors'])}")
            break


if __name__ == "__main__":
    profile_analyzer_performance()