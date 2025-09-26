"""Tests for runtime parameter assignment checking functionality."""

from __future__ import annotations


class TestRuntimeAssignmentChecking:
    """Test runtime parameter assignment validation."""

    def test_valid_runtime_assignments(self, analyzer):
        """Test valid runtime assignments don't generate errors."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    string_param = param.String(default="hello")
    int_param = param.Integer(default=5)
    bool_param = param.Boolean(default=True)

# Valid assignments
instance = TestClass()
instance.string_param = "world"
instance.int_param = 10
instance.bool_param = False

# Also test direct instantiation assignment
TestClass().string_param = "direct"
"""

        result = analyzer.analyze_file(code_py)

        runtime_errors = [e for e in result["type_errors"] if e["code"].startswith("runtime")]
        assert len(runtime_errors) == 0

    def test_runtime_type_mismatches(self, analyzer):
        """Test runtime assignment type mismatches generate errors."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    string_param = param.String(default="hello")
    int_param = param.Integer(default=5)

instance = TestClass()
instance.string_param = 123      # Error: int to String
instance.int_param = "not_int"   # Error: str to Integer
"""

        result = analyzer.analyze_file(code_py)

        runtime_errors = [e for e in result["type_errors"] if e["code"] == "runtime-type-mismatch"]
        assert len(runtime_errors) == 2

        error_messages = [e["message"] for e in runtime_errors]
        assert any("string_param" in msg and "int" in msg for msg in error_messages)
        assert any("int_param" in msg and "str" in msg for msg in error_messages)

    def test_runtime_boolean_strict_checking(self, analyzer):
        """Test runtime Boolean assignment strict checking."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    bool_param = param.Boolean(default=True)

instance = TestClass()
instance.bool_param = 1        # Error: int not allowed for Boolean
instance.bool_param = 0        # Error: int not allowed for Boolean
instance.bool_param = "yes"    # Error: str not allowed for Boolean
TestClass().bool_param = []    # Error: list not allowed for Boolean
"""

        result = analyzer.analyze_file(code_py)

        boolean_errors = [
            e for e in result["type_errors"] if e["code"] == "runtime-boolean-type-mismatch"
        ]
        assert len(boolean_errors) == 4

        for error in boolean_errors:
            assert "Boolean parameter" in error["message"]
            assert "expects True/False" in error["message"]

    def test_runtime_bounds_violations(self, analyzer):
        """Test runtime assignment bounds violations."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    int_param = param.Integer(default=5, bounds=(0, 10))
    number_param = param.Number(default=2.5, bounds=(1.0, 5.0))

instance = TestClass()
instance.int_param = -5        # Error: below minimum
instance.int_param = 15        # Error: above maximum
instance.number_param = 0.5    # Error: below minimum
instance.number_param = 6.0    # Error: above maximum
"""

        result = analyzer.analyze_file(code_py)

        bounds_errors = [e for e in result["type_errors"] if e["code"] == "bounds-violation"]
        assert len(bounds_errors) == 4

        for error in bounds_errors:
            assert "outside bounds" in error["message"]
            assert "[" in error["message"] or "(" in error["message"]  # Bounds notation

    def test_runtime_inclusive_bounds_checking(self, analyzer):
        """Test runtime bounds checking with inclusive_bounds."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    # Exclusive bounds (0, 5)
    exclusive_param = param.Number(default=2.5, bounds=(0, 5), inclusive_bounds=(False, False))
    # Mixed bounds [0, 5)
    mixed_param = param.Number(default=2.5, bounds=(0, 5), inclusive_bounds=(True, False))

instance = TestClass()
instance.exclusive_param = 0    # Error: at exclusive minimum
instance.exclusive_param = 5    # Error: at exclusive maximum
instance.mixed_param = 0        # Valid: at inclusive minimum
instance.mixed_param = 5        # Error: at exclusive maximum
"""

        result = analyzer.analyze_file(code_py)

        bounds_errors = [e for e in result["type_errors"] if e["code"] == "bounds-violation"]
        assert len(bounds_errors) == 3  # Three violations

        # Check bounds notation in error messages
        error_messages = [e["message"] for e in bounds_errors]
        assert any("(0, 5)" in msg for msg in error_messages)  # Exclusive bounds
        assert any("[0, 5)" in msg for msg in error_messages)  # Mixed bounds

    def test_direct_instantiation_assignments(self, analyzer):
        """Test assignments to direct class instantiations."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    string_param = param.String(default="hello")
    int_param = param.Integer(default=5, bounds=(0, 10))

# Direct instantiation assignments
TestClass().string_param = 123      # Error: type mismatch
TestClass().int_param = -5          # Error: bounds violation
TestClass().string_param = "valid"  # Valid
"""

        result = analyzer.analyze_file(code_py)

        runtime_errors = [
            e
            for e in result["type_errors"]
            if e["code"].startswith("runtime") or e["code"] == "bounds-violation"
        ]
        assert len(runtime_errors) == 2

    def test_variable_assignment_pattern_matching(self, analyzer):
        """Test that both variable.param and Class().param patterns are detected."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    test_param = param.String(default="hello")

# Variable assignment pattern
instance = TestClass()
instance.test_param = 123

# Direct instantiation pattern
TestClass().test_param = 456
"""

        result = analyzer.analyze_file(code_py)

        runtime_errors = [e for e in result["type_errors"] if e["code"] == "runtime-type-mismatch"]
        assert len(runtime_errors) == 2

    def test_multiple_param_classes(self, analyzer):
        """Test runtime checking with multiple param classes."""
        code_py = """\
import param

class ClassA(param.Parameterized):
    param_a = param.String(default="a")

class ClassB(param.Parameterized):
    param_b = param.Integer(default=1)

a_instance = ClassA()
b_instance = ClassB()

a_instance.param_a = 123    # Error: wrong type for ClassA
b_instance.param_b = "str"  # Error: wrong type for ClassB

# Valid assignments
a_instance.param_a = "valid"
b_instance.param_b = 42
"""

        result = analyzer.analyze_file(code_py)

        runtime_errors = [e for e in result["type_errors"] if e["code"] == "runtime-type-mismatch"]
        assert len(runtime_errors) == 2

    def test_non_param_assignments_ignored(self, analyzer):
        """Test that assignments to non-param objects are ignored."""
        code_py = """\
import param

class RegularClass:
    def __init__(self):
        self.attr = "value"

class ParamClass(param.Parameterized):
    param_attr = param.String(default="hello")

regular = RegularClass()
param_obj = ParamClass()

# These should be ignored (no errors)
regular.attr = 123
regular.new_attr = "anything"

# This should generate an error
param_obj.param_attr = 456
"""

        result = analyzer.analyze_file(code_py)

        runtime_errors = [e for e in result["type_errors"] if e["code"] == "runtime-type-mismatch"]
        assert len(runtime_errors) == 1
        assert "param_attr" in runtime_errors[0]["message"]

    def test_complex_assignment_values(self, analyzer):
        """Test runtime checking with complex assignment values."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    list_param = param.List(default=[])
    dict_param = param.Dict(default={})
    number_param = param.Number(default=0, bounds=(0, 10))

instance = TestClass()

# Valid complex assignments
instance.list_param = [1, 2, 3]
instance.dict_param = {"key": "value"}

# Invalid assignments
instance.list_param = "not_list"    # Error: wrong type
instance.dict_param = []            # Error: wrong type
instance.number_param = -5          # Error: bounds violation
"""

        result = analyzer.analyze_file(code_py)

        runtime_errors = [
            e
            for e in result["type_errors"]
            if e["code"].startswith("runtime") or e["code"] == "bounds-violation"
        ]
        assert len(runtime_errors) == 3
