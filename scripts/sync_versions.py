#!/usr/bin/env python3
"""Sync VSCode extension version with param-lsp version."""

from __future__ import annotations

import json
import re
from pathlib import Path

from param_lsp._version import __version__ as param_version

print(f"Current param-lsp version: {param_version}")


# Convert param version to VSCode extension compatible version
def convert_version(version: str) -> str:
    """Convert param version to VSCode extension compatible version."""
    # Remove 'v' prefix if present
    version = version.lstrip("v")

    # Handle development versions (e.g., "0.0.1a0.post1.dev30+...")
    if "+" in version:
        version = version.split("+")[0]

    if ".post" in version:
        version = version.split(".post")[0]

    if ".dev" in version:
        version = version.split(".dev")[0]

    # Convert 'a' alpha suffix to '-alpha.'
    if "a" in version and version[-2:].startswith("a"):
        match = re.match(r"(\d+\.\d+\.\d+)a(\d+)", version)
        if match:
            base, alpha_num = match.groups()
            version = f"{base}-alpha.{alpha_num}"

    # Convert 'b' beta suffix to '-beta.'
    if "b" in version and version[-2:].startswith("b"):
        match = re.match(r"(\d+\.\d+\.\d+)b(\d+)", version)
        if match:
            base, beta_num = match.groups()
            version = f"{base}-beta.{beta_num}"

    # Convert 'rc' release candidate suffix to '-rc.'
    if "rc" in version:
        match = re.match(r"(\d+\.\d+\.\d+)rc(\d+)", version)
        if match:
            base, rc_num = match.groups()
            version = f"{base}-rc.{rc_num}"

    return version


vscode_version = convert_version(param_version)
print(f"Converted VSCode version: {vscode_version}")

# Update VSCode extension package.json
package_json_path = Path(__file__).parent.parent / "vscode-extension" / "package.json"

with open(package_json_path) as f:
    package_data = json.load(f)

old_version = package_data["version"]
package_data["version"] = vscode_version

with open(package_json_path, "w") as f:
    json.dump(package_data, f, indent=2)

print(f"Updated VSCode extension version: {old_version} → {vscode_version}")
