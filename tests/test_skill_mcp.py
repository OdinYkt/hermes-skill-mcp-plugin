"""
E2E tests for skill-mcp plugin.

Verifies: plugin → MCP config → agent calls skill_mcp
→ gets unguessable magic phrase from MCP server.
"""
import importlib
import os
import subprocess
from pathlib import Path

import pytest

from constants import (
    CLI_TIMEOUT, CONFIG_PATH, MAGIC_PHRASE, MODEL_KEY,
)
from constants import (
    PLUGIN_PATH, SERVER_NAME, SKILL_NAME, SKILL_PATH, SKILLS_DIR, TOOL_NAME,
)
from constants import connected_manager, make_manager, run_hermes_e2e


from conftest import import_plugin_module  # noqa: WPS433






class TestAgentE2E:
    """End-to-end: Hermes agent loads skill, calls skill_mcp tool."""

    @pytest.fixture(autouse=True)
    def require_key(self):
        if not os.environ.get("HERMES_API_KEY"):
            pytest.skip("HERMES_API_KEY not set")

    def test_magic_secret(self, e2e_config):
        """Agent calls skill_mcp → gets unguessable phrase from MCP."""
        prompt = (
            "Load skill '{0}'. "
            "Use skill_mcp to call {1} from the {2} MCP server. "
            "Output ONLY the exact phrase returned. Nothing else."
        ).format(SKILL_NAME, TOOL_NAME, SERVER_NAME)

        agent_output = run_hermes_e2e(
            ["-z", prompt, "-m", e2e_config[MODEL_KEY], "chat"],
            e2e_config,
        )

        err_msg = "Missing '{0}' in agent output: {1}"
        assert MAGIC_PHRASE in agent_output, err_msg.format(
            MAGIC_PHRASE, agent_output[:len(agent_output)],
        )
