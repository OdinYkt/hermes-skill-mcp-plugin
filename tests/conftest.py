"""Shared fixtures for hermes-skill-mcp plugin tests."""

from __future__ import annotations

import sys
from pathlib import Path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import shutil
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def temp_skills_dir() -> Path:
    """Create a temporary skills directory, yield it, then clean up."""
    tmp = Path(tempfile.mkdtemp(prefix="hermes-skill-mcp-test-"))
    try:
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def skill_with_mcp(temp_skills_dir: Path):
    """Factory: create a skill dir containing SKILL.md + mcp.yaml, return Path."""

    def _create(name: str, mcp_config: dict | None = None) -> Path:
        skill_dir = temp_skills_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Write SKILL.md
        (skill_dir / "SKILL.md").write_text(
            f"# {name}\n\nDescription of {name} skill.\n",
            encoding="utf-8",
        )

        # Write mcp.yaml with provided or default config
        import yaml

        if mcp_config is None:
            mcp_config = {
                "mcpServers": {
                    f"{name}-server": {
                        "command": "python",
                        "args": ["-m", f"{name}_server"],
                    }
                }
            }
        (skill_dir / "mcp.yaml").write_text(
            yaml.safe_dump(mcp_config), encoding="utf-8"
        )

        return skill_dir

    return _create


@pytest.fixture
def skill_without_mcp(temp_skills_dir: Path):
    """Factory: create a skill dir containing only SKILL.md, return Path."""

    def _create(name: str) -> Path:
        skill_dir = temp_skills_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)

        (skill_dir / "SKILL.md").write_text(
            f"# {name}\n\nDescription of {name} skill (no MCP).\n",
            encoding="utf-8",
        )

        return skill_dir

    return _create


@pytest.fixture
def mock_mcp_client() -> MagicMock:
    """Return a MagicMock simulating an MCP client session.

    - list_tools: AsyncMock returning a list of Tool dicts
    - call_tool: AsyncMock returning CallToolResult
    - close: AsyncMock
    """
    client = MagicMock()
    client.list_tools = AsyncMock(return_value=[])
    client.call_tool = AsyncMock(return_value=MagicMock(content=[]))
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_plugin_context() -> MagicMock:
    """Return a MagicMock simulating Hermes PluginContext.

    Provides:
    - register_tool: MagicMock
    - register_hook: MagicMock
    - manifest: MagicMock with name='hermes-skill-mcp'
    """
    ctx = MagicMock()
    ctx.register_tool = MagicMock()
    ctx.register_hook = MagicMock()
    ctx.manifest = MagicMock()
    ctx.manifest.name = "hermes-skill-mcp"
    return ctx
