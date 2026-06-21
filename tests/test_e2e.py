"""End-to-end integration tests with real MCP server."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


def _check_mcp_server_time():
    """Check if mcp-server-time is available."""
    if not shutil.which("uvx"):
        return False, "uvx not found on PATH"
    try:
        result = subprocess.run(
            ["uvx", "mcp-server-time", "--help"],
            capture_output=True, timeout=15,
        )
        return result.returncode == 0, "mcp-server-time --help failed"
    except Exception as e:
        return False, str(e)


MCP_TIME_OK, MCP_TIME_REASON = _check_mcp_server_time()


@pytest.mark.skipif(not MCP_TIME_OK, reason=f"mcp-server-time not available: {MCP_TIME_REASON}")
class TestEndToEndRealMcp:
    """Full pipeline with real mcp-server-time."""

    @pytest.fixture
    def time_skill_dir(self, temp_skills_dir):
        skill_dir = temp_skills_dir / "time-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: time-skill\ndescription: Get current time via MCP.\n---\n# Time Skill\n"
        )
        config = {"time": {"command": "uvx", "args": ["mcp-server-time"], "timeout": 15}}
        (skill_dir / "mcp.yaml").write_text(yaml.dump(config))
        return skill_dir

    @pytest.mark.asyncio
    async def test_parse_connect_call_get_result(self, time_skill_dir):
        """Parse mcp.yaml -> connect -> call get_current_time -> get result."""
        from _config import parse_mcp_config
        from _connection import SkillMcpManager

        config = parse_mcp_config(time_skill_dir)
        assert "time" in config
        assert config["time"]["command"] == "uvx"

        manager = SkillMcpManager()
        try:
            client = await manager.get_or_create_client(
                "e2e-test", "time-skill", "time", config["time"]
            )
            result = await client.call_tool(name="get_current_time", arguments={})
            text_parts = [item.text for item in result.content if hasattr(item, "text")]
            output = "\n".join(text_parts)
            assert len(output) > 0
            assert any(w in output.lower() for w in ["time", "utc", "gmt", "202"])
        finally:
            await manager.shutdown_all()

    @pytest.mark.asyncio
    async def test_list_tools_returns_time_tools(self, time_skill_dir):
        """list_tools returns expected tools."""
        from _config import parse_mcp_config
        from _connection import SkillMcpManager

        config = parse_mcp_config(time_skill_dir)
        manager = SkillMcpManager()
        try:
            client = await manager.get_or_create_client(
                "e2e-test", "time-skill", "time", config["time"]
            )
            tools = await client.list_tools()
            tool_names = [t.name for t in tools.tools]
            assert "get_current_time" in tool_names or "convert_time" in tool_names
        finally:
            await manager.shutdown_all()


class TestSkillViewHookE2E:
    """skill_view hook integration — static MCP section, no handshake."""

    def test_hook_appends_static_mcp_section(self, temp_skills_dir):
        """Hook augments skill_view result with static MCP config."""
        skill_dir = temp_skills_dir / "e2e-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: e2e-skill\ndescription: Test skill.\n---\n# Test\n"
        )
        config = {"test": {"command": "uvx", "args": ["mcp-server-time"], "timeout": 10}}
        (skill_dir / "mcp.yaml").write_text(yaml.dump(config))

        from _skill_view_hook import create_hook

        hook = create_hook()
        view_json = json.dumps({
            "success": True,
            "name": "e2e-skill",
            "content": "# Test",
            "path": str(skill_dir),
        })
        result = hook(
            tool_name="skill_view", args={"name": "e2e-skill"}, result=view_json,
            task_id="e2e", session_id="e2e", tool_call_id="tc", turn_id="tn",
            api_request_id=None, duration_ms=10, status="success",
            error_type=None, error_message=None,
        )
        assert "## MCP Servers" in result
        assert "uvx" in result
        assert "mcp-server-time" in result
        # Must NOT contain tool names (no handshake)
        assert "get_current_time" not in result
        assert "convert_time" not in result
