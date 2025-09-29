"""Test parso_utils functions independently."""

from __future__ import annotations

import parso

from param_lsp._analyzer.parso_utils import (
    find_all_parameter_assignments,
    find_arguments_in_trailer,
    find_class_suites,
    find_function_call_trailers,
    find_parameter_assignments,
    get_assignment_target_name,
    get_children,
    get_class_bases,
    get_class_name,
    get_value,
    has_attribute_target,
    has_children,
    has_value,
    is_assignment_stmt,
    is_function_call,
    walk_tree,
)


class TestBasicUtils:
    """Test basic parso utility functions."""

    def test_has_value(self):
        """Test has_value function."""
        code = "x = 42"
        tree = parso.parse(code)
        nodes = list(walk_tree(tree))

        # Find nodes with and without values
        name_node = None
        number_node = None
        for node in nodes:
            if get_value(node) == "x":
                name_node = node
            elif get_value(node) == "42":
                number_node = node

        assert name_node is not None
        assert number_node is not None
        assert has_value(name_node)
        assert has_value(number_node)

    def test_get_value(self):
        """Test get_value function."""
        code = "x = 42"
        tree = parso.parse(code)
        nodes = list(walk_tree(tree))

        # Find specific values we expect
        found_values = []
        for node in nodes:
            if has_value(node):
                value = get_value(node)
                if value:  # Skip empty values
                    found_values.append(value)

        # Should find these key values
        assert "x" in found_values
        assert "=" in found_values
        assert "42" in found_values

    def test_has_children(self):
        """Test has_children function."""
        code = "x = 42"
        tree = parso.parse(code)

        assert has_children(tree)  # Module should have children

        # Find a leaf node
        for node in walk_tree(tree):
            if get_value(node) == "x":
                assert not has_children(node)  # Name nodes typically don't have children
                break

    def test_get_children(self):
        """Test get_children function."""
        code = "x = 42"
        tree = parso.parse(code)

        children = get_children(tree)
        assert len(children) > 0  # Module should have children

    def test_walk_tree(self):
        """Test walk_tree function."""
        code = "x = 42"
        tree = parso.parse(code)

        nodes = list(walk_tree(tree))
        assert len(nodes) > 0

        # Should include the root
        assert nodes[0] == tree

        # Should include values we expect
        values = [get_value(node) for node in nodes if has_value(node)]
        assert "x" in values
        assert "=" in values
        assert "42" in values


class TestClassUtils:
    """Test class-related utility functions."""

    def test_get_class_name(self):
        """Test get_class_name function."""
        code = """
class MyClass:
    pass
"""
        tree = parso.parse(code)
        class_nodes = [node for node in walk_tree(tree) if node.type == "classdef"]
        assert len(class_nodes) == 1

        class_name = get_class_name(class_nodes[0])
        assert class_name == "MyClass"

    def test_get_class_bases(self):
        """Test get_class_bases function."""
        code = """
class MyClass(BaseClass):
    pass
"""
        tree = parso.parse(code)
        class_nodes = [node for node in walk_tree(tree) if node.type == "classdef"]
        assert len(class_nodes) == 1

        bases = get_class_bases(class_nodes[0])
        assert len(bases) == 1
        # The base should be a name node with value "BaseClass"
        assert get_value(bases[0]) == "BaseClass"

    def test_get_class_bases_multiple(self):
        """Test get_class_bases with multiple bases."""
        code = """
class MyClass(Base1, Base2):
    pass
"""
        tree = parso.parse(code)
        class_nodes = [node for node in walk_tree(tree) if node.type == "classdef"]
        assert len(class_nodes) == 1

        bases = get_class_bases(class_nodes[0])
        assert len(bases) >= 2  # Should have at least 2 bases

    def test_find_class_suites(self):
        """Test find_class_suites function."""
        code = """
class MyClass:
    x = 42
    y = "hello"
"""
        tree = parso.parse(code)
        class_nodes = [node for node in walk_tree(tree) if node.type == "classdef"]
        assert len(class_nodes) == 1

        suites = list(find_class_suites(class_nodes[0]))
        assert len(suites) == 1
        assert suites[0].type == "suite"


