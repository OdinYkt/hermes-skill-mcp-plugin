"""Tests for _skill_view_hook.py — transform_tool_result hook.

Covers all behavioral contract scenarios from Task 5 of IMPLEMENTATION_PLAN.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


# ============================================================================
# Helpers
# ============================================================================


def _make_skill_view_result(path: str, ok: bool = True) -> str:
    """Build a fake skill_view JSON result string."""
    return json.dumps({
        "ok": ok,
        "path": path,
        "name": Path(path).name,
        "description": "A test skill",
    })


def _invoke_hook(hook, tool_name: str = "skill_view", result: str | None = None,
                 **extra_kwargs) -> str | None:
    """Call the hook with standard Hermes transform_tool_result kwargs."""
    kwargs = {
        "tool_name": tool_name,
        "result": result,
        "args": {},
        "task_id": "",
        "session_id": "",
        "tool_call_id": "",
        "turn_id": "",
        "api_request_id": "",
        "duration_ms": 0,
        "status": "success",
        "error_type": "",
        "error_message": "",
        **extra_kwargs,
    }
    return hook(**kwargs)


# ============================================================================
# create_hook basic
# ============================================================================


class TestCreateHookBasic:
    """create_hook() returns a callable, works with or without skill_dirs."""

    def test_returns_callable(self):
        from _skill_view_hook import create_hook
        hook = create_hook()
        assert callable(hook)

    def test_returns_callable_with_skill_dirs(self):
        from _skill_view_hook import create_hook
        hook = create_hook(skill_dirs=["/tmp/skills"])
        assert callable(hook)

    def test_returns_callable_with_none_skill_dirs(self):
        from _skill_view_hook import create_hook
        hook = create_hook(skill_dirs=None)
        assert callable(hook)


# ============================================================================
# Hook augments skill_view result
# ============================================================================


class TestHookAugmentsSkillView:
    """Hook appends MCP section for skill_view results with valid mcp.yaml."""

    def test_stdio_server_appended(self, temp_skills_dir: Path):
        from _skill_view_hook import create_hook

        # Create skill dir with mcp.yaml (stdio)
        skill_dir = temp_skills_dir / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# My Skill\n", encoding="utf-8")

        mcp_config = {
            "sqlite": {
                "command": "uvx",
                "args": ["mcp-server-sqlite", "--db", "data.db"],
            }
        }
        (skill_dir / "mcp.yaml").write_text(
            yaml.safe_dump(mcp_config), encoding="utf-8"
        )

        hook = create_hook()
        original = _make_skill_view_result(str(skill_dir))
        result = _invoke_hook(hook, result=original)

        assert result is not None
        assert isinstance(result, str)
        assert result.startswith(original)
        assert "## MCP Servers" in result
        assert "### sqlite" in result
        assert "Static config" in result
        assert "uvx mcp-server-sqlite --db data.db" in result
        assert "timeout: 60s" in result
        assert "connect_timeout: 10s" in result
        assert "idle_timeout: 300s" in result
        assert 'skill_mcp(skill_name="my-skill"' in result
        assert 'mcp_name="sqlite"' in result

    def test_http_server_appended(self, temp_skills_dir: Path):
        from _skill_view_hook import create_hook

        skill_dir = temp_skills_dir / "http-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# HTTP Skill\n", encoding="utf-8")

        mcp_config = {
            "api": {
                "url": "https://mcp.example.com/v1",
                "headers": {
                    "Authorization": "Bearer sk-abc123secret",
                    "X-Custom": "custom-value",
                },
            }
        }
        (skill_dir / "mcp.yaml").write_text(
            yaml.safe_dump(mcp_config), encoding="utf-8"
        )

        hook = create_hook()
        original = _make_skill_view_result(str(skill_dir))
        result = _invoke_hook(hook, result=original)

        assert result is not None
        assert "## MCP Servers" in result
        assert "### api" in result
        assert "url: https://mcp.example.com/v1" in result
        assert "headers:" in result
        # Headers should NOT contain raw credential
        assert "sk-abc123secret" not in result
        assert "timeout: 60s" in result

    def test_skill_view_result_without_ok_field_proceeds(self, temp_skills_dir: Path):
        """Missing 'ok' field → treated as success (proceed)."""
        from _skill_view_hook import create_hook

        skill_dir = temp_skills_dir / "no-ok-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# No OK\n", encoding="utf-8")

        mcp_config = {
            "srv": {"command": "echo", "args": ["hello"]}
        }
        (skill_dir / "mcp.yaml").write_text(
            yaml.safe_dump(mcp_config), encoding="utf-8"
        )

        hook = create_hook()
        # Result without "ok" field
        original = json.dumps({"path": str(skill_dir), "name": "no-ok-skill"})
        result = _invoke_hook(hook, result=original)

        assert result is not None
        assert "## MCP Servers" in result


# ============================================================================
# Non-skill_view tools → None
# ============================================================================


class TestNonSkillViewTools:
    """Hook returns None for any tool_name that isn't 'skill_view'."""

    def test_terminal_returns_none(self):
        from _skill_view_hook import create_hook
        hook = create_hook()
        result = _invoke_hook(hook, tool_name="terminal", result="some output")
        assert result is None

    def test_execute_code_returns_none(self):
        from _skill_view_hook import create_hook
        hook = create_hook()
        result = _invoke_hook(hook, tool_name="execute_code", result="{}")
        assert result is None

    def test_skill_mcp_returns_none(self):
        """Our own skill_mcp tool should not be augmented."""
        from _skill_view_hook import create_hook
        hook = create_hook()
        result = _invoke_hook(hook, tool_name="skill_mcp", result="{}")
        assert result is None

    def test_missing_tool_name_returns_none(self):
        from _skill_view_hook import create_hook
        hook = create_hook()
        result = hook(result="{}", args={})
        assert result is None


