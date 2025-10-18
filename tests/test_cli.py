from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


def test_check_command_no_errors():
    """Test check command with valid file."""
    code = """
import param

class Widget(param.Parameterized):
    value = param.String(default="hello")
    count = param.Integer(default=42, bounds=(0, 100))
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        f.flush()
        temp_file = f.name

    try:
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "param_lsp", "check", temp_file],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "No issues found" in result.stdout
    finally:
        Path(temp_file).unlink()


def test_check_command_with_type_error():
    """Test check command with type mismatch error."""
    code = """
import param

class Widget(param.Parameterized):
    value = param.String(default=123)  # Type error: int not string
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        f.flush()
        temp_file = f.name

    try:
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "param_lsp", "check", temp_file],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "type-mismatch" in result.stdout
        assert "Found 1 error(s)" in result.stdout
    finally:
        Path(temp_file).unlink()


def test_check_command_with_bounds_violation():
    """Test check command with bounds violation."""
    code = """
import param

class Widget(param.Parameterized):
    count = param.Integer(default=200, bounds=(0, 100))  # Bounds violation
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        f.flush()
        temp_file = f.name

    try:
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "param_lsp", "check", temp_file],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "bounds-violation" in result.stdout
        assert "Found 1 error(s)" in result.stdout
    finally:
        Path(temp_file).unlink()


def test_check_command_multiple_files():
    """Test check command with multiple files."""
    code1 = """
import param

class Widget1(param.Parameterized):
    value = param.String(default="valid")
"""
    code2 = """
import param

class Widget2(param.Parameterized):
    value = param.String(default=123)  # Type error
"""
    with (
        tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f1,
        tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f2,
    ):
        f1.write(code1)
        f1.flush()
        temp_file1 = f1.name

        f2.write(code2)
        f2.flush()
        temp_file2 = f2.name

    try:
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "param_lsp", "check", temp_file1, temp_file2],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "type-mismatch" in result.stdout
        assert "Found 1 error(s)" in result.stdout
        assert "in 2 file(s)" in result.stdout
    finally:
        Path(temp_file1).unlink()
        Path(temp_file2).unlink()


def test_check_command_file_not_found():
    """Test check command with non-existent file."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "param_lsp", "check", "/nonexistent/file.py"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Path not found" in result.stderr


def test_check_command_with_depends_error():
    """Test check command with invalid @param.depends parameter."""
    code = """
import param

class Widget(param.Parameterized):
    value = param.String(default="hello")

    @param.depends('nonexistent')
    def compute(self):
        return self.value
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        f.flush()
        temp_file = f.name

    try:
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "param_lsp", "check", temp_file],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "invalid-depends-parameter" in result.stdout
        assert "Found 1 error(s)" in result.stdout
    finally:
        Path(temp_file).unlink()


def test_cache_show_command():
    """Test cache --show command."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "param_lsp", "cache", "--show"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "::" in result.stdout  # Format: path::version


def test_server_help():
    """Test that server subcommand help works."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "param_lsp", "server", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--tcp" in result.stdout
    assert "--stdio" in result.stdout


def test_check_help():
    """Test that check subcommand help works."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "param_lsp", "check", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "files" in result.stdout
    assert "directories" in result.stdout


def test_requires_subcommand():
    """Test that CLI requires an explicit subcommand."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "param_lsp"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "A subcommand is required" in result.stderr
    assert "param-lsp server" in result.stderr


def test_check_command_with_directory():
    """Test check command with directory input."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create valid file
        valid_file = temp_path / "valid.py"
        valid_file.write_text("""
import param

class Widget(param.Parameterized):
    value = param.String(default="hello")
""")

        # Create file with error
        error_file = temp_path / "error.py"
        error_file.write_text("""
import param

class Widget(param.Parameterized):
    value = param.String(default=123)  # Type error
""")

        result = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "param_lsp", "check", str(temp_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "type-mismatch" in result.stdout
        assert "Found 1 error(s)" in result.stdout
        assert "in 2 file(s)" in result.stdout


def test_check_command_excludes_venv():
    """Test that check command excludes .venv, .pixi, and node_modules directories."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create valid file in root
        valid_file = temp_path / "valid.py"
        valid_file.write_text("""
import param

class Widget(param.Parameterized):
    value = param.String(default="hello")
""")

        # Create .venv directory with error file
        venv_dir = temp_path / ".venv"
        venv_dir.mkdir()
        venv_file = venv_dir / "error.py"
        venv_file.write_text("""
import param

class Widget(param.Parameterized):
    value = param.String(default=123)  # Type error - should be ignored
""")

        # Create .pixi directory with error file
        pixi_dir = temp_path / ".pixi"
        pixi_dir.mkdir()
        pixi_file = pixi_dir / "error.py"
        pixi_file.write_text("""
import param

class Widget(param.Parameterized):
    value = param.String(default=123)  # Type error - should be ignored
""")

        # Create node_modules directory with error file
        node_dir = temp_path / "node_modules"
        node_dir.mkdir()
        node_file = node_dir / "error.py"
        node_file.write_text("""
import param

class Widget(param.Parameterized):
    value = param.String(default=123)  # Type error - should be ignored
""")

        result = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "param_lsp", "check", str(temp_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        # Should succeed because the only file checked is valid.py
        assert result.returncode == 0
        assert "No issues found in 1 file(s)" in result.stdout
