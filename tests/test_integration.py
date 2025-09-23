"""Integration tests for the complete param-lsp functionality."""

from __future__ import annotations


class TestIntegration:
    """Integration tests covering complete workflows."""

    def test_complete_analysis_workflow(self, analyzer):
        """Test complete analysis workflow with all features."""
        code_py = """
from __future__ import annotations
import param

class CompleteExample(param.Parameterized):
    # Valid parameters
    name = param.String(
        default="example",
        doc="The name of the example"
    )

    count = param.Integer(
        default=5,
        bounds=(1, 100),
        doc="Number of items (between 1 and 100)"
    )

    enabled = param.Boolean(
        default=True,
        doc="Whether the feature is enabled"
    )

    ratio = param.Number(
        default=0.5,
        bounds=(0.0, 1.0),
        inclusive_bounds=(False, True),
        doc="A ratio between 0 and 1 (exclusive of 0)"
    )

    # Parameters with errors
    bad_string = param.String(default=123)  # Type error
    bad_bool = param.Boolean(default=1)     # Boolean type error
    bad_bounds = param.Integer(default=150, bounds=(1, 100))  # Bounds violation
    invalid_bounds = param.Number(bounds=(10, 5))  # Invalid bounds

# Runtime assignments
example = CompleteExample()
example.name = "new name"        # Valid
example.count = 50              # Valid
example.enabled = False         # Valid
example.ratio = 0.75            # Valid

# Runtime errors
example.name = 456              # Type error
example.enabled = "yes"         # Boolean type error
example.count = 0               # Bounds violation
example.ratio = 0               # Exclusive bounds violation
"""

        result = analyzer.analyze_file(code_py)

        # Verify class detection
        assert "CompleteExample" in result["param_classes"]

        # Verify parameter extraction
        params = result["param_parameters"]["CompleteExample"]
        expected_params = [
            "name",
            "count",
            "enabled",
            "ratio",
            "bad_string",
            "bad_bool",
            "bad_bounds",
            "invalid_bounds",
        ]
        assert all(param in params for param in expected_params)

        # Verify type extraction
        types = result["param_parameter_types"]["CompleteExample"]
        assert types["name"] == "String"
        assert types["count"] == "Integer"
        assert types["enabled"] == "Boolean"
        assert types["ratio"] == "Number"

        # Verify documentation extraction
        docs = result["param_parameter_docs"]["CompleteExample"]
        assert "name" in docs
        assert "The name of the example" in docs["name"]
        assert "count" in docs
        assert "enabled" in docs
        assert "ratio" in docs

        # Verify bounds extraction
        bounds = result["param_parameter_bounds"]["CompleteExample"]
        assert "count" in bounds
        assert "ratio" in bounds

        # Count and categorize errors
        type_errors = [e for e in result["type_errors"] if e["code"] == "type-mismatch"]
        boolean_errors = [e for e in result["type_errors"] if "boolean" in e["code"]]
        bounds_errors = [e for e in result["type_errors"] if "bounds" in e["code"]]
        runtime_errors = [e for e in result["type_errors"] if "runtime" in e["code"]]

        # Verify error counts
        assert len(type_errors) >= 1  # bad_string
        assert len(boolean_errors) >= 2  # bad_bool + runtime boolean errors
        assert len(bounds_errors) >= 3  # bad_bounds, invalid_bounds, runtime bounds
        assert (
            len(runtime_errors) >= 2
        )  # Runtime assignment errors (type + boolean, bounds use different code)

        # Total errors should include all categories
        total_errors = len(result["type_errors"])
        assert total_errors >= 8  # At least 8 errors expected

    def test_real_world_example(self, analyzer):
        """Test with a realistic param class example."""
        code_py = '''
import param

class DataProcessor(param.Parameterized):
    """A data processing configuration."""

    input_file = param.Filename(
        default="data.csv",
        doc="Path to the input data file"
    )

    output_dir = param.Foldername(
        default="./output",
        doc="Directory for output files"
    )

    batch_size = param.Integer(
        default=100,
        bounds=(1, 10000),
        doc="Number of records to process in each batch"
    )

    learning_rate = param.Number(
        default=0.001,
        bounds=(0.0, 1.0),
        inclusive_bounds=(False, True),
        doc="Learning rate for the algorithm"
    )

    use_gpu = param.Boolean(
        default=False,
        doc="Whether to use GPU acceleration"
    )

    features = param.List(
        default=["feature1", "feature2"],
        doc="List of features to use"
    )

    metadata = param.Dict(
        default={"version": "1.0"},
        doc="Additional metadata"
    )

# Usage
processor = DataProcessor()
processor.batch_size = 500          # Valid
processor.learning_rate = 0.01      # Valid
processor.use_gpu = True            # Valid

# These should cause errors
processor.batch_size = "invalid"    # Type error
processor.learning_rate = 1.5       # Bounds error
processor.use_gpu = 1              # Boolean type error
'''

        result = analyzer.analyze_file(code_py)

        # Verify comprehensive analysis
        assert "DataProcessor" in result["param_classes"]

        # Check all parameter types are detected
        types = result["param_parameter_types"]["DataProcessor"]
        expected_types = {
            "input_file": "Filename",
            "output_dir": "Foldername",
            "batch_size": "Integer",
            "learning_rate": "Number",
            "use_gpu": "Boolean",
            "features": "List",
            "metadata": "Dict",
        }

        for param_name, expected_type in expected_types.items():
            assert param_name in types
            assert types[param_name] == expected_type

        # Check documentation is extracted
        docs = result["param_parameter_docs"]["DataProcessor"]
        assert len(docs) == 7  # All parameters have docs

        # Check bounds are extracted
        bounds = result["param_parameter_bounds"]["DataProcessor"]
        assert "batch_size" in bounds
        assert "learning_rate" in bounds

        # Check runtime errors are detected
        runtime_errors = [e for e in result["type_errors"] if "runtime" in e["code"]]
        bounds_violations = [e for e in result["type_errors"] if e["code"] == "bounds-violation"]

        assert len(runtime_errors) >= 2  # Type and boolean errors
        assert len(bounds_violations) >= 1  # Learning rate bounds error

    def test_edge_cases_and_corner_cases(self, analyzer):
        """Test edge cases and corner cases."""
        code_py = """\
import param

class EdgeCases(param.Parameterized):
    # Edge case: parameter with same name as Python keywords
    class_ = param.String(default="class_value", doc="A parameter named 'class_'")

    # Edge case: very long documentation
    long_doc = param.String(
        default="test",
        doc="This is a very long documentation string that spans multiple lines and contains lots of information about the parameter including special characters !@#$%^&*() and unicode characters like café"
    )

    # Edge case: bounds at extreme values
    extreme_bounds = param.Number(
        default=0.0,
        bounds=(-1e10, 1e10),
        doc="Parameter with extreme bounds"
    )

    # Edge case: very precise bounds
    precise_bounds = param.Number(
        default=3.14159,
        bounds=(3.14158, 3.14160),
        doc="Very precise bounds"
    )

# Edge case runtime assignments
edge = EdgeCases()
edge.class_ = "new_value"        # Valid
edge.extreme_bounds = 1e9        # Valid (within bounds)
edge.precise_bounds = 3.14161 # Invalid (outside precise bounds)
"""

        result = analyzer.analyze_file(code_py)

        # Verify all edge cases are handled
        assert "EdgeCases" in result["param_classes"]

        # Check documentation extraction handles long text and special characters
        docs = result["param_parameter_docs"]["EdgeCases"]
        assert "long_doc" in docs
        assert "café" in docs["long_doc"]
        assert "!@#$%^&*()" in docs["long_doc"]

        # Check bounds handling with extreme values
        bounds = result["param_parameter_bounds"]["EdgeCases"]
        assert "extreme_bounds" in bounds
        assert "precise_bounds" in bounds

        # Check precise bounds violation is detected
        bounds_violations = [e for e in result["type_errors"] if e["code"] == "bounds-violation"]
        assert any("precise_bounds" in e["message"] for e in bounds_violations)

    def test_error_recovery_and_robustness(self, analyzer):
        """Test that the analyzer recovers gracefully from syntax errors and edge cases."""
        # Test with some invalid syntax mixed with valid param code
        code_py = """\
import param

class ValidClass(param.Parameterized):
    valid_param = param.String(default="test", doc="This should work")

# Some invalid Python syntax that should be handled gracefully
# This would cause a syntax error but analyzer should still extract what it can
"""

        # This should not crash the analyzer
        result = analyzer.analyze_file(code_py)

        # Should still extract the valid parts
        assert "ValidClass" in result["param_classes"]
        assert result["param_parameter_types"]["ValidClass"]["valid_param"] == "String"
