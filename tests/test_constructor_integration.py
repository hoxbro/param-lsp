"""Integration tests for constructor parameter validation with existing features."""

from __future__ import annotations

from src.param_lsp.analyzer import ParamAnalyzer


class TestConstructorIntegration:
    """Test integration between constructor validation and existing LSP features."""

    def test_constructor_validation_with_existing_runtime_checks(self):
        """Test that constructor validation works alongside existing runtime assignment checks."""
        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer()
    y = param.String()

# Constructor errors
instance1 = P(x="bad")  # Constructor type error

# Runtime assignment errors
instance2 = P(x=5)
instance2.x = "also_bad"  # Runtime assignment error

# Mixed scenario
instance3 = P(x=10, y=20)  # Constructor error on y
instance3.x = "runtime_bad"  # Runtime error on x
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 4

        error_codes = [error["code"] for error in errors]
        assert "constructor-type-mismatch" in error_codes
        assert "runtime-type-mismatch" in error_codes

        error_messages = [error["message"] for error in errors]
        assert any("constructor" in msg for msg in error_messages)
        assert any("Cannot assign" in msg and "constructor" not in msg for msg in error_messages)

    def test_constructor_validation_with_inheritance_and_runtime(self):
        """Test constructor validation with inheritance and runtime assignments."""
        code_py = """\
import param

class Base(param.Parameterized):
    base_x = param.Integer()

class Child(Base):
    child_y = param.String()

# Constructor errors on inherited and own parameters
child = Child(base_x="bad", child_y=123)

# Runtime errors on inherited and own parameters
child2 = Child(base_x=5, child_y="good")
child2.base_x = "runtime_bad"
child2.child_y = 456
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 4

        # Check mix of constructor and runtime errors
        constructor_errors = [e for e in errors if "constructor" in e["message"]]
        runtime_errors = [e for e in errors if "constructor" not in e["message"]]

        assert len(constructor_errors) == 2
        assert len(runtime_errors) == 2

    def test_constructor_validation_with_bounds_and_defaults(self):
        """Test constructor validation works with parameter bounds and default values."""
        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=5, bounds=(0, 10))  # Default in bounds
    y = param.Number(default=15, bounds=(0, 10))  # Default out of bounds - should error
    z = param.String(default="good")

# Constructor calls
P(x=8)           # Valid - within bounds
P(x=15)          # Invalid - outside bounds
P(y=5)           # Valid - within bounds despite bad default
P(z=123)         # Invalid - wrong type
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        # Should have errors for:
        # 1. Default value bounds violation (y=15 with bounds (0,10))
        # 2. Constructor bounds violation (x=15)
        # 3. Constructor type mismatch (z=123)

        assert len(errors) >= 3

        error_messages = [error["message"] for error in errors]
        assert any("Default value 15" in msg and "bounds" in msg for msg in error_messages)
        assert any(
            "Value 15 for parameter 'x'" in msg and "constructor" in msg for msg in error_messages
        )
        assert any(
            "Cannot assign int to parameter 'z'" in msg and "constructor" in msg
            for msg in error_messages
        )

    def test_constructor_validation_with_doc_strings(self):
        """Test that constructor validation works with parameter documentation."""
        code_py = """\
import param

class DocumentedClass(param.Parameterized):
    x = param.Integer(doc="An integer parameter")
    y = param.String(doc="A string parameter with documentation")
    z = param.Boolean(doc="Boolean flag")

# Valid constructor calls should not interfere with documentation
DocumentedClass(x=42, y="test", z=True)

