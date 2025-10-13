"""
Python environment resolver for param-lsp.

This module provides utilities to discover Python environments and their
site-packages directories, enabling cross-environment analysis.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


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
            msg = f"Python executable not found: {self.python}"
            raise ValueError(msg)

    @property
    def site_packages(self) -> list[Path]:
        """Get the site-packages directories for this environment."""
        if self._site_packages is None:
            self._site_packages = self._query_site_packages()
        return self._site_packages

    @property
    def user_site(self) -> Path | None:
        """Get the user site-packages directory for this environment."""
        if self._user_site is None:
            self._user_site = self._query_user_site()
        return self._user_site

    def _query_site_packages(self) -> list[Path]:
        """Query the Python environment for site-packages and editable install paths."""
        try:
            # Query sys.path which includes both site-packages and paths from .pth files (editable installs)
            # We filter to only include site-packages directories and editable install paths,
            # excluding the base Python installation directories
            result = subprocess.run(  # noqa: S603
                [
                    str(self.python),
                    "-c",
                    "import sys; import json; import os; "
                    "from pathlib import Path; "
                    "cwd = Path.cwd(); "
                    # Filter sys.path to include only site-packages and editable install paths
                    # Exclude: current dir, .zip files, base Python lib dirs (lib/python3.x without site-packages)
                    "paths = [p for p in map(Path, sys.path) if p and p.is_absolute() and p.is_dir() "
                    "and p != cwd "  # Exclude current working directory
                    "and ('site-packages' in p.parts or 'dist-packages' in p.parts or "
                    # Include paths added by .pth files for editable installs (src dirs in projects)
                    "any((p / name).is_file() for name in ['.pth', 'setup.py', 'pyproject.toml']))]; "
                    "print(json.dumps([str(p) for p in paths]))",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            paths = json.loads(result.stdout.strip())
            return [Path(p) for p in paths]
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            json.JSONDecodeError,
        ) as e:
            logger.warning(f"Failed to query site-packages from {self.python}: {e}")
            return []

    def _query_user_site(self) -> Path | None:
        """Query the Python environment for user site-packages directory."""
        try:
            result = subprocess.run(  # noqa: S603
                [
                    str(self.python),
                    "-c",
                    "import site; print(site.getusersitepackages())",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            user_site = Path(result.stdout.strip())
            return user_site if user_site.exists() else None
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.warning(f"Failed to query user site from {self.python}: {e}")
            return None

    @classmethod
    def from_current(cls) -> PythonEnvironment:
        """Create a PythonEnvironment from the current Python interpreter."""
        import site

        # Get the current working directory to exclude it from sys.path scan
        cwd = Path.cwd()

        # Use sys.path to include both site-packages and editable installs
        # Filter to only include site-packages and editable install paths,
        # excluding the base Python installation directories and current working directory
        site_packages = [
            p
            for p in map(Path, sys.path)
            if p
            and p.is_absolute()
            and p.is_dir()
            and p != cwd  # Exclude current working directory
            and (
                "site-packages" in p.parts
                or "dist-packages" in p.parts
                # Include paths added by .pth files for editable installs
                or any((p / name).is_file() for name in [".pth", "setup.py", "pyproject.toml"])
            )
        ]
        user_site_path = site.getusersitepackages()
        user_site = (
            Path(user_site_path) if user_site_path and Path(user_site_path).exists() else None
        )

        return cls(
            python=sys.executable,
            site_packages=site_packages,
            user_site=user_site,
        )

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
                logger.info(f"Detected venv from VIRTUAL_ENV: {venv_path}")
                return cls.from_venv(venv_path)
            except ValueError as e:
                logger.warning(f"Failed to use VIRTUAL_ENV: {e}")

        # Check for conda environment
        if conda_env and conda_prefix:
            python_path = cls._find_python_in_prefix(Path(conda_prefix))
            if python_path:
                try:
                    logger.info(f"Detected conda environment: {conda_env}")
                    return cls.from_path(python_path)
                except ValueError as e:
                    logger.warning(f"Failed to use conda environment: {e}")
            else:
                logger.warning(f"Failed to locate Python in conda environment: {conda_env}")

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

    def __repr__(self) -> str:
        return f"PythonEnvironment(python={self.python})"