# ============================================================================
# Malformed / missing JSON
# ============================================================================


class TestMalformedInput:
    """Hook returns None for invalid or incomplete input."""

    def test_malformed_json_returns_none(self):
        from _skill_view_hook import create_hook
        hook = create_hook()
        result = _invoke_hook(hook, result="not valid json {{{")
        assert result is None

    def test_non_string_result_returns_none(self):
        from _skill_view_hook import create_hook
        hook = create_hook()
        result = _invoke_hook(hook, result=12345)  # type: ignore[arg-type]
        assert result is None

    def test_none_result_returns_none(self):
        from _skill_view_hook import create_hook
        hook = create_hook()
        result = _invoke_hook(hook, result=None)
        assert result is None

    def test_array_json_returns_none(self):
        from _skill_view_hook import create_hook
        hook = create_hook()
        result = _invoke_hook(hook, result='[1, 2, 3]')
        assert result is None

    def test_no_path_field_returns_none(self):
        from _skill_view_hook import create_hook
        hook = create_hook()
        result = _invoke_hook(hook, result='{"ok": true, "name": "test"}')
        assert result is None

    def test_error_status_returns_none(self, temp_skills_dir: Path):
        """skill_view result with ok=false → pass through."""
        from _skill_view_hook import create_hook

        skill_dir = temp_skills_dir / "error-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Error\n", encoding="utf-8")
        (skill_dir / "mcp.yaml").write_text(
            yaml.safe_dump({"srv": {"command": "echo", "args": ["hi"]}}),
            encoding="utf-8",
        )

        hook = create_hook()
        result = _invoke_hook(
            hook,
            result=_make_skill_view_result(str(skill_dir), ok=False),
        )
        assert result is None

    def test_path_not_a_directory_returns_none(self, temp_skills_dir: Path):
        """Path exists but isn't a directory → None."""
        from _skill_view_hook import create_hook

        file_path = temp_skills_dir / "not-a-dir.txt"
        file_path.write_text("hello")

        hook = create_hook()
        result = _invoke_hook(
            hook,
            result=json.dumps({"ok": True, "path": str(file_path)}),
        )
        assert result is None

    def test_nonexistent_path_returns_none(self):
        from _skill_view_hook import create_hook
        hook = create_hook()
        result = _invoke_hook(
            hook,
            result=json.dumps({"ok": True, "path": "/nonexistent/path/xyz"}),
        )
        assert result is None


# ============================================================================
# Missing mcp.yaml
# ============================================================================


