"""Hermes plugin shim — re-exports register() from hermes_skill_mcp package.

This file exists so that Hermes directory-based plugin discovery
finds both ``plugin.yaml`` and ``__init__.py`` at the repository root.
The actual plugin code lives in the ``src/hermes_skill_mcp/`` subdirectory.
"""

try:
    from .hermes_skill_mcp import register  # Hermes directory-based discovery
except ImportError:
    from hermes_skill_mcp import register  # pytest / pip install
