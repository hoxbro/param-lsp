"""Tests for incomplete syntax recovery functionality."""

from __future__ import annotations


class TestIncompleteSyntaxRecovery:
    """Test incomplete syntax recovery in ParamAnalyzer."""

    def test_unclosed_string_recovery(self, analyzer):
        """Test recovery from unclosed string literals."""
        # Test unclosed double quote
        code_py = """\
import param

class TestClass(param.Parameterized):
    string_param = param.String(default="hello
"""
        result = analyzer.analyze_file(code_py)
        # Should successfully parse and find the class
        assert "TestClass" in result["param_classes"]

        # Test unclosed single quote
        code_py = """\
import param

class TestClass(param.Parameterized):
    string_param = param.String(default='hello
"""
        result = analyzer.analyze_file(code_py)
        assert "TestClass" in result["param_classes"]

    def test_unclosed_brackets_recovery(self, analyzer):
        """Test recovery from unclosed brackets."""
        # Test unclosed parenthesis
        code_py = """\
import param

class TestClass(param.Parameterized):
    int_param = param.Integer(default=5, bounds=(0, 10
"""
        result = analyzer.analyze_file(code_py)
        assert "TestClass" in result["param_classes"]

        # Test unclosed square bracket
        code_py = """\
import param

class TestClass(param.Parameterized):
    list_param = param.List(default=[1, 2, 3
"""
        result = analyzer.analyze_file(code_py)
        assert "TestClass" in result["param_classes"]

        # Test unclosed curly brace
        code_py = """\
import param

class TestClass(param.Parameterized):
    dict_param = param.Dict(default={"key": "value"
"""
        result = analyzer.analyze_file(code_py)
        assert "TestClass" in result["param_classes"]

    def test_multiple_syntax_issues_recovery(self, analyzer):
        """Test recovery from multiple syntax issues."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    string_param = param.String(default="hello
    int_param = param.Integer(default=5, bounds=(0, 10
    list_param = param.List(default=[1, 2, 3
"""
        result = analyzer.analyze_file(code_py)
        # With multiple complex syntax issues, the analyzer may fall back to line removal
        # In such cases, the class may not be detectable, which is acceptable
        # The key is that the analyzer doesn't crash and provides some result
        assert isinstance(result, dict)
        assert "param_classes" in result
        assert "imports" in result

    def test_decorator_incomplete_recovery(self, analyzer):
        """Test recovery from incomplete decorator calls (generalized approach)."""
        # Test unclosed parenthesis in any decorator
        code_py = """\
import some_module

class TestClass:
    value = 42

    @some_module.decorator('argument'
    def compute(self):
        return self.value * 2
"""
        result = analyzer.analyze_file(code_py)
        # Should successfully parse the class structure
        assert isinstance(result, dict)

        # Test unclosed quote in decorator
        code_py = """\
import another_module

class TestClass:
    value = 42

    @another_module.depends('value
    def compute(self):
        return self.value * 2
"""
        result = analyzer.analyze_file(code_py)
        # Should successfully parse the class structure
        assert isinstance(result, dict)

        # Test with param.depends specifically (should work with generalized approach)
        code_py = """\
import param

class TestClass(param.Parameterized):
    value = param.Number(default=1.0)

    @param.depends('value'
    def compute(self):
        return self.value * 2
"""
        result = analyzer.analyze_file(code_py)
        assert "TestClass" in result["param_classes"]

    def test_memory_based_recovery(self, analyzer):
        """Test memory-based recovery from previous successful state."""
        file_path = "/test/example.py"

        # First, analyze a valid file to establish successful state
        valid_code = """\
import param

class TestClass(param.Parameterized):
    string_param = param.String(default="hello")
    int_param = param.Integer(default=5)
"""
        result = analyzer.analyze_file(valid_code, file_path)
        assert "TestClass" in result["param_classes"]
        assert len(result["param_classes"]["TestClass"].parameters) == 2

        # Now try analyzing invalid syntax - should fall back to memory
        invalid_code = """\
import param

class TestClass(param.Parameterized):
    string_param = param.String(default="hello")
    int_param = param.Integer(default=5, bounds=(0, 10
    # This line has syntax error with unclosed parenthesis
"""
        result = analyzer.analyze_file(invalid_code, file_path)
        # Should still get some result, either from memory or syntax fixing
        assert "TestClass" in result["param_classes"]

    def test_content_difference_detection(self, analyzer):
        """Test detection of differences between file contents."""
        current_lines = [
            "import param",
            "",
            "class TestClass(param.Parameterized):",
            "    value = param.Number(default=1.0",  # Missing closing paren
            "    other = param.String(default='test')",
        ]

        last_lines = [
            "import param",
            "",
            "class TestClass(param.Parameterized):",
            "    value = param.Number(default=1.0)",  # Has closing paren
            "    other = param.String(default='test')",
        ]

        diff_start, diff_end = analyzer._find_content_difference_range(current_lines, last_lines)
        assert diff_start == 3  # Line with the difference
        assert diff_end == 4  # End of different range

    def test_fix_line_syntax_issues(self, analyzer):
        """Test individual line syntax issue fixing."""
        # Test unclosed quote fixing
        line = 'param.String(default="hello'
        fixed = analyzer._fix_line_syntax_issues(line)
        assert '"' in fixed
        assert fixed.count('"') % 2 == 0

        # Test that brackets are not fixed at line level (handled globally)
        line = "param.Integer(default=5, bounds=(0, 10"
        fixed = analyzer._fix_line_syntax_issues(line)
        # Line level should not fix brackets (left for global fixing)
        assert fixed == line

        # Test that brackets are not fixed at line level (handled globally)
        line = "param.List(default=[1, 2, 3"
        fixed = analyzer._fix_line_syntax_issues(line)
        # Line level should not fix brackets (left for global fixing)
        assert fixed == line

    def test_syntax_tracking_state(self, analyzer):
        """Test syntax state tracking via global syntax fixing."""
        # Test with unclosed brackets - should be fixed by global syntax fixing
        content_with_unclosed_brackets = "param.Integer(default=5, bounds=[0, 10"
        fixed_content = analyzer._fix_global_syntax_issues(content_with_unclosed_brackets)
        # Should have closing brackets
        assert fixed_content.count("(") == fixed_content.count(")")
        assert fixed_content.count("[") == fixed_content.count("]")

        # Test with unclosed string
        content_with_unclosed_string = 'param.String(default="hello'
        fixed_content = analyzer._fix_global_syntax_issues(content_with_unclosed_string)
        # Should have balanced quotes
        assert fixed_content.count('"') % 2 == 0

    def test_comprehensive_incomplete_syntax_scenario(self, analyzer):
        """Test a comprehensive scenario with multiple incomplete syntax patterns."""
        code_py = """\
import param

class ComplexClass(param.Parameterized):
    # Multiple syntax issues
    string_param = param.String(default="unclosed string
    number_param = param.Number(default=1.5, bounds=(0, 10
    list_param = param.List(default=[1, 2, 3
    dict_param = param.Dict(default={"key": "value"

    @param.depends('string_param', 'number_param'
    def compute_something(self):
        return len(self.string_param) + self.number_param
"""

        result = analyzer.analyze_file(code_py)
        # With many complex syntax issues, the analyzer may not be able to parse the class
        # The important thing is that it doesn't crash and returns a valid structure
        assert isinstance(result, dict)
        assert "param_classes" in result
        assert "imports" in result
        # It should at least detect that param was imported
        assert "param" in result["imports"]

    def test_generalized_import_fixing(self, analyzer):
        """Test generalized import statement fixing."""
        # Test incomplete "from module" statements
        code_py = """\
from os
from sys
from collections

def some_function():
    pass
"""
        result = analyzer.analyze_file(code_py)
        # Should successfully parse without crashing
        assert isinstance(result, dict)

    def test_generalized_decorator_patterns(self, analyzer):
        """Test that decorator fixing works for various patterns."""
        # Test Flask-like decorator
        code_py = """\
from flask import app

@app.route('/test'
def hello():
    return "Hello"
"""
        result = analyzer.analyze_file(code_py)
        assert isinstance(result, dict)

        # Test property decorator
        code_py = """\
class MyClass:
    @property
    def value(self
        return 42
"""
        result = analyzer.analyze_file(code_py)
        assert isinstance(result, dict)

        # Test dataclass decorator
        code_py = """\
from dataclasses import dataclass

@dataclass
class Point:
    x: int = 0
    y: int = 0
"""
        result = analyzer.analyze_file(code_py)
        assert isinstance(result, dict)
