"""Tests for _security module."""

from __future__ import annotations

import os
from unittest.mock import patch

from _security import (
    DENIED_COMMANDS,
    SAFE_BASELINE_VARS,
    filter_mcp_environment,
    is_command_allowed,
    redact_credentials,
)


PATH_KEY = "PATH"
HOME_KEY = "HOME"
USER_KEY = "USER"
SHELL_KEY = "SHELL"
TMPDIR_KEY = "TMPDIR"
LANG_KEY = "LANG"


def base_safe_env() -> dict[str, str]:
    return {
        PATH_KEY: "/usr/bin:/usr/local/bin",
        HOME_KEY: "/home/testuser",
        USER_KEY: "testuser",
        SHELL_KEY: "/bin/bash",
        TMPDIR_KEY: "/tmp",
        LANG_KEY: "en_US.UTF-8",
    }


class TestSafeBaselineVars:
    def test_contains_minimum_required_vars(self):
        for key in (PATH_KEY, HOME_KEY, USER_KEY, TMPDIR_KEY, LANG_KEY):
            assert key in SAFE_BASELINE_VARS

    def test_is_set_type(self):
        assert isinstance(SAFE_BASELINE_VARS, set)


class TestDeniedCommands:
    def test_contains_sudo(self):
        assert "sudo" in DENIED_COMMANDS

    def test_contains_su(self):
        assert "su" in DENIED_COMMANDS

    def test_is_set_type(self):
        assert isinstance(DENIED_COMMANDS, set)


class TestFilterMcpEnvironment:
    def test_empty_env(self):
        with patch.dict(os.environ, base_safe_env(), clear=True):
            env = filter_mcp_environment({})

        assert env == base_safe_env()

    def test_path_override_appends(self):
        with patch.dict(os.environ, base_safe_env(), clear=True):
            env = filter_mcp_environment({PATH_KEY: "/custom/bin"})

        expected = os.pathsep.join([base_safe_env()[PATH_KEY], "/custom/bin"])
        assert env[PATH_KEY] == expected

    def test_explicit_env_vars_are_in_output(self):
        with patch.dict(os.environ, base_safe_env(), clear=True):
            env = filter_mcp_environment({"MY_CUSTOM_VAR": "custom_value"})

        assert env["MY_CUSTOM_VAR"] == "custom_value"
        assert env["USER"] == "testuser"


class TestRedactCredentials:
    def test_bearer_sk_token(self):
        assert redact_credentials("Bearer sk-abc123") == "Bearer ***"

    def test_github_pat_standalone(self):
        assert redact_credentials("ghp_1234567890abcdef") == "***"

    def test_key_value(self):
        assert redact_credentials("key=supersecret") == "key=***"

    def test_mixed_secrets_and_normal_text(self):
        text = "\n".join([
            "Error: key=abc123",
            "Connection failed with password=secret!",
            "Retry with token=xyz789.",
        ])
        redacted = redact_credentials(text)

        assert "key=***" in redacted
        assert "password=***" in redacted
        assert "token=***" in redacted
        assert "abc123" not in redacted
        assert "xyz789" not in redacted

    def test_keyboard_not_redacted(self):
        assert redact_credentials("keyboard shortcut") == "keyboard shortcut"


class TestIsCommandAllowed:
    def test_allowed_commands(self):
        for cmd in ("uvx", "npx", "python", "node", "docker"):
            assert is_command_allowed(cmd) is True

    def test_denied_commands(self):
        for cmd in ("sudo", "su"):
            assert is_command_allowed(cmd) is False
