"""Tests for Python environment resolver."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from param_lsp._analyzer.python_environment import PythonEnvironment


def test_from_current():
    """Test creating PythonEnvironment from current interpreter."""
    env = PythonEnvironment.from_current()

    assert env.python == Path(sys.executable)
    assert len(env.site_packages) > 0
    assert all(isinstance(p, Path) for p in env.site_packages)


def test_from_path_valid(tmp_path):
    """Test creating PythonEnvironment from a valid Python path."""
    # Create a mock Python executable
    python_path = tmp_path / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.touch()

    env = PythonEnvironment(python=python_path)
    assert env.python == python_path


def test_from_path_invalid():
    """Test creating PythonEnvironment from an invalid path."""
    with pytest.raises(ValueError, match="Python executable not found"):
        PythonEnvironment(python="/nonexistent/python")


@patch("subprocess.check_output")
def test_query_site_packages(mock_check_output, tmp_path):
    """Test querying site-packages from a Python environment."""
    import json

    python_path = tmp_path / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.touch()

    site_pkg_1 = tmp_path / "lib" / "python3.10" / "site-packages"
    site_pkg_1.mkdir(parents=True)

    user_site = tmp_path / ".local" / "lib" / "python3.10" / "site-packages"
    user_site.mkdir(parents=True)

    # Mock subprocess.check_output to return JSON output
    mock_output = json.dumps({"sys_path": ["", str(site_pkg_1)], "user_site": str(user_site)})
    mock_check_output.return_value = mock_output

    env = PythonEnvironment(python=python_path)
    site_packages = env.site_packages

    assert len(site_packages) == 1
    assert site_packages[0] == site_pkg_1


@patch("subprocess.check_output")
def test_query_user_site(mock_check_output, tmp_path):
    """Test querying user site-packages from a Python environment."""
    import json

    python_path = tmp_path / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.touch()

    user_site = tmp_path / ".local" / "lib" / "python3.10" / "site-packages"
    user_site.mkdir(parents=True)

    # Mock subprocess.check_output to return JSON output
    mock_output = json.dumps({"sys_path": [""], "user_site": str(user_site)})
    mock_check_output.return_value = mock_output

    env = PythonEnvironment(python=python_path)
    # Trigger queries
    _ = env.site_packages
    user_site_result = env.user_site

    assert user_site_result == user_site


def test_from_venv_unix(tmp_path):
    """Test creating PythonEnvironment from a Unix venv."""
    venv_path = tmp_path / "my_venv"
    python_path = venv_path / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.touch()

    env = PythonEnvironment.from_venv(venv_path)
    assert env.python == python_path


def test_from_venv_windows(tmp_path):
    """Test creating PythonEnvironment from a Windows venv."""
    venv_path = tmp_path / "my_venv"
    python_path = venv_path / "Scripts" / "python.exe"
    python_path.parent.mkdir(parents=True)
    python_path.touch()

    env = PythonEnvironment.from_venv(venv_path)
    assert env.python == python_path


def test_from_venv_invalid():
    """Test creating PythonEnvironment from an invalid venv."""
    with pytest.raises(ValueError, match="Virtual environment not found"):
        PythonEnvironment.from_venv("/nonexistent/venv")


def test_from_venv_no_python(tmp_path):
    """Test creating PythonEnvironment from a venv without Python."""
    venv_path = tmp_path / "my_venv"
    venv_path.mkdir()

    with pytest.raises(ValueError, match="No Python executable found in venv"):
        PythonEnvironment.from_venv(venv_path)


@patch("subprocess.run")
def test_from_conda(mock_run, tmp_path):
    """Test creating PythonEnvironment from a conda environment."""
    import json

    conda_env_path = tmp_path / "envs" / "my_conda_env"
    python_path = conda_env_path / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.touch()

    # Mock conda info command - use json.dumps to properly escape paths
    mock_result = MagicMock()
    mock_result.stdout = json.dumps({"envs": [str(conda_env_path)]})
    mock_run.return_value = mock_result

    env = PythonEnvironment.from_conda("my_conda_env")
    assert env.python == python_path


@patch("subprocess.run")
def test_from_conda_windows(mock_run, tmp_path):
    """Test creating PythonEnvironment from a Windows conda environment."""
    import json

    conda_env_path = tmp_path / "envs" / "my_conda_env"
    python_path = conda_env_path / "python.exe"
    python_path.parent.mkdir(parents=True)
    python_path.touch()

    # Mock conda info command - use json.dumps to properly escape paths
    mock_result = MagicMock()
    mock_result.stdout = json.dumps({"envs": [str(conda_env_path)]})
    mock_run.return_value = mock_result

    env = PythonEnvironment.from_conda("my_conda_env")
    assert env.python == python_path


@patch("subprocess.run")
def test_from_conda_windows_scripts(mock_run, tmp_path):
    """Test creating PythonEnvironment from a Windows conda env with Scripts dir."""
    import json

    conda_env_path = tmp_path / "envs" / "my_conda_env"
    python_path = conda_env_path / "Scripts" / "python.exe"
    python_path.parent.mkdir(parents=True)
    python_path.touch()

    # Mock conda info command - use json.dumps to properly escape paths
    mock_result = MagicMock()
    mock_result.stdout = json.dumps({"envs": [str(conda_env_path)]})
    mock_run.return_value = mock_result

    env = PythonEnvironment.from_conda("my_conda_env")
    assert env.python == python_path


@patch("subprocess.run")
def test_from_conda_not_found(mock_run):
    """Test creating PythonEnvironment from a non-existent conda env."""
    mock_result = MagicMock()
    mock_result.stdout = '{"envs": []}'
    mock_run.return_value = mock_result

    with pytest.raises(ValueError, match="Conda environment not found"):
        PythonEnvironment.from_conda("nonexistent_env")


@patch("subprocess.run")
def test_from_conda_no_conda(mock_run):
    """Test creating PythonEnvironment when conda is not installed."""
    mock_run.side_effect = FileNotFoundError()

    with pytest.raises(ValueError, match="conda command not found"):
        PythonEnvironment.from_conda("my_env")


def test_repr(tmp_path):
    """Test string representation of PythonEnvironment."""
    python_path = tmp_path / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.touch()

    env = PythonEnvironment(python=python_path)
    assert repr(env) == f"PythonEnvironment({str(python_path)!r})"


def test_from_environment_variables_venv(tmp_path, monkeypatch):
    """Test detecting environment from VIRTUAL_ENV variable."""
    venv_path = tmp_path / "my_venv"
    python_path = venv_path / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.touch()

    monkeypatch.setenv("VIRTUAL_ENV", str(venv_path))

    env = PythonEnvironment.from_environment_variables()
    assert env is not None
    assert env.python == python_path


def test_from_environment_variables_conda(tmp_path, monkeypatch):
    """Test detecting environment from CONDA variables."""
    conda_prefix = tmp_path / "conda_env"
    python_path = conda_prefix / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.touch()

    # Clear VIRTUAL_ENV to prevent it from taking priority
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setenv("CONDA_DEFAULT_ENV", "my_conda_env")
    monkeypatch.setenv("CONDA_PREFIX", str(conda_prefix))

    env = PythonEnvironment.from_environment_variables()
    assert env is not None
    assert env.python == python_path


def test_from_environment_variables_conda_windows(tmp_path, monkeypatch):
    """Test detecting Windows conda environment."""
    conda_prefix = tmp_path / "conda_env"
    python_path = conda_prefix / "python.exe"
    python_path.parent.mkdir(parents=True)
    python_path.touch()

    # Clear VIRTUAL_ENV to prevent it from taking priority
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setenv("CONDA_DEFAULT_ENV", "my_conda_env")
    monkeypatch.setenv("CONDA_PREFIX", str(conda_prefix))

    env = PythonEnvironment.from_environment_variables()
    assert env is not None
    assert env.python == python_path


def test_from_environment_variables_none(monkeypatch):
    """Test when no environment variables are set."""
    # Clear all relevant environment variables
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.delenv("CONDA_DEFAULT_ENV", raising=False)
    monkeypatch.delenv("CONDA_PREFIX", raising=False)

    env = PythonEnvironment.from_environment_variables()
    assert env is None


def test_from_environment_variables_priority_venv(tmp_path, monkeypatch, caplog):
    """Test that VIRTUAL_ENV takes priority over CONDA variables and warns."""
    import logging

    venv_path = tmp_path / "my_venv"
    venv_python = venv_path / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.touch()

    conda_prefix = tmp_path / "conda_env"
    conda_python = conda_prefix / "bin" / "python"
    conda_python.parent.mkdir(parents=True)
    conda_python.touch()

    monkeypatch.setenv("VIRTUAL_ENV", str(venv_path))
    monkeypatch.setenv("CONDA_DEFAULT_ENV", "my_conda_env")
    monkeypatch.setenv("CONDA_PREFIX", str(conda_prefix))

    with caplog.at_level(logging.WARNING):
        env = PythonEnvironment.from_environment_variables()
        assert env is not None
        assert env.python == venv_python  # venv should win

        # Check that warning was logged
        assert any("Both VIRTUAL_ENV" in record.message for record in caplog.records)
        assert any("misconfiguration" in record.message for record in caplog.records)
