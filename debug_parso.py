#!/usr/bin/env python3

import parso

# Test parso structure for function calls with keyword arguments
test_code = """
param.Integer(default=10, bounds=(0, 100), doc="test parameter")
"""

grammar = parso.load_grammar()
tree = grammar.parse(test_code, error_recovery=True)

def print_tree(node, indent=0):
    spaces = "  " * indent
    print(f"{spaces}{node.type}: {repr(node.value) if hasattr(node, 'value') else ''}")
    if hasattr(node, 'children'):
        for child in node.children:
            print_tree(child, indent + 1)

print_tree(tree)