class TestMissingMcpYaml:
    """Hook returns None when mcp.yaml is not found at the skill path."""

    def test_no_mcp_yaml_returns_none(self, temp_skills_dir: Path):
        from _skill_view_hook import create_hook

        skill_dir = temp_skills_dir / "no-mcp-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# No MCP\n", encoding="utf-8")
        # No mcp.yaml created

        hook = create_hook()
        original = _make_skill_view_result(str(skill_dir))
        result = _invoke_hook(hook, result=original)
        assert result is None

    def test_empty_mcp_yaml_returns_none(self, temp_skills_dir: Path):
        from _skill_view_hook import create_hook

        skill_dir = temp_skills_dir / "empty-mcp-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Empty MCP\n", encoding="utf-8")
        (skill_dir / "mcp.yaml").write_text("{}\n", encoding="utf-8")

        hook = create_hook()
        original = _make_skill_view_result(str(skill_dir))
        result = _invoke_hook(hook, result=original)
        assert result is None

    def test_invalid_mcp_yaml_returns_none(self, temp_skills_dir: Path):
        from _skill_view_hook import create_hook

        skill_dir = temp_skills_dir / "bad-mcp-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Bad\n", encoding="utf-8")
        (skill_dir / "mcp.yaml").write_text(
            "server: [unclosed\n  command: bad", encoding="utf-8"
        )

        hook = create_hook()
        original = _make_skill_view_result(str(skill_dir))
        result = _invoke_hook(hook, result=original)
        assert result is None


# ============================================================================
# Multiple servers
# ============================================================================


class TestMultipleServers:
    """Hook lists all servers from mcp.yaml."""

    def test_multiple_servers_all_listed(self, temp_skills_dir: Path):
        from _skill_view_hook import create_hook

        skill_dir = temp_skills_dir / "multi-server-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Multi\n", encoding="utf-8")

        mcp_config = {
            "sqlite": {
                "command": "uvx",
                "args": ["mcp-server-sqlite"],
            },
            "github": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
            },
            "weather-api": {
                "url": "https://weather.example.com/mcp",
            },
        }
        (skill_dir / "mcp.yaml").write_text(
            yaml.safe_dump(mcp_config), encoding="utf-8"
        )

        hook = create_hook()
        original = _make_skill_view_result(str(skill_dir))
        result = _invoke_hook(hook, result=original)

        assert result is not None
        assert "### sqlite" in result
        assert "### github" in result
        assert "### weather-api" in result
        # All three servers present
        assert result.count("### ") == 3

    def test_mixed_stdio_and_http(self, temp_skills_dir: Path):
        from _skill_view_hook import create_hook

        skill_dir = temp_skills_dir / "mixed-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Mixed\n", encoding="utf-8")

        mcp_config = {
            "local-db": {
                "command": "python",
                "args": ["-m", "db_server"],
            },
            "remote-api": {
                "url": "https://api.example.com/mcp",
                "headers": {"X-API-Key": "secret-key-12345"},
            },
        }
        (skill_dir / "mcp.yaml").write_text(
            yaml.safe_dump(mcp_config), encoding="utf-8"
        )

        hook = create_hook()
        original = _make_skill_view_result(str(skill_dir))
        result = _invoke_hook(hook, result=original)

        assert result is not None
        assert "### local-db" in result
        assert "### remote-api" in result
        # Stdio shows command
        assert "python -m db_server" in result
        # HTTP shows url
        assert "url: https://api.example.com/mcp" in result
        # HTTP does NOT show command
        # (command is not present for HTTP server after parse_mcp_config)
        assert "command:" not in result.split("### remote-api")[1] or \
            "command:" not in result


# ============================================================================
# Static config, no tool names
# ============================================================================