# Invalid constructor calls should still error despite documentation
DocumentedClass(x="bad", y=123, z="false")
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        # Should have 3 constructor errors
        assert len(errors) == 3

        # Verify documentation is still extracted properly
        param_docs = result.get("param_parameter_docs", {})
        assert "DocumentedClass" in param_docs
        assert param_docs["DocumentedClass"]["x"] == "An integer parameter"
        assert param_docs["DocumentedClass"]["y"] == "A string parameter with documentation"
        assert param_docs["DocumentedClass"]["z"] == "Boolean flag"

    def test_constructor_validation_with_import_resolution(self):
        """Test constructor validation with different import styles."""
        code_py = """
# Test various import styles
import param
import param as p
from param import Parameterized, Integer, String

class Style1(param.Parameterized):
    x = param.Integer()

class Style2(p.Parameterized):
    x = p.Integer()

class Style3(Parameterized):
    x = Integer()

# All should detect constructor errors
Style1(x="bad")
Style2(x="bad")
Style3(x="bad")

# All should work with valid values
Style1(x=1)
Style2(x=2)
Style3(x=3)
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        # Should have exactly 3 constructor errors (one for each bad call)
        assert len(errors) == 3

        error_messages = [error["message"] for error in errors]
        assert any("Style1() constructor" in msg for msg in error_messages)
        assert any("Style2() constructor" in msg for msg in error_messages)
        assert any("Style3() constructor" in msg for msg in error_messages)

    def test_constructor_validation_comprehensive_workflow(self):
        """Test complete workflow with all validation features enabled."""
        code_py = """\
import param

class CompleteExample(param.Parameterized):
    # Various parameter types with different constraints
    id = param.Integer(doc="Unique identifier", bounds=(1, 1000))
    name = param.String(doc="Display name")
    active = param.Boolean(doc="Whether item is active", default=True)
    score = param.Number(doc="Performance score", bounds=(0, 100), inclusive_bounds=(True, True))
    tags = param.List(doc="Associated tags")
    metadata = param.Dict(doc="Additional metadata")

# Valid usage - should not error
good_instance = CompleteExample(
    id=42,
    name="test",
    active=True,
    score=85.5,
    tags=["important", "test"],
    metadata={"created": "2023-01-01"}
)

# Constructor errors - multiple types
bad_constructor = CompleteExample(
    id="not_int",      # Type error
    name=123,          # Type error
    active="yes",      # Boolean type error
    score=150,         # Bounds error
    tags="not_list",   # Type error
    metadata=[1,2,3]   # Type error
)

# Runtime assignment errors
good_instance.id = "runtime_bad"      # Runtime type error
good_instance.score = 200             # Runtime bounds error
good_instance.active = "runtime_bool" # Runtime boolean error

# Mixed constructor and runtime in inheritance
class ExtendedExample(CompleteExample):
    priority = param.Integer(bounds=(1, 5))

extended = ExtendedExample(
    id=1, name="base", score=50, tags=[], metadata={},
    priority="bad"  # Constructor error on new parameter
)
extended.priority = 10  # Runtime bounds error on new parameter
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        # Should have many errors from different validation types
        assert len(errors) >= 10

        # Verify we have different error codes
        error_codes = [error["code"] for error in errors]
        assert "constructor-type-mismatch" in error_codes
        assert "constructor-bounds-violation" in error_codes
        assert "constructor-boolean-type-mismatch" in error_codes
        assert "runtime-type-mismatch" in error_codes
        assert "bounds-violation" in error_codes

        # Verify parameter analysis still works
        param_classes = result.get("param_classes", set())
        assert "CompleteExample" in param_classes
        assert "ExtendedExample" in param_classes

        param_docs = result.get("param_parameter_docs", {})
        assert len(param_docs.get("CompleteExample", {})) == 6  # All parameters documented

    def test_constructor_validation_error_recovery(self):
        """Test that constructor validation continues after errors."""
        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer()

# Multiple constructor calls with errors
P(x="error1")
P(x="error2")
P(x="error3")

# Should still validate later valid calls
P(x=42)

# And catch later errors too
P(x="error4")
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        # Should catch all 4 errors and not stop after first
        assert len(errors) == 4

        # All should be constructor errors
        for error in errors:
            assert "constructor" in error["message"]
            assert error["code"] == "constructor-type-mismatch"
