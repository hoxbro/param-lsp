"""Tests for parameter bounds validation functionality."""

from __future__ import annotations


class TestBoundsValidation:
    """Test bounds validation in parameter definitions."""

    def test_valid_bounds_definition(self, analyzer):
        """Test valid bounds definitions don't generate errors."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    int_param = param.Integer(default=5, bounds=(0, 10))
    number_param = param.Number(default=2.5, bounds=(0.0, 5.0))
"""

        result = analyzer.analyze_file(code_py)

        assert len(result["type_errors"]) == 0
        assert "TestClass" in result["param_parameter_bounds"]
        bounds = result["param_parameter_bounds"]["TestClass"]
        assert "int_param" in bounds
        assert "number_param" in bounds

    def test_invalid_bounds_min_greater_than_max(self, analyzer):
        """Test bounds where min >= max generates error."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    invalid_bounds1 = param.Integer(bounds=(10, 5))  # min > max
    invalid_bounds2 = param.Number(bounds=(5.0, 5.0))  # min == max
"""

        result = analyzer.analyze_file(code_py)

        invalid_bounds_errors = [e for e in result["type_errors"] if e["code"] == "invalid-bounds"]
        assert len(invalid_bounds_errors) == 2

        for error in invalid_bounds_errors:
            assert "invalid bounds" in error["message"]
            assert ">=" in error["message"]

    def test_default_value_outside_bounds(self, analyzer):
        """Test default values outside bounds generate errors."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    too_low = param.Integer(default=-5, bounds=(0, 10))
    too_high = param.Integer(default=15, bounds=(0, 10))
    float_too_low = param.Number(default=-1.0, bounds=(0.0, 5.0))
    float_too_high = param.Number(default=6.0, bounds=(0.0, 5.0))
"""

        result = analyzer.analyze_file(code_py)

        bounds_violation_errors = [
            e for e in result["type_errors"] if e["code"] == "default-bounds-violation"
        ]
        assert len(bounds_violation_errors) == 4

        for error in bounds_violation_errors:
            assert "outside bounds" in error["message"]
            assert "[" in error["message"]
            assert "]" in error["message"]

    def test_inclusive_bounds_violations(self, analyzer):
        """Test inclusive_bounds parameter affects bound checking."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    # Exclusive bounds: (0, 5) - 0 and 5 should not be allowed
    exclusive_both = param.Number(default=0.0, bounds=(0, 5), inclusive_bounds=(False, False))
    exclusive_left = param.Number(default=0.0, bounds=(0, 5), inclusive_bounds=(False, True))
    exclusive_right = param.Number(default=5.0, bounds=(0, 5), inclusive_bounds=(True, False))

    # These should be valid
    valid_exclusive = param.Number(default=2.5, bounds=(0, 5), inclusive_bounds=(False, False))
    valid_inclusive_left = param.Number(default=5.0, bounds=(0, 5), inclusive_bounds=(False, True))
    valid_inclusive_right = param.Number(default=0.0, bounds=(0, 5), inclusive_bounds=(True, False))
"""

        result = analyzer.analyze_file(code_py)

        bounds_violation_errors = [
            e for e in result["type_errors"] if e["code"] == "default-bounds-violation"
        ]
        assert len(bounds_violation_errors) == 3  # exclusive_both, exclusive_left, exclusive_right

        # Check notation in error messages
        for error in bounds_violation_errors:
            if "exclusive_both" in error["message"]:
                assert "(0, 5)" in error["message"]  # Both exclusive
            elif "exclusive_left" in error["message"]:
                assert "(0, 5]" in error["message"]  # Left exclusive, right inclusive
            elif "exclusive_right" in error["message"]:
                assert "[0, 5)" in error["message"]  # Left inclusive, right exclusive

    def test_default_inclusive_bounds(self, analyzer):
        """Test that bounds are inclusive by default."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    # Default bounds are inclusive [0, 10]
    at_min = param.Integer(default=0, bounds=(0, 10))
    at_max = param.Integer(default=10, bounds=(0, 10))
"""

        result = analyzer.analyze_file(code_py)

        bounds_violation_errors = [
            e for e in result["type_errors"] if e["code"] == "default-bounds-violation"
        ]
        assert len(bounds_violation_errors) == 0  # Should be valid with inclusive bounds

    def test_bounds_extraction_and_storage(self, analyzer):
        """Test that bounds are correctly extracted and stored."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    simple_bounds = param.Integer(default=5, bounds=(0, 10))
    float_bounds = param.Number(default=2.5, bounds=(1.0, 5.0))
    exclusive_bounds = param.Number(default=2.5, bounds=(0, 5), inclusive_bounds=(False, True))
"""

        result = analyzer.analyze_file(code_py)

        bounds = result["param_parameter_bounds"]["TestClass"]

        # Check simple bounds
        assert "simple_bounds" in bounds
        simple_bounds_data = bounds["simple_bounds"]
        assert len(simple_bounds_data) == 4  # (min, max, left_inclusive, right_inclusive)
        assert simple_bounds_data[0] == 0
        assert simple_bounds_data[1] == 10
        assert simple_bounds_data[2] is True  # Default inclusive
        assert simple_bounds_data[3] is True  # Default inclusive

        # Check exclusive bounds
        assert "exclusive_bounds" in bounds
        exclusive_bounds_data = bounds["exclusive_bounds"]
        assert exclusive_bounds_data[2] is False  # Left exclusive
        assert exclusive_bounds_data[3] is True  # Right inclusive

    def test_negative_bounds(self, analyzer):
        """Test bounds with negative numbers."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    negative_bounds = param.Integer(default=-2, bounds=(-5, 0))
    mixed_bounds = param.Number(default=0.0, bounds=(-10.0, 10.0))
"""

        result = analyzer.analyze_file(code_py)

        assert len(result["type_errors"]) == 0
        bounds = result["param_parameter_bounds"]["TestClass"]
        assert bounds["negative_bounds"][0] == -5
        assert bounds["negative_bounds"][1] == 0

    def test_bounds_with_non_numeric_parameters(self, analyzer):
        """Test that bounds are only checked for numeric parameter types."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    string_param = param.String(default="hello", bounds=("a", "z"))  # Invalid but not our concern
    bool_param = param.Boolean(default=True, bounds=(False, True))   # Invalid but not our concern
    number_param = param.Number(default=15, bounds=(0, 10))          # Should be checked
"""

        result = analyzer.analyze_file(code_py)

        # Only the Number parameter should generate bounds violation
        bounds_violation_errors = [
            e for e in result["type_errors"] if e["code"] == "default-bounds-violation"
        ]
        assert len(bounds_violation_errors) == 1
        assert "number_param" in bounds_violation_errors[0]["message"]

    def test_empty_default_with_bounds_warning(self, analyzer):
        """Test warning for empty default values with bounds specified."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    empty_list_with_bounds = param.List(default=[], bounds=(1, 5))
    empty_tuple_with_bounds = param.Tuple(default=(), bounds=(1, 3))
"""

        result = analyzer.analyze_file(code_py)

        empty_default_warnings = [
            e for e in result["type_errors"] if e["code"] == "empty-default-with-bounds"
        ]
        assert len(empty_default_warnings) == 2

        for warning in empty_default_warnings:
            assert warning["severity"] == "warning"
            assert "empty default but bounds specified" in warning["message"]