class TestStaticConfigNoToolNames:
    """MCP section shows static config, not live tool names."""

    def test_no_tool_names_listed(self, temp_skills_dir: Path):
        from _skill_view_hook import create_hook

        skill_dir = temp_skills_dir / "static-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Static\n", encoding="utf-8")

        mcp_config = {
            "time": {
                "command": "uvx",
                "args": ["mcp-server-time"],
            }
        }
        (skill_dir / "mcp.yaml").write_text(
            yaml.safe_dump(mcp_config), encoding="utf-8"
        )

        hook = create_hook()
        original = _make_skill_view_result(str(skill_dir))
        result = _invoke_hook(hook, result=original)

        assert result is not None
        # Must NOT contain tool discovery language
        assert "tools:" not in result.lower().split("## mcp servers")[1] if "## MCP Servers" in result else True
        assert "list_tools" not in result.lower()
        assert "get_current_time" not in result.lower()
        # Must contain static config label
        assert "Static config" in result

    def test_config_contains_timeout_values(self, temp_skills_dir: Path):
        from _skill_view_hook import create_hook

        skill_dir = temp_skills_dir / "timeout-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Timeout\n", encoding="utf-8")

        mcp_config = {
            "srv": {
                "command": "echo",
                "args": ["hi"],
            }
        }
        (skill_dir / "mcp.yaml").write_text(
            yaml.safe_dump(mcp_config), encoding="utf-8"
        )

        hook = create_hook()
        original = _make_skill_view_result(str(skill_dir))
        result = _invoke_hook(hook, result=original)

        assert result is not None
        assert "timeout: 60s" in result
        assert "connect_timeout: 10s" in result
        assert "idle_timeout: 300s" in result

    def test_custom_timeouts_shown(self, temp_skills_dir: Path):
        from _skill_view_hook import create_hook

        skill_dir = temp_skills_dir / "custom-timeout-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Custom\n", encoding="utf-8")

        mcp_config = {
            "srv": {
                "command": "python",
                "args": ["server.py"],
                "timeout": 30,
                "connect_timeout": 5,
                "idle_timeout": 120,
            }
        }
        (skill_dir / "mcp.yaml").write_text(
            yaml.safe_dump(mcp_config), encoding="utf-8"
        )

        hook = create_hook()
        original = _make_skill_view_result(str(skill_dir))
        result = _invoke_hook(hook, result=original)

        assert result is not None
        assert "timeout: 30s" in result
        assert "connect_timeout: 5s" in result
        assert "idle_timeout: 120s" in result


# ============================================================================
# Fail-open — exceptions do not propagate
# ============================================================================


class TestFailOpen:
    """Hook never raises; exceptions are caught, original result preserved."""

    def test_exception_during_parse_returns_none(self, monkeypatch):
        """If json.loads raises unexpectedly, hook returns None."""
        from _skill_view_hook import create_hook

        hook = create_hook()

        # Simulate a weird case where json.loads itself breaks
        import json as json_module
        original_loads = json_module.loads

        def broken_loads(s, **kw):
            raise RuntimeError("simulated crash")

        monkeypatch.setattr(json_module, "loads", broken_loads)

        try:
            result = _invoke_hook(hook, result='{"ok": true, "path": "/tmp"}')
            assert result is None
        finally:
            monkeypatch.setattr(json_module, "loads", original_loads)

    def test_never_raises_on_garbage(self):
        from _skill_view_hook import create_hook
        hook = create_hook()

        # Various garbage inputs — must never raise
        for garbage in [
            None,
            42,
            [],
            {},
            "",
            "not json",
            '{"ok": true}',  # valid JSON but no path
        ]:
            result = _invoke_hook(hook, result=garbage)
            assert result is None, f"hook raised for input: {garbage!r}"


# ============================================================================
# Header redaction
# ============================================================================


class TestHeaderRedaction:
    """HTTP server headers show credential-redacted values."""

    def test_bearer_token_redacted(self, temp_skills_dir: Path):
        from _skill_view_hook import create_hook

        skill_dir = temp_skills_dir / "bearer-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Bearer\n", encoding="utf-8")

        mcp_config = {
            "api": {
                "url": "https://api.example.com",
                "headers": {
                    "Authorization": "Bearer sk-secret-token-value",
                },
            }
        }
        (skill_dir / "mcp.yaml").write_text(
            yaml.safe_dump(mcp_config), encoding="utf-8"
        )

        hook = create_hook()
        original = _make_skill_view_result(str(skill_dir))
        result = _invoke_hook(hook, result=original)

        assert result is not None
        # Raw token should NOT appear
        assert "sk-secret-token-value" not in result
        # Should show something
        assert "Authorization" in result

    def test_api_key_redacted(self, temp_skills_dir: Path):
        from _skill_view_hook import create_hook

        skill_dir = temp_skills_dir / "apikey-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# APIKey\n", encoding="utf-8")

        mcp_config = {
            "api": {
                "url": "https://api.example.com",
                "headers": {
                    "X-API-Key": "super-secret-api-key-12345",
                },
            }
        }
        (skill_dir / "mcp.yaml").write_text(
            yaml.safe_dump(mcp_config), encoding="utf-8"
        )

        hook = create_hook()
        original = _make_skill_view_result(str(skill_dir))
        result = _invoke_hook(hook, result=original)

        assert result is not None
        # Raw key should NOT appear
        assert "super-secret-api-key-12345" not in result

    def test_multiple_headers_all_redacted(self, temp_skills_dir: Path):
        from _skill_view_hook import create_hook

        skill_dir = temp_skills_dir / "multi-header-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# MultiHeader\n", encoding="utf-8")

        mcp_config = {
            "api": {
                "url": "https://api.example.com",
                "headers": {
                    "Authorization": "Bearer token-abc",
                    "X-API-Key": "key-123",
                    "X-Request-ID": "req-456",
                },
            }
        }
        (skill_dir / "mcp.yaml").write_text(
            yaml.safe_dump(mcp_config), encoding="utf-8"
        )

        hook = create_hook()
        original = _make_skill_view_result(str(skill_dir))
        result = _invoke_hook(hook, result=original)

        assert result is not None
        # No raw credentials leaked
        assert "token-abc" not in result
        assert "key-123" not in result
        # Non-sensitive values like req-456 — may or may not be redacted
        # depending on fallback logic. The key point: nothing sensitive leaks.


