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

        boolean_errors = [e for e in result["type_errors"] if e["code"] == "runtime-type-mismatch"]
        assert len(boolean_errors) == 4

        for error in boolean_errors:
            assert "of type Boolean" in error["message"]
            assert "expects bool" in error["message"]

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

    def test_runtime_assignment_with_duplicate_class_names(self, analyzer):
        """Test runtime assignments with duplicate class names (like Panel tests)."""
        code_py = """\
import param

def test_number():
    class Test(param.Parameterized):
        a = param.Number(default=1.0)

    test = Test()
    test.a = 5.0  # Valid
    test.a = "invalid"  # Error: wrong type

def test_boolean():
    class Test(param.Parameterized):
        a = param.Boolean(default=False)

    test = Test()
    test.a = True  # Valid
    test.a = "invalid"  # Error: wrong type
"""

        result = analyzer.analyze_file(code_py)

        # Should detect 2 type errors (one in each function)
        runtime_errors = [e for e in result["type_errors"] if e["code"] == "runtime-type-mismatch"]
        assert len(runtime_errors) == 2

        # Verify errors are in the correct functions
        error_lines = [e["line"] for e in runtime_errors]
        # Line 9 is in test_number, line 17 is in test_boolean
        assert 9 in error_lines or 8 in error_lines  # "invalid" assignment in test_number
        assert 17 in error_lines or 16 in error_lines  # "invalid" assignment in test_boolean

    def test_non_param_objects_with_matching_attribute_names(self, analyzer):
        """Test that assignments to non-Param objects with matching attribute names are ignored.

        This is a regression test for false positives where pandas DataFrames,
        Jupyter config objects, or other non-Param objects have attributes with the
        same names as Param parameters (e.g., 'name', 'port', 'value').
        """
        code_py = """\
import param

class Widget(param.Parameterized):
    name = param.String(default="widget")
    port = param.Integer(default=8080)

# Simulate a pandas-like object with index.name attribute
class MockIndex:
    name = None

class MockDataFrame:
    def __init__(self):
        self.index = MockIndex()

# Simulate a Jupyter-like config object
class MockServerApp:
    port = 0

class MockConfig:
    ServerApp = MockServerApp()

# These should NOT generate errors (not Param objects)
df = MockDataFrame()
df.index.name = None  # NOT a Param parameter assignment

c = MockConfig()
c.ServerApp.port = 8888  # NOT a Param parameter assignment

# This SHOULD generate an error (is a Param object)
widget = Widget()
widget.name = 123  # Error: wrong type
"""

        result = analyzer.analyze_file(code_py)

        runtime_errors = [e for e in result["type_errors"] if e["code"] == "runtime-type-mismatch"]
        # Should only have 1 error (widget.name = 123), not the pandas/config ones
        assert len(runtime_errors) == 1
        assert (
            "widget" not in runtime_errors[0]["message"].lower()
            or "name" in runtime_errors[0]["message"]
        )

    def test_self_assignment_to_non_parameter_attribute(self, analyzer):
        """Test that self.attribute assignments to non-parameters don't generate false positives.

        This is a regression test for the bug where `self.style = None` inside a class's
        __init__ method was incorrectly flagged as a parameter type error, even though
        the class doesn't have a `style` parameter. The code was incorrectly matching
        against unrelated external classes that happen to have a parameter with the same name.
        """
        code_py = """\
import param

class ClassWithStyleParam(param.Parameterized):
    style = param.Dict(default={})

class ClassWithoutStyleParam(param.Parameterized):
    name = param.String(default="test")
    value = param.Integer(default=0)

    def __init__(self, **params):
        # These should NOT be flagged as errors
        # because style and _widgets are not parameters of this class
        self.style = None  # Just a regular instance attribute
        self._widgets = []  # Just a regular instance attribute
        self._computed_styler = {}  # Just a regular instance attribute
        super().__init__(**params)

        # This SHOULD generate an error (is a parameter)
        self.name = 123  # Error: wrong type for parameter

# This SHOULD also generate an error (is a parameter on ClassWithStyleParam)
instance = ClassWithStyleParam()
instance.style = "wrong"  # Error: wrong type for parameter
"""

        result = analyzer.analyze_file(code_py)

        runtime_errors = [e for e in result["type_errors"] if e["code"] == "runtime-type-mismatch"]
        # Should have 2 errors:
        # 1. self.name = 123 (wrong type for parameter)
        # 2. instance.style = "wrong" (wrong type for parameter)
        # Should NOT have errors for self.style, self._widgets, or self._computed_styler
        assert len(runtime_errors) == 2

        # Verify the errors are for the right lines
        error_lines = {e["line"] for e in runtime_errors}
        assert 18 in error_lines  # self.name = 123
        assert 22 in error_lines  # instance.style = "wrong"

        # Verify no errors for the non-parameter attributes
        for error in runtime_errors:
            assert "style = None" not in error["message"]
            assert "_widgets" not in error["message"]
            assert "_computed_styler" not in error["message"]
