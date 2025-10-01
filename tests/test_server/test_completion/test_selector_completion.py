"""Test Selector parameter completion functionality."""

from __future__ import annotations

from lsprotocol.types import Position

from param_lsp.server import ParamLanguageServer


class TestSelectorCompletion:
    """Test Selector parameter completion."""

    def test_selector_parameter_completion(self):
        """Test basic Selector parameter completion functionality."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class VideoPlayer(param.Parameterized):
    volume = param.Number(
        default=0.5, bounds=(0.0, 1.0), doc="Audio volume level from 0.0 (mute) to 1.0 (maximum)"
    )

    quality = param.Selector(
        default="720p", objects=["480p", "720p", "1080p", "4K"], doc="Video quality setting"
    )

# Test constructor completion
VideoPlayer("""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion at end of VideoPlayer(
        position = Position(line=12, character=12)  # After VideoPlayer(
        completions = server._get_constructor_parameter_completions(
            "file:///test.py", "VideoPlayer(", position
        )

        # Should have completions for both volume and quality parameters
        assert len(completions) == 2, f"Expected 2 completions, got {len(completions)}"

        completion_labels = [item.label for item in completions]
        completion_inserts = [item.insert_text for item in completions]

        # Check that we get parameter assignments
        assert "volume=0.5" in completion_labels, "Should suggest 'volume=0.5' with default value"
        assert 'quality="720p"' in completion_labels, (
            "Should suggest 'quality=\"720p\"' with quoted string value"
        )
        assert "volume=0.5" in completion_inserts, "Should insert 'volume=0.5'"
        assert 'quality="720p"' in completion_inserts, "Should insert quoted string assignment"

    def test_selector_parameter_hover(self):
        """Test hover information for Selector parameter."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class VideoPlayer(param.Parameterized):
    volume = param.Number(
        default=0.5, bounds=(0.0, 1.0), doc="Audio volume level from 0.0 (mute) to 1.0 (maximum)"
    )

    quality = param.Selector(
        default="720p", objects=["480p", "720p", "1080p", "4K"], doc="Video quality setting"
    )
"""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test hover for quality parameter
        hover_info = server._get_hover_info("file:///test.py", "quality", "quality")

        assert hover_info is not None, "Should have hover info for quality parameter"
        assert "Selector Parameter 'quality'" in hover_info, "Should show parameter type and name"
        assert "Video quality setting" in hover_info, "Should include parameter documentation"
        assert "Allowed objects:" in hover_info, "Should show allowed objects"

    def test_selector_parameter_analysis(self):
        """Test that Selector parameters are properly analyzed and detected."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class TestClass(param.Parameterized):
    mode = param.Selector(default="auto", objects=["auto", "manual"], doc="Operation mode")
    threshold = param.Number(default=0.5)
"""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Access analysis results from analyzer
        result = server.analyzer.param_classes

        # Verify that both parameters are detected
        assert "TestClass" in result, "Should detect TestClass"
        test_class = result["TestClass"]

        assert "mode" in test_class.parameters, "Should detect mode parameter"
        assert "threshold" in test_class.parameters, "Should detect threshold parameter"

        # Verify parameter types
        mode_param = test_class.get_parameter("mode")
        threshold_param = test_class.get_parameter("threshold")

        assert mode_param is not None, "Mode parameter should exist"
        assert threshold_param is not None, "Threshold parameter should exist"

        assert mode_param.cls == "Selector", "Mode parameter should be Selector type"
        assert threshold_param.cls == "Number", "Threshold parameter should be Number type"

        # Verify parameter documentation
        assert mode_param.doc == "Operation mode", "Should preserve parameter documentation"

    def test_multiple_selector_parameters(self):
        """Test class with multiple Selector parameters."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class Config(param.Parameterized):
    theme = param.Selector(default="light", objects=["light", "dark"])
    language = param.Selector(default="en", objects=["en", "es", "fr"])
    level = param.Selector(default="info", objects=["debug", "info", "warning", "error"])

Config("""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion for all Selector parameters
        position = Position(line=6, character=7)  # After Config(
        completions = server._get_constructor_parameter_completions(
            "file:///test.py", "Config(", position
        )

        # Should have completions for all three selector parameters
        assert len(completions) == 3, f"Expected 3 completions, got {len(completions)}"

        completion_labels = [item.label for item in completions]

        # Check that we get all selector parameter assignments
        assert 'theme="light"' in completion_labels, "Should suggest theme parameter"
        assert 'language="en"' in completion_labels, "Should suggest language parameter"
        assert 'level="info"' in completion_labels, "Should suggest level parameter"