# ============================================================================
# Result preservation
# ============================================================================


class TestResultPreservation:
    """Original skill_view result is preserved; MCP section is appended."""

    def test_original_content_preserved(self, temp_skills_dir: Path):
        from _skill_view_hook import create_hook

        skill_dir = temp_skills_dir / "preserve-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Preserve\n", encoding="utf-8")

        mcp_config = {
            "srv": {"command": "echo", "args": ["hello"]}
        }
        (skill_dir / "mcp.yaml").write_text(
            yaml.safe_dump(mcp_config), encoding="utf-8"
        )

        hook = create_hook()
        original = json.dumps({
            "ok": True,
            "path": str(skill_dir),
            "name": "preserve-skill",
            "description": "Skill with MCP servers",
            "sections": ["overview", "usage"],
        })
        result = _invoke_hook(hook, result=original)

        assert result is not None
        assert result.startswith(original)
        # Original fields still present in the result
        parsed_original = json.loads(original)
        for key in parsed_original:
            assert key in result


# ============================================================================
# Edge cases
# ============================================================================


class TestEdgeCases:
    """Borderline scenarios."""

    def test_single_server_with_empty_args(self, temp_skills_dir: Path):
        from _skill_view_hook import create_hook

        skill_dir = temp_skills_dir / "empty-args-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# EmptyArgs\n", encoding="utf-8")

        mcp_config = {
            "srv": {"command": "uvx"}
        }
        (skill_dir / "mcp.yaml").write_text(
            yaml.safe_dump(mcp_config), encoding="utf-8"
        )

        hook = create_hook()
        original = _make_skill_view_result(str(skill_dir))
        result = _invoke_hook(hook, result=original)

        assert result is not None
        assert "command: uvx" in result

    def test_skill_name_extracted_from_path(self, temp_skills_dir: Path):
        from _skill_view_hook import create_hook

        # Skill name with hyphens and underscores
        skill_dir = temp_skills_dir / "my-complex_skill-name"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Complex\n", encoding="utf-8")

        mcp_config = {
            "srv": {"command": "echo", "args": ["hi"]}
        }
        (skill_dir / "mcp.yaml").write_text(
            yaml.safe_dump(mcp_config), encoding="utf-8"
        )

        hook = create_hook()
        original = _make_skill_view_result(str(skill_dir))
        result = _invoke_hook(hook, result=original)

        assert result is not None
        assert 'skill_name="my-complex_skill-name"' in result

    def test_no_exception_for_parse_mcp_config_error(self, temp_skills_dir: Path):
        """Even if parse_mcp_config encounters issues, hook doesn't raise."""
        from _skill_view_hook import create_hook

        # Skill dir with no mcp.yaml at all
        skill_dir = temp_skills_dir / "clean-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Clean\n", encoding="utf-8")

        hook = create_hook()
        original = _make_skill_view_result(str(skill_dir))
        result = _invoke_hook(hook, result=original)
        # Should return None gracefully
        assert result is None

    def test_hook_does_not_import_connection(self):
        """Hook must NOT import _connection or SkillMcpManager."""
        from _skill_view_hook import create_hook
        import sys

        # Verify _connection is NOT in sys.modules from hook import
        # (it might be loaded by other tests, but the hook module itself
        #  shouldn't import it)
        hook_module = sys.modules.get("_skill_view_hook")
        assert hook_module is not None
        assert hook_module.__file__ is not None

        # Check the module's source for forbidden imports
        source = Path(hook_module.__file__).read_text()
        assert "from _connection import" not in source
        assert "import _connection" not in source
        assert "SkillMcpManager" not in source
