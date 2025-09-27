#!/usr/bin/env python3

import parso
from src.param_lsp.analyzer import ParamAnalyzer

# Test parso structure for function calls with bounds
test_code = """
param.Integer(bounds=(10, 5))
"""

grammar = parso.load_grammar()
tree = grammar.parse(test_code, error_recovery=True)

def print_tree(node, indent=0):
    spaces = "  " * indent
    print(f"{spaces}{node.type}: {repr(node.value) if hasattr(node, 'value') else ''}")
    if hasattr(node, 'children'):
        for child in node.children:
            print_tree(child, indent + 1)

print("Parso tree structure:")
print_tree(tree)

print("\n" + "="*50)

# Test bounds extraction
analyzer = ParamAnalyzer()

# Get the param call node
def find_param_call(node):
    if node.type in ("power", "atom_expr"):
        return node
    if hasattr(node, 'children'):
        for child in node.children:
            result = find_param_call(child)
            if result:
                return result
    return None

param_call = find_param_call(tree)
if param_call:
    print(f"Found param call: {param_call}")

    # Test our keyword extraction
    kwargs = analyzer._get_keyword_arguments(param_call)
    print(f"Extracted kwargs: {kwargs}")

    # Test bounds extraction specifically
    bounds = analyzer._extract_bounds_from_call(param_call)
    print(f"Extracted bounds: {bounds}")
else:
    print("No param call found")