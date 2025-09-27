#!/usr/bin/env python3

from src.param_lsp.analyzer import ParamAnalyzer

code = """
import param

class TestClass(param.Parameterized):
    invalid_bounds1 = param.Integer(bounds=(10, 5))  # min > max
    invalid_bounds2 = param.Number(bounds=(5.0, 5.0))  # min == max
"""

analyzer = ParamAnalyzer()
result = analyzer.analyze_file(code)

print("Type errors found:", len(result.get("type_errors", [])))
for error in result.get("type_errors", []):
    print(f"- {error['code']}: {error['message']}")

print("\nParam classes:")
for name, cls_info in result.get("param_classes", {}).items():
    print(f"- {name}: {cls_info}")
    for param_name, param_info in cls_info.parameters.items():
        print(f"  - {param_name}: cls={param_info.cls}, bounds={param_info.bounds}")