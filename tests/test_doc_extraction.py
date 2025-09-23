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

        assert "TestClass" in result["param_parameter_docs"]
        docs = result["param_parameter_docs"]["TestClass"]

        assert "documented_param" in docs
        assert docs["documented_param"] == "This is a string parameter with documentation"

        assert "undocumented_param" not in docs  # No doc parameter

        assert "multiline_doc" in docs
        assert (
            docs["multiline_doc"]
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

        docs = result["param_parameter_docs"]["TestClass"]

        assert docs["single_quotes"] == "Single quoted documentation"
        assert docs["double_quotes"] == "Double quoted documentation"
        assert docs["triple_quotes"] == "Triple quoted documentation"

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

        docs = result["param_parameter_docs"]["TestClass"]

        assert "special_chars" in docs
        assert "!@#$%^&*()_+-=" in docs["special_chars"]

        assert "unicode_chars" in docs
        assert "café" in docs["unicode_chars"]

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

        docs = result["param_parameter_docs"]["TestClass"]

        assert docs["doc_first"] == "Documentation comes first"
        assert docs["doc_middle"] == "Documentation in the middle"
        assert docs["doc_last"] == "Documentation comes last"

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
        docs = result["param_parameter_docs"]["TestClass"]
        assert "comprehensive_param" in docs
        assert (
            docs["comprehensive_param"]
            == "A comprehensive parameter with bounds and documentation"
        )

        # Check that other attributes are also extracted
        bounds = result["param_parameter_bounds"]["TestClass"]
        assert "comprehensive_param" in bounds

        types = result["param_parameter_types"]["TestClass"]
        assert types["comprehensive_param"] == "Number"

    def test_empty_doc_parameter(self, analyzer):
        """Test handling of empty doc parameters."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    empty_doc = param.String(default="test", doc="")
    none_doc = param.String(default="test", doc=None)  # This would be a runtime error, but test parsing
"""

        result = analyzer.analyze_file(code_py)

        docs = result["param_parameter_docs"]["TestClass"]

        # Empty string doc should still be recorded
        assert "empty_doc" in docs
        assert docs["empty_doc"] == ""

        # None doc would not be extracted as it's not a string literal
        assert "none_doc" not in docs

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

        docs = result["param_parameter_docs"]["TestClass"]

        assert "param_alias" in docs
        assert docs["param_alias"] == "Using param alias"

        assert "direct_import" in docs
        assert docs["direct_import"] == "Using direct import"

        assert "no_doc" not in docs

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

        docs = result["param_parameter_docs"]

        assert "ClassA" in docs
        assert docs["ClassA"]["param_a"] == "Documentation for class A"

        assert "ClassB" in docs
        assert docs["ClassB"]["param_b"] == "Documentation for class B"

        assert "ClassC" in docs
        assert len(docs["ClassC"]) == 0  # No documented parameters

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

        docs = result["param_parameter_docs"]["TestClass"]

        # Only simple string literal should be extracted
        assert "simple_doc" in docs
        assert docs["simple_doc"] == "Simple documentation"

        # Complex expressions should not be extracted
        assert "variable_doc" not in docs
        assert "expression_doc" not in docs
        assert "method_doc" not in docs

    def test_doc_storage_structure(self, analyzer):
        """Test the structure of doc storage in analysis results."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    param1 = param.String(default="test", doc="Doc 1")
    param2 = param.Integer(default=5, doc="Doc 2")
"""

        result = analyzer.analyze_file(code_py)

        # Check that param_parameter_docs is in the result
        assert "param_parameter_docs" in result

        # Check structure: class_name -> {param_name: doc_string}
        docs = result["param_parameter_docs"]
        assert isinstance(docs, dict)
        assert "TestClass" in docs
        assert isinstance(docs["TestClass"], dict)

        class_docs = docs["TestClass"]
        assert len(class_docs) == 2
        assert all(
            isinstance(key, str) and isinstance(value, str) for key, value in class_docs.items()
        )
