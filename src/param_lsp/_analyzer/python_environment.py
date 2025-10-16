"""
Python environment resolver for param-lsp.

This module provides utilities to discover Python environments and their
site-packages directories, enabling cross-environment analysis.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

from param_lsp._logging import get_logger

logger = get_logger(__name__, "python-env")


class PythonEnvironment:
    """Represents a Python environment with its site-packages paths."""

    def __init__(
        self,
        python: str | Path,
        site_packages: list[Path] | None = None,
        user_site: Path | None = None,
    ):
        """
        Initialize a Python environment.

        Args:
            python: Path to the Python executable
            site_packages: List of site-packages directories (will be queried if None)
            user_site: User site-packages directory (will be queried if None)
        """
        self.python = Path(python)
        self._site_packages = site_packages
        self._user_site = user_site

        # Validate the Python executable exists
        if not self.python.exists():
            msg = f"Python executable not found: {self._pretty_python}"
            raise ValueError(msg)

    @property
    def site_packages(self) -> list[Path]:
        """Get the site-packages directories for this environment."""
        if self._site_packages is None:
            self._query_python_exe()
        return cast("list[Path]", self._site_packages)

    @property
    def user_site(self) -> Path | None:
        """Get the user site-packages directory for this environment."""
        if self._user_site is None:
            self._query_python_exe()
        return self._user_site

    def _query_python_exe(self) -> Path | None:
        try:
            # Use JSON output for reliable cross-platform path handling
            script = "import json, sys, site; print(json.dumps({'sys_path': sys.path, 'user_site': site.USER_SITE}))"
            output = subprocess.check_output(  # noqa: S603
                [os.fspath(self.python), "-c", script], text=True, timeout=10
            )
            site_info = json.loads(output)
            # Skip the first empty entry in sys.path
            self._site_packages = [Path(p) for p in site_info["sys_path"][1:]]
            user_site = Path(site_info["user_site"])
            self._user_site = user_site if user_site.exists() else None
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            json.JSONDecodeError,
        ) as e:
            logger.warning(f"Failed to query site from {self.python}: {e}")

    @classmethod
    def from_current(cls) -> PythonEnvironment:
        """Create a PythonEnvironment from the current Python interpreter."""
        return cls(python=sys.executable)

    @classmethod
    def _find_python_in_prefix(cls, prefix: Path) -> Path | None:
        """
        Find Python executable in a given prefix directory.

        Args:
            prefix: Root directory to search for Python executable

        Returns:
            Path to Python executable if found, None otherwise
        """
        python_paths = [
            prefix / "bin" / "python",  # Unix/Linux/macOS
            prefix / "python.exe",  # Windows (root)
            prefix / "Scripts" / "python.exe",  # Windows (Scripts)
            prefix / "bin" / "python3",  # Unix/Linux/macOS alternative
        ]

        for python_path in python_paths:
            if python_path.exists():
                return python_path

        return None

    @classmethod
    def from_environment_variables(cls) -> PythonEnvironment | None:
        """
        Detect and create a PythonEnvironment from standard environment variables.

        Checks for VIRTUAL_ENV and CONDA_DEFAULT_ENV/CONDA_PREFIX to automatically
        detect the current Python environment.

        Returns:
            PythonEnvironment instance if an environment is detected, None otherwise

        Priority:
            1. VIRTUAL_ENV (venv/virtualenv)
            2. CONDA_DEFAULT_ENV + CONDA_PREFIX (conda)
        """
        import os

        # Check for venv/virtualenv
        venv_path = os.environ.get("VIRTUAL_ENV")
        conda_env = os.environ.get("CONDA_DEFAULT_ENV")
        conda_prefix = os.environ.get("CONDA_PREFIX")

        # Warn if both are set (potential misconfiguration)
        if venv_path and conda_env and conda_prefix:
            logger.warning(
                f"Both VIRTUAL_ENV ({venv_path}) and CONDA environment "
                f"({conda_env}) detected. Using VIRTUAL_ENV. "
                "This may indicate a misconfiguration."
            )

        if venv_path:
            try:
                logger.info(f"Detected virtual environment: {venv_path!r}")
                return cls.from_venv(venv_path)
            except ValueError as e:
                logger.warning(f"Failed to use virtual environment: {e}")

        # Check for conda environment
        if conda_env and conda_prefix:
            python_path = cls._find_python_in_prefix(Path(conda_prefix))
            if python_path:
                try:
                    logger.info(f"Detected conda environment: {conda_env!r}")
                    return cls.from_path(python_path)
                except ValueError as e:
                    logger.warning(f"Failed to use conda environment: {e}")
            else:
                logger.warning(f"Failed to locate Python in conda environment: {conda_env!r}")

        return None

    @classmethod
    def from_path(cls, python_path: str | Path) -> PythonEnvironment:
        """
        Create a PythonEnvironment from a Python executable path.

        Args:
            python_path: Path to Python executable
                        (e.g., /path/to/venv/bin/python or C:\\path\\to\\venv\\Scripts\\python.exe)

        Returns:
            PythonEnvironment instance

        Raises:
            ValueError: If the Python executable is invalid
        """
        return cls(python=python_path)

    @classmethod
    def from_venv(cls, venv_path: str | Path) -> PythonEnvironment:
        """
        Create a PythonEnvironment from a virtual environment directory.

        Args:
            venv_path: Path to the venv root directory

        Returns:
            PythonEnvironment instance

        Raises:
            ValueError: If the venv is invalid
        """
        venv_path = Path(venv_path)
        if not venv_path.exists():
            msg = f"Virtual environment not found: {venv_path}"
            raise ValueError(msg)

        python_path = cls._find_python_in_prefix(venv_path)
        if python_path:
            return cls(python=python_path)

        msg = f"No Python executable found in venv: {venv_path}"
        raise ValueError(msg)

    @classmethod
    def from_conda(cls, env_name: str) -> PythonEnvironment:
        """
        Create a PythonEnvironment from a conda environment name.

        Args:
            env_name: Name of the conda environment

        Returns:
            PythonEnvironment instance

        Raises:
            ValueError: If the conda environment is invalid
        """
        try:
            # Get conda environment info
            result = subprocess.run(
                ["conda", "info", "--envs", "--json"],  # noqa: S607
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            envs_info = json.loads(result.stdout)
            envs = envs_info.get("envs", [])

            # Find the environment by name
            env_path = None
            for env in envs:
                env_path_obj = Path(env)
                if env_path_obj.name == env_name:
                    env_path = env_path_obj
                    break

            if not env_path:
                msg = f"Conda environment not found: {env_name}"
                raise ValueError(msg)

            # Find Python executable in conda env
            python_path = cls._find_python_in_prefix(env_path)
            if python_path:
                return cls(python=python_path)

            msg = f"No Python executable found in conda env: {env_name}"
            raise ValueError(msg)

        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            json.JSONDecodeError,
        ) as e:
            msg = f"Failed to query conda environment {env_name}: {e}"
            raise ValueError(msg) from e
        except FileNotFoundError as e:
            msg = "conda command not found. Is conda installed and in PATH?"
            raise ValueError(msg) from e

    @property
    def _pretty_python(self):
        if self.python is None:
            return self.python
        if sys.platform.startswith("win"):
            return os.fspath(self.python)
        return os.fspath(self.python).replace(os.path.expanduser("~"), "~")

    def __repr__(self) -> str:
        return f"PythonEnvironment({self._pretty_python!r})"