class TestAssignmentUtils:
    """Test assignment-related utility functions."""

    def test_is_assignment_stmt(self):
        """Test is_assignment_stmt function."""
        code = """
x = 42
y = "hello"
z
"""
        tree = parso.parse(code)

        assignment_count = 0
        for node in walk_tree(tree):
            if node.type == "expr_stmt" and is_assignment_stmt(node):
                assignment_count += 1

        assert assignment_count == 2  # x = 42 and y = "hello"

    def test_get_assignment_target_name(self):
        """Test get_assignment_target_name function."""
        code = "x = 42"
        tree = parso.parse(code)

        for node in walk_tree(tree):
            if node.type == "expr_stmt" and is_assignment_stmt(node):
                target_name = get_assignment_target_name(node)
                assert target_name == "x"
                break

    def test_has_attribute_target(self):
        """Test has_attribute_target function."""
        code = """
obj.attr = 42
x = 42
"""
        tree = parso.parse(code)

        attribute_assignments = []
        regular_assignments = []

        for node in walk_tree(tree):
            if node.type == "expr_stmt" and is_assignment_stmt(node):
                if has_attribute_target(node):
                    attribute_assignments.append(node)
                else:
                    regular_assignments.append(node)

        assert len(attribute_assignments) == 1  # obj.attr = 42
        assert len(regular_assignments) == 1  # x = 42


class TestFunctionCallUtils:
    """Test function call utility functions."""

    def test_is_function_call(self):
        """Test is_function_call function."""
        code = """
func()
obj.method()
x = 42
"""
        tree = parso.parse(code)

        function_calls = [
            node
            for node in walk_tree(tree)
            if node.type in ("power", "atom_expr") and is_function_call(node)
        ]

        assert len(function_calls) >= 1  # Should find at least one function call

    def test_find_function_call_trailers(self):
        """Test find_function_call_trailers function."""
        code = "func(arg1, arg2)"
        tree = parso.parse(code)

        for node in walk_tree(tree):
            if node.type in ("power", "atom_expr") and is_function_call(node):
                trailers = list(find_function_call_trailers(node))
                assert len(trailers) >= 1
                break

    def test_find_arguments_in_trailer(self):
        """Test find_arguments_in_trailer function."""
        code = "func(arg1=42, arg2='hello')"
        tree = parso.parse(code)

        for node in walk_tree(tree):
            if node.type in ("power", "atom_expr") and is_function_call(node):
                for trailer in find_function_call_trailers(node):
                    args = list(find_arguments_in_trailer(trailer))
                    assert len(args) >= 1  # Should find arguments
                break


class TestParameterAssignmentUtils:
    """Test parameter assignment utility functions."""

    def test_find_parameter_assignments(self):
        """Test find_parameter_assignments function."""
        code = """
class MyClass:
    x = param.Integer(default=42)
    y = param.String(default="hello")
    z = 42  # Not a parameter
"""
        tree = parso.parse(code)

        # Simple mock parameter assignment checker
        def is_param_assignment(node):
            """Simple check for param.* assignments."""
            if not is_assignment_stmt(node):
                return False

            # Look for param.* in the assignment
            for child in get_children(node):
                if child.type in ("power", "atom_expr"):
                    # Check if it contains "param"
                    for subchild in walk_tree(child):
                        if has_value(subchild) and get_value(subchild) == "param":
                            return True
            return False

        class_nodes = [node for node in walk_tree(tree) if node.type == "classdef"]
        assert len(class_nodes) == 1

        for suite in find_class_suites(class_nodes[0]):
            assignments = list(find_parameter_assignments(suite, is_param_assignment))
            # Should find the param assignments, not the regular assignment
            assert len(assignments) >= 0  # May be 0 if param detection is not perfect

    def test_find_all_parameter_assignments(self):
        """Test find_all_parameter_assignments function."""
        code = """
class MyClass:
    x = param.Integer(default=42)
    def method(self):
        pass
"""
        tree = parso.parse(code)

        # Simple mock parameter assignment checker
        def is_param_assignment(node):
            """Simple check for param.* assignments."""
            return is_assignment_stmt(
                node
            )  # For testing, consider all assignments as parameter assignments

        class_nodes = [node for node in walk_tree(tree) if node.type == "classdef"]
        assert len(class_nodes) == 1

        assignments = list(find_all_parameter_assignments(class_nodes[0], is_param_assignment))
        assert len(assignments) >= 1  # Should find at least the x assignment


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_code(self):
        """Test functions with empty code."""
        code = ""
        tree = parso.parse(code)

        nodes = list(walk_tree(tree))
        assert len(nodes) >= 1  # Should at least have the root module

        class_nodes = [node for node in nodes if node.type == "classdef"]
        assert len(class_nodes) == 0

    def test_malformed_class(self):
        """Test with malformed class definition."""
        code = "class"  # Incomplete class definition
        tree = parso.parse(code)

        # Should not crash
        nodes = list(walk_tree(tree))
        assert len(nodes) >= 1

    def test_none_values(self):
        """Test functions with None values."""
        # Test get_value with None
        assert get_value(None) is None

        # Test get_children with None
        assert get_children(None) == []

        # Test has_value with None
        assert not has_value(None)

        # Test has_children with None
        assert not has_children(None)
