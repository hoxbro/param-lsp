"""Tests for parameter documentation extraction functionality."""

from __future__ import annotations


class TestDocExtraction:
    """Test parameter documentation extraction and storage."""

    def test_doc_parameter_extraction(self, analyzer):
        """Test that doc parameters are correctly extracted."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    documented_param = param.String(
        default="hello",
        doc="This is a string parameter with documentation"
    )

    undocumented_param = param.Integer(default=5)

    multiline_doc = param.Boolean(
        default=True,
        doc="This is a boolean parameter with a longer documentation string"
    )
"""

        result = analyzer.analyze_file(code_py)

        param_classes = result["param_classes"]
        assert "TestClass" in param_classes
        test_class = param_classes["TestClass"]

        assert "documented_param" in test_class.parameters
        assert (
            test_class.parameters["documented_param"].doc
            == "This is a string parameter with documentation"
        )

        assert "undocumented_param" in test_class.parameters
        assert test_class.parameters["undocumented_param"].doc is None  # No doc parameter

        assert "multiline_doc" in test_class.parameters
        assert (
            test_class.parameters["multiline_doc"].doc
            == "This is a boolean parameter with a longer documentation string"
        )

    def test_doc_with_different_quote_types(self, analyzer):
        """Test doc parameter extraction with different quote types."""
        code_py = '''
import param

class TestClass(param.Parameterized):
    single_quotes = param.String(default="test", doc='Single quoted documentation')
    double_quotes = param.String(default="test", doc="Double quoted documentation")
    triple_quotes = param.String(default="test", doc="""Triple quoted documentation""")
'''

        result = analyzer.analyze_file(code_py)

        test_class = result["param_classes"]["TestClass"]

        assert test_class.parameters["single_quotes"].doc == "Single quoted documentation"
        assert test_class.parameters["double_quotes"].doc == "Double quoted documentation"
        assert test_class.parameters["triple_quotes"].doc == "Triple quoted documentation"

    def test_doc_with_special_characters(self, analyzer):
        """Test doc parameter extraction with special characters."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    special_chars = param.String(
        default="test",
        doc="Documentation with special chars: !@#$%^&*()_+-={}[]"
    )

    unicode_chars = param.String(
        default="test",
        doc="Documentation with unicode: café, naïve, résumé"
    )
"""

        result = analyzer.analyze_file(code_py)

        test_class = result["param_classes"]["TestClass"]

        assert "special_chars" in test_class.parameters
        assert "!@#$%^&*()_+-=" in test_class.parameters["special_chars"].doc

        assert "unicode_chars" in test_class.parameters
        assert "café" in test_class.parameters["unicode_chars"].doc

    def test_doc_parameter_order_independence(self, analyzer):
        """Test that doc parameter works regardless of parameter order."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    doc_first = param.String(
        doc="Documentation comes first",
        default="hello"
    )

    doc_middle = param.Integer(
        default=5,
        doc="Documentation in the middle",
        bounds=(0, 10)
    )

    doc_last = param.Boolean(
        default=True,
        bounds=(False, True),
        doc="Documentation comes last"
    )
"""

        result = analyzer.analyze_file(code_py)

        test_class = result["param_classes"]["TestClass"]

        assert test_class.parameters["doc_first"].doc == "Documentation comes first"
        assert test_class.parameters["doc_middle"].doc == "Documentation in the middle"
        assert test_class.parameters["doc_last"].doc == "Documentation comes last"

    def test_doc_with_bounds_and_other_parameters(self, analyzer):
        """Test doc extraction alongside other parameter attributes."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    comprehensive_param = param.Number(
        default=2.5,
        bounds=(0.0, 10.0),
        inclusive_bounds=(True, False),
        doc="A comprehensive parameter with bounds and documentation",
        label="Comprehensive Parameter",
        precedence=1
    )
"""

        result = analyzer.analyze_file(code_py)

        # Check that doc is extracted
        test_class = result["param_classes"]["TestClass"]
        assert "comprehensive_param" in test_class.parameters
        assert (
            test_class.parameters["comprehensive_param"].doc
            == "A comprehensive parameter with bounds and documentation"
        )

        # Check that other attributes are also extracted
        assert test_class.parameters["comprehensive_param"].bounds is not None

        assert test_class.parameters["comprehensive_param"].cls == "Number"

    def test_empty_doc_parameter(self, analyzer):
        """Test handling of empty doc parameters."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    empty_doc = param.String(default="test", doc="")
    none_doc = param.String(default="test", doc=None)  # This would be a runtime error, but test parsing
"""

        result = analyzer.analyze_file(code_py)

        test_class = result["param_classes"]["TestClass"]

        # Empty string doc should still be recorded
        assert "empty_doc" in test_class.parameters
        assert test_class.parameters["empty_doc"].doc == ""

        # None doc would not be extracted as it's not a string literal
        assert "none_doc" in test_class.parameters
        assert test_class.parameters["none_doc"].doc is None

    def test_doc_with_different_import_styles(self, analyzer):
        """Test doc extraction with different import styles."""
        code_py = """\
import param as p
from param import String, Integer

class TestClass(p.Parameterized):
    param_alias = p.String(default="test", doc="Using param alias")
    direct_import = String(default="test", doc="Using direct import")
    no_doc = Integer(default=5)
"""

        result = analyzer.analyze_file(code_py)

        test_class = result["param_classes"]["TestClass"]

        assert "param_alias" in test_class.parameters
        assert test_class.parameters["param_alias"].doc == "Using param alias"

        assert "direct_import" in test_class.parameters
        assert test_class.parameters["direct_import"].doc == "Using direct import"

        assert "no_doc" in test_class.parameters
        assert test_class.parameters["no_doc"].doc is None

    def test_multiple_classes_doc_extraction(self, analyzer):
        """Test doc extraction across multiple param classes."""
        code_py = """\
import param

class ClassA(param.Parameterized):
    param_a = param.String(default="a", doc="Documentation for class A")

class ClassB(param.Parameterized):
    param_b = param.Integer(default=1, doc="Documentation for class B")

class ClassC(param.Parameterized):
    param_c = param.Boolean(default=True)  # No doc
"""

        result = analyzer.analyze_file(code_py)

        param_classes = result["param_classes"]

        assert "ClassA" in param_classes
        assert param_classes["ClassA"].parameters["param_a"].doc == "Documentation for class A"

        assert "ClassB" in param_classes
        assert param_classes["ClassB"].parameters["param_b"].doc == "Documentation for class B"

        assert "ClassC" in param_classes
        class_c_docs = [p for p in param_classes["ClassC"].parameters.values() if p.doc]
        assert len(class_c_docs) == 0  # No documented parameters

    def test_doc_parameter_with_complex_expressions(self, analyzer):
        """Test that only simple string literals are extracted for doc."""
        code_py = """\
import param

DOC_CONSTANT = "Constant documentation"

class TestClass(param.Parameterized):
    simple_doc = param.String(default="test", doc="Simple documentation")

    # These should not be extracted as they're not simple string literals
    variable_doc = param.String(default="test", doc=DOC_CONSTANT)
    expression_doc = param.String(default="test", doc="Part 1" + " Part 2")
    method_doc = param.String(default="test", doc=str("method call"))
"""

        result = analyzer.analyze_file(code_py)

        test_class = result["param_classes"]["TestClass"]

        # Only simple string literal should be extracted
        assert "simple_doc" in test_class.parameters
        assert test_class.parameters["simple_doc"].doc == "Simple documentation"

        # Complex expressions should not be extracted (doc should be None)
        assert "variable_doc" in test_class.parameters
        assert test_class.parameters["variable_doc"].doc is None
        assert "expression_doc" in test_class.parameters
        assert test_class.parameters["expression_doc"].doc is None
        assert "method_doc" in test_class.parameters
        assert test_class.parameters["method_doc"].doc is None

    def test_doc_storage_structure(self, analyzer):
        """Test the structure of doc storage in analysis results."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    param1 = param.String(default="test", doc="Doc 1")
    param2 = param.Integer(default=5, doc="Doc 2")
"""

        result = analyzer.analyze_file(code_py)

        # Check that param_classes is in the result
        assert "param_classes" in result

        # Check structure: class_name -> ParameterizedInfo with parameters
        param_classes = result["param_classes"]
        assert isinstance(param_classes, dict)
        assert "TestClass" in param_classes
        test_class = param_classes["TestClass"]

        # Check that we have 2 documented parameters
        documented_params = [p for p in test_class.parameters.values() if p.doc]
        assert len(documented_params) == 2
        assert all(isinstance(p.doc, str) for p in documented_params)
