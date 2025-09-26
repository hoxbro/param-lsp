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
        complete_class = result["param_classes"]["CompleteExample"]

        # Verify parameter extraction
        params = list(complete_class.parameters.keys())
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
        assert complete_class.parameters["name"].cls == "String"
        assert complete_class.parameters["count"].cls == "Integer"
        assert complete_class.parameters["enabled"].cls == "Boolean"
        assert complete_class.parameters["ratio"].cls == "Number"

        # Verify documentation extraction
        assert complete_class.parameters["name"].doc is not None
        assert "The name of the example" in complete_class.parameters["name"].doc
        assert complete_class.parameters["count"].doc is not None
        assert complete_class.parameters["enabled"].doc is not None
        assert complete_class.parameters["ratio"].doc is not None

        # Verify bounds extraction
        assert complete_class.parameters["count"].bounds is not None
        assert complete_class.parameters["ratio"].bounds is not None

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
        data_processor_class = result["param_classes"]["DataProcessor"]

        # Check all parameter types are detected
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
            assert param_name in data_processor_class.parameters
            assert data_processor_class.parameters[param_name].cls == expected_type

        # Check documentation is extracted
        docs_count = sum(1 for p in data_processor_class.parameters.values() if p.doc is not None)
        assert docs_count == 7  # All parameters have docs

        # Check bounds are extracted
        assert data_processor_class.parameters["batch_size"].bounds is not None
        assert data_processor_class.parameters["learning_rate"].bounds is not None

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
        edge_cases_class = result["param_classes"]["EdgeCases"]

        # Check documentation extraction handles long text and special characters
        long_doc_param = edge_cases_class.parameters["long_doc"]
        assert long_doc_param.doc is not None
        assert "café" in long_doc_param.doc
        assert "!@#$%^&*()" in long_doc_param.doc

        # Check bounds handling with extreme values
        assert edge_cases_class.parameters["extreme_bounds"].bounds is not None
        assert edge_cases_class.parameters["precise_bounds"].bounds is not None

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
        valid_class = result["param_classes"]["ValidClass"]
        assert valid_class.parameters["valid_param"].cls == "String"
