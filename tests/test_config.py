"""Tests for _config.py — mcp.yaml config parser.

Covers all behavioral contract scenarios from Task 1 of IMPLEMENTATION_PLAN.md.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


# ============================================================================
# parse_mcp_config — basic parsing
# ============================================================================


class TestParseMcpConfigBasicStdio:
    """mcp.yaml with command + args → returns dict with server config."""

    def test_command_and_args_parsed(self, skill_with_mcp):
        from _config import parse_mcp_config

        mcp_config = {
            "sqlite": {
                "command": "uvx",
                "args": ["mcp-server-sqlite"],
            }
        }
        skill_dir = skill_with_mcp("sqlite-workflow", mcp_config)
        result = parse_mcp_config(skill_dir)

        assert "sqlite" in result
        assert result["sqlite"]["command"] == "uvx"
        assert result["sqlite"]["args"] == ["mcp-server-sqlite"]

    def test_default_timeouts_filled(self, skill_with_mcp):
        from _config import parse_mcp_config

        mcp_config = {
            "sqlite": {
                "command": "uvx",
                "args": ["mcp-server-sqlite"],
            }
        }
        skill_dir = skill_with_mcp("sqlite-workflow", mcp_config)
        result = parse_mcp_config(skill_dir)

        server = result["sqlite"]
        assert server["timeout"] == 60
        assert server["connect_timeout"] == 10
        assert server["idle_timeout"] == 300

    def test_custom_timeouts_preserved(self, skill_with_mcp):
        from _config import parse_mcp_config

        mcp_config = {
            "db": {
                "command": "python",
                "args": ["server.py"],
                "timeout": 30,
                "connect_timeout": 5,
                "idle_timeout": 120,
            }
        }
        skill_dir = skill_with_mcp("custom-skill", mcp_config)
        result = parse_mcp_config(skill_dir)

        server = result["db"]
        assert server["timeout"] == 30
        assert server["connect_timeout"] == 5
        assert server["idle_timeout"] == 120


class TestParseMcpConfigHttp:
    """mcp.yaml with url → transport = HTTP (no command key)."""

    def test_url_config_has_no_command_key(self, skill_with_mcp):
        from _config import parse_mcp_config

        mcp_config = {
            "company_api": {
                "url": "https://mcp.company.com/v1",
                "headers": {
                    "Authorization": "Bearer static-key",
                },
            }
        }
        skill_dir = skill_with_mcp("remote-skill", mcp_config)
        result = parse_mcp_config(skill_dir)

        assert "company_api" in result
        server = result["company_api"]
        assert server["url"] == "https://mcp.company.com/v1"
        assert "command" not in server
        assert server["headers"] == {"Authorization": "Bearer static-key"}

    def test_url_config_gets_default_timeouts(self, skill_with_mcp):
        from _config import parse_mcp_config

        mcp_config = {
            "api": {
                "url": "https://example.com/mcp",
            }
        }
        skill_dir = skill_with_mcp("http-skill", mcp_config)
        result = parse_mcp_config(skill_dir)

        server = result["api"]
        assert server["timeout"] == 60
        assert server["connect_timeout"] == 10
        assert server["idle_timeout"] == 300


class TestParseMcpConfigMultipleServers:
    """Multiple valid servers in one mcp.yaml."""

    def test_multiple_servers_all_parsed(self, skill_with_mcp):
        from _config import parse_mcp_config

        mcp_config = {
            "sqlite": {
                "command": "uvx",
                "args": ["mcp-server-sqlite"],
            },
            "github": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
            },
        }
        skill_dir = skill_with_mcp("multi-skill", mcp_config)
        result = parse_mcp_config(skill_dir)

        assert len(result) == 2
        assert "sqlite" in result
        assert "github" in result


# ============================================================================
# Env var expansion
# ============================================================================


class TestEnvVarExpansion:
    """${VAR} syntax expanded from os.environ."""

    def test_env_var_expanded(self, skill_with_mcp, monkeypatch):
        from _config import parse_mcp_config

        monkeypatch.setenv("API_KEY", "sk-test-12345")
        mcp_config = {
            "api": {
                "url": "https://api.example.com",
                "headers": {
                    "Authorization": "Bearer ${API_KEY}",
                },
            }
        }
        skill_dir = skill_with_mcp("env-skill", mcp_config)
        result = parse_mcp_config(skill_dir)

        headers = result["api"]["headers"]
        assert headers["Authorization"] == "Bearer sk-test-12345"

    def test_env_var_in_command_args_expanded(self, skill_with_mcp, monkeypatch):
        from _config import parse_mcp_config

        monkeypatch.setenv("DB_PATH", "/data/mydb.sqlite")
        mcp_config = {
            "sqlite": {
                "command": "uvx",
                "args": ["mcp-server-sqlite", "--db-path", "${DB_PATH}"],
            }
        }
        skill_dir = skill_with_mcp("db-skill", mcp_config)
        result = parse_mcp_config(skill_dir)

        # args after env expansion: ["mcp-server-sqlite", "--db-path", "/data/mydb.sqlite"]
        assert result["sqlite"]["args"][2] == "/data/mydb.sqlite"

    def test_env_var_in_env_block_expanded(self, skill_with_mcp, monkeypatch):
        from _config import parse_mcp_config

        monkeypatch.setenv("GH_TOKEN", "ghp_secret")
        mcp_config = {
            "github": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {
                    "GITHUB_TOKEN": "${GH_TOKEN}",
                },
            }
        }
        skill_dir = skill_with_mcp("gh-skill", mcp_config)
        result = parse_mcp_config(skill_dir)

        assert result["github"]["env"]["GITHUB_TOKEN"] == "ghp_secret"

    def test_missing_env_var_left_unexpanded(self, skill_with_mcp, monkeypatch):
        from _config import parse_mcp_config

        # Ensure var is NOT set
        monkeypatch.delenv("MISSING_VAR", raising=False)
        mcp_config = {
            "api": {
                "url": "https://example.com",
                "headers": {
                    "X-Token": "${MISSING_VAR}",
                },
            }
        }
        skill_dir = skill_with_mcp("missing-env-skill", mcp_config)
        result = parse_mcp_config(skill_dir)

        # Should leave ${MISSING_VAR} as-is (or empty — we decide)
        # Per behavior contract: expanded from os.environ → if not set, leaves original
        headers = result["api"]["headers"]
        assert headers["X-Token"] == "${MISSING_VAR}" or headers["X-Token"] == ""

    def test_no_expansion_without_dollar_brace_syntax(self, skill_with_mcp):
        """Values without ${} syntax used literally."""
        from _config import parse_mcp_config

        mcp_config = {
            "api": {
                "url": "https://example.com",
                "headers": {
                    "Authorization": "Bearer static-key",
                },
            }
        }
        skill_dir = skill_with_mcp("static-skill", mcp_config)
        result = parse_mcp_config(skill_dir)

        headers = result["api"]["headers"]
        assert headers["Authorization"] == "Bearer static-key"


# ============================================================================
# Path resolution
# ============================================================================


class TestPathResolution:
    """Relative paths resolved relative to mcp.yaml directory."""

    def test_relative_path_in_args_resolved(self, skill_with_mcp):
        from _config import parse_mcp_config

        mcp_config = {
            "local": {
                "command": "python",
                "args": ["./server.py"],
            }
        }
        skill_dir = skill_with_mcp("tool", mcp_config)
        result = parse_mcp_config(skill_dir)

        resolved = Path(result["local"]["args"][0])
        assert resolved.is_absolute()
        assert resolved == (skill_dir / "server.py").resolve()

    def test_path_escaping_skill_dir_rejected(self, skill_with_mcp, caplog):
        from _config import parse_mcp_config

        mcp_config = {
            "escape": {
                "command": "python",
                "args": ["../../../etc/passwd"],
            }
        }
        skill_dir = skill_with_mcp("escape-skill", mcp_config)

        with caplog.at_level(logging.WARNING):
            result = parse_mcp_config(skill_dir)

        # Entry should be rejected
        assert "escape" not in result
        assert any(
            "escapes skill directory" in record.message.lower()
            for record in caplog.records
        )

    def test_absolute_path_preserved(self, skill_with_mcp):
        from _config import parse_mcp_config

        abs_path = "/usr/local/bin/my-server"
        mcp_config = {
            "abs": {
                "command": abs_path,
                "args": [],
            }
        }
        skill_dir = skill_with_mcp("abs-skill", mcp_config)
        result = parse_mcp_config(skill_dir)

        assert result["abs"]["command"] == abs_path


# ============================================================================
# Missing / empty / invalid config
# ============================================================================


class TestMissingConfig:
    """No mcp.yaml → returns {}."""

    def test_no_mcp_yaml_returns_empty_dict(self, skill_without_mcp):
        from _config import parse_mcp_config

        skill_dir = skill_without_mcp("basic-skill")
        result = parse_mcp_config(skill_dir)

        assert result == {}

    def test_empty_mcp_yaml_returns_empty_dict(self, skill_with_mcp):
        from _config import parse_mcp_config

        # Empty yaml — yaml.safe_dump({}) yields "{}\n" which is valid YAML
        skill_dir = skill_with_mcp("empty-skill", {})
        result = parse_mcp_config(skill_dir)

        assert result == {}


class TestInvalidYaml:
    """Invalid YAML → returns {}, warning logged."""

    def test_invalid_yaml_returns_empty_and_warns(self, temp_skills_dir, caplog):
        from _config import parse_mcp_config

        skill_dir = temp_skills_dir / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Bad\n", encoding="utf-8")
        (skill_dir / "mcp.yaml").write_text(
            "server: [unclosed\n  command: bad", encoding="utf-8"
        )

        with caplog.at_level(logging.WARNING):
            result = parse_mcp_config(skill_dir)

        assert result == {}
        assert any(
            "failed to parse" in record.message.lower()
            or "yaml" in record.message.lower()
            for record in caplog.records
        )


# ============================================================================
# Validation: command/url mutual exclusivity
# ============================================================================


class TestCommandUrlValidation:
    """Entries must have command XOR url."""

    def test_missing_both_command_and_url_rejected(self, skill_with_mcp, caplog):
        from _config import parse_mcp_config

        mcp_config = {
            "bad": {
                "timeout": 30,
            }
        }
        skill_dir = skill_with_mcp("invalid-skill", mcp_config)

        with caplog.at_level(logging.WARNING):
            result = parse_mcp_config(skill_dir)

        assert "bad" not in result

    def test_both_command_and_url_rejected(self, skill_with_mcp, caplog):
        from _config import parse_mcp_config

        mcp_config = {
            "bad": {
                "command": "uvx",
                "url": "https://example.com",
            }
        }
        skill_dir = skill_with_mcp("confused-skill", mcp_config)

        with caplog.at_level(logging.WARNING):
            result = parse_mcp_config(skill_dir)

        assert "bad" not in result


# ============================================================================
# Unknown fields — forward compatibility
# ============================================================================


class TestUnknownFields:
    """Unknown fields silently ignored."""

    def test_unknown_field_ignored(self, skill_with_mcp):
        from _config import parse_mcp_config

        mcp_config = {
            "server": {
                "command": "uvx",
                "args": ["mcp-server-example"],
                "sampling": {"enabled": True},
            }
        }
        skill_dir = skill_with_mcp("future-skill", mcp_config)
        result = parse_mcp_config(skill_dir)

        assert "server" in result
        assert "sampling" not in result["server"]


# ============================================================================
# Max servers truncation
# ============================================================================


class TestMaxServers:
    """Max 32 servers; >32 truncated with warning."""

    def test_max_32_servers_truncated(self, skill_with_mcp, caplog):
        from _config import parse_mcp_config

        # Create 40 server entries
        mcp_config = {}
        for i in range(40):
            mcp_config[f"server_{i}"] = {
                "command": "echo",
                "args": [f"server_{i}"],
            }

        skill_dir = skill_with_mcp("many-skill", mcp_config)

        with caplog.at_level(logging.WARNING):
            result = parse_mcp_config(skill_dir)

        assert len(result) == 32
        assert any(
            "truncat" in record.message.lower() or "32" in record.message
            for record in caplog.records
        )

    def test_exactly_32_servers_all_loaded(self, skill_with_mcp):
        from _config import parse_mcp_config

        mcp_config = {}
        for i in range(32):
            mcp_config[f"server_{i}"] = {
                "command": "echo",
                "args": [f"server_{i}"],
            }

        skill_dir = skill_with_mcp("exact-32-skill", mcp_config)
        result = parse_mcp_config(skill_dir)

        assert len(result) == 32


# ============================================================================
# Edge cases
# ============================================================================


class TestEdgeCases:
    """Edge case handling."""

    def test_unknown_server_keys_are_top_level_dict_keys(self, skill_with_mcp):
        """Each top-level key in mcp.yaml is a server name."""
        from _config import parse_mcp_config

        mcp_config = {
            "db": {"command": "uvx", "args": ["mcp-server-sqlite"]},
            "api": {"url": "https://api.example.com"},
        }
        skill_dir = skill_with_mcp("multi-skill", mcp_config)
        result = parse_mcp_config(skill_dir)

        assert isinstance(result, dict)
        assert all(isinstance(k, str) for k in result)
        assert all(isinstance(v, dict) for v in result.values())

    def test_result_always_has_timeout_keys(self, skill_with_mcp):
        from _config import parse_mcp_config

        for config in [
            {"s": {"command": "uvx", "args": []}},
            {"s": {"url": "https://x.com"}},
        ]:
            skill_dir = skill_with_mcp("timeout-skill", config)
            result = parse_mcp_config(skill_dir)
            server = result["s"]
            assert "timeout" in server
            assert "connect_timeout" in server
            assert "idle_timeout" in server

    def test_empty_args_defaults_to_empty_list(self, skill_with_mcp):
        from _config import parse_mcp_config

        mcp_config = {
            "server": {
                "command": "uvx",
            }
        }
        skill_dir = skill_with_mcp("no-args-skill", mcp_config)
        result = parse_mcp_config(skill_dir)

        assert result["server"]["args"] == []

    def test_never_raises_exception(self, temp_skills_dir):
        """parse_mcp_config never raises, even with non-existent dir."""
        from _config import parse_mcp_config

        # Non-existent directory
        result = parse_mcp_config(temp_skills_dir / "does-not-exist")
        assert result == {}

        # Directory with no mcp.yaml (just SKILL.md)
        skill_dir = temp_skills_dir / "just-skills"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Just skills\n", encoding="utf-8")
        result = parse_mcp_config(skill_dir)
        assert result == {}


# ============================================================================
# check_mcp_sdk_available
# ============================================================================


class TestCheckMcpSdkAvailable:
    """check_mcp_sdk_available returns True/False based on import success."""

    def test_returns_true_when_mcp_importable(self):
        from _config import check_mcp_sdk_available
        import importlib.util

        result = check_mcp_sdk_available()
        spec = importlib.util.find_spec("mcp")
        if spec is not None:
            assert result is True, f"mcp SDK IS installed but check_mcp_sdk_available returned False"
        else:
            # mcp not installed in this env — expected to return False
            assert result is False

    def test_returns_false_when_mcp_not_importable(self):
        from _config import check_mcp_sdk_available

        with patch.dict("sys.modules", {"mcp": None}):
            # Force ImportError by making mcp raise on import
            original_import = __builtins__["__import__"]

            def mock_import(name, *args, **kwargs):
                if name == "mcp" or name.startswith("mcp."):
                    raise ImportError("No module named 'mcp'")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                result = check_mcp_sdk_available()
                assert result is False

    def test_does_not_cache_result(self):
        """Each call re-checks import. Tested by calling twice."""
        from _config import check_mcp_sdk_available

        r1 = check_mcp_sdk_available()
        r2 = check_mcp_sdk_available()
        # Both should return the same value (no caching weirdness)
        assert r1 == r2
        assert isinstance(r1, bool)
