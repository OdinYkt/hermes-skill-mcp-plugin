"""Tests for _security module — environment filtering, credential redaction, command denylist."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from _security import (
    SAFE_BASELINE_VARS,
    DENIED_COMMANDS,
    filter_mcp_environment,
    redact_credentials,
    is_command_allowed,
)


# ============================================================================
# SAFE_BASELINE_VARS
# ============================================================================


class TestSafeBaselineVars:
    """Verify SAFE_BASELINE_VARS contains minimum required set."""

    def test_contains_minimum_required_vars(self):
        assert "PATH" in SAFE_BASELINE_VARS
        assert "HOME" in SAFE_BASELINE_VARS
        assert "USER" in SAFE_BASELINE_VARS
        assert "TMPDIR" in SAFE_BASELINE_VARS
        assert "LANG" in SAFE_BASELINE_VARS

    def test_is_set_type(self):
        assert isinstance(SAFE_BASELINE_VARS, set)


# ============================================================================
# DENIED_COMMANDS
# ============================================================================


class TestDeniedCommands:
    """Verify DENIED_COMMANDS contains minimum required entries."""

    def test_contains_sudo(self):
        assert "sudo" in DENIED_COMMANDS

    def test_contains_su(self):
        assert "su" in DENIED_COMMANDS

    def test_is_set_type(self):
        assert isinstance(DENIED_COMMANDS, set)


# ============================================================================
# filter_mcp_environment
# ============================================================================


class TestFilterMcpEnvironment:
    """Tests for filter_mcp_environment(explicit_env)."""

    BASE_SAFE_ENV = {
        "PATH": "/usr/bin:/usr/local/bin",
        "HOME": "/home/testuser",
        "USER": "testuser",
        "SHELL": "/bin/bash",
        "TMPDIR": "/tmp",
        "LANG": "en_US.UTF-8",
    }

    # --- empty explicit_env ---

    def test_empty_explicit_env_returns_only_safe_vars(self):
        """Only SAFE_BASELINE_VARS from os.environ are returned."""
        with patch.dict(os.environ, self.BASE_SAFE_ENV, clear=True):
            result = filter_mcp_environment({})

        assert result == self.BASE_SAFE_ENV

    # --- PATH override appends, not replaces ---

    def test_path_override_appends_not_replaces(self):
        with patch.dict(os.environ, self.BASE_SAFE_ENV, clear=True):
            result = filter_mcp_environment({"PATH": "/custom/bin"})

        expected = self.BASE_SAFE_ENV["PATH"] + os.pathsep + "/custom/bin"
        assert result["PATH"] == expected

    def test_home_override_appends_not_replaces(self):
        with patch.dict(os.environ, self.BASE_SAFE_ENV, clear=True):
            result = filter_mcp_environment({"HOME": "/extra/home"})

        expected = self.BASE_SAFE_ENV["HOME"] + os.pathsep + "/extra/home"
        assert result["HOME"] == expected

    def test_shell_override_appends_not_replaces(self):
        with patch.dict(os.environ, self.BASE_SAFE_ENV, clear=True):
            result = filter_mcp_environment({"SHELL": "/usr/bin/zsh"})

        expected = self.BASE_SAFE_ENV["SHELL"] + os.pathsep + "/usr/bin/zsh"
        assert result["SHELL"] == expected

    def test_append_only_var_when_not_in_os_environ_sets_directly(self):
        """If PATH not in os.environ, explicit PATH is used as-is."""
        env_no_path = {k: v for k, v in self.BASE_SAFE_ENV.items() if k != "PATH"}
        with patch.dict(os.environ, env_no_path, clear=True):
            result = filter_mcp_environment({"PATH": "/standalone/path"})

        assert result["PATH"] == "/standalone/path"

    # --- explicit_env vars pass through ---

    def test_explicit_env_vars_are_in_output(self):
        with patch.dict(os.environ, self.BASE_SAFE_ENV, clear=True):
            result = filter_mcp_environment({
                "MY_CUSTOM_VAR": "custom_value",
                "ANOTHER_VAR": "42",
            })

        assert result["MY_CUSTOM_VAR"] == "custom_value"
        assert result["ANOTHER_VAR"] == "42"
        # Safe vars still present
        assert result["USER"] == "testuser"

    # --- secret vars from os.environ NOT leaked ---

    def test_api_key_not_leaked(self):
        env = {**self.BASE_SAFE_ENV, "API_KEY": "sk-super-secret"}
        with patch.dict(os.environ, env, clear=True):
            result = filter_mcp_environment({})
        assert "API_KEY" not in result

    def test_token_not_leaked(self):
        env = {**self.BASE_SAFE_ENV, "TOKEN": "ghp_secret_token"}
        with patch.dict(os.environ, env, clear=True):
            result = filter_mcp_environment({})
        assert "TOKEN" not in result

    def test_password_not_leaked(self):
        env = {**self.BASE_SAFE_ENV, "PASSWORD": "hunter2"}
        with patch.dict(os.environ, env, clear=True):
            result = filter_mcp_environment({})
        assert "PASSWORD" not in result

    def test_other_random_vars_not_leaked(self):
        """Any var not in SAFE_BASELINE_VARS should not appear."""
        env = {**self.BASE_SAFE_ENV, "DATABASE_URL": "postgres://localhost"}
        with patch.dict(os.environ, env, clear=True):
            result = filter_mcp_environment({})
        assert "DATABASE_URL" not in result

    # --- missing safe vars in os.environ ---

    def test_missing_safe_var_in_os_environ_is_skipped(self):
        env = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "USER": "testuser",
            "LANG": "en_US.UTF-8",
            # TMPDIR is missing
        }
        with patch.dict(os.environ, env, clear=True):
            result = filter_mcp_environment({})
        assert "TMPDIR" not in result

    # --- explicit_env can introduce vars that override safe baseline names ---

    def test_explicit_env_overwrites_safe_var_when_not_append_only(self):
        """Non-append vars from explicit_env replace safe baseline values."""
        with patch.dict(os.environ, self.BASE_SAFE_ENV, clear=True):
            result = filter_mcp_environment({"USER": "override_user"})

        assert result["USER"] == "override_user"


# ============================================================================
# redact_credentials
# ============================================================================


class TestRedactCredentials:
    """Tests for redact_credentials(text)."""

    # --- bear patterns from spec ---

    def test_bearer_sk_token(self):
        assert redact_credentials("Bearer sk-abc123") == "Bearer ***"

    def test_bearer_ghp_token(self):
        assert redact_credentials("Authorization: Bearer ghp_abcdef123456") == "Authorization: Bearer ***"

    def test_bearer_generic_token(self):
        assert redact_credentials("Bearer some-random-token-12345") == "Bearer ***"

    # --- standalone token patterns ---

    def test_github_pat_standalone(self):
        assert redact_credentials("ghp_1234567890abcdef") == "***"

    def test_sk_token_standalone(self):
        assert redact_credentials("sk-abc123def456") == "***"

    # --- key=value patterns ---

    def test_key_value(self):
        assert redact_credentials("key=supersecret") == "key=***"

    def test_token_value(self):
        assert redact_credentials("token=mysecrettoken") == "token=***"

    def test_password_value(self):
        assert redact_credentials("password=hunter2") == "password=***"

    def test_secret_value(self):
        assert redact_credentials("secret=classified") == "secret=***"

    # --- no change for normal text ---

    def test_normal_text_unchanged(self):
        assert redact_credentials("Connection failed") == "Connection failed"

    def test_empty_string(self):
        assert redact_credentials("") == ""

    # --- mixed content ---

    def test_mixed_secrets_and_normal_text(self):
        text = (
            "Error: key=abc123\n"
            "Connection to server failed with password=secret!\n"
            "Retry with token=xyz789."
        )
        result = redact_credentials(text)

        assert "key=***" in result
        assert "password=***" in result
        assert "token=***" in result
        assert "Error:" in result
        assert "Connection to server failed with" in result
        assert "Retry with" in result
        # Original secret values must be gone
        assert "abc123" not in result
        assert "xyz789" not in result

    def test_multiple_secrets_same_line(self):
        result = redact_credentials("key=abc secret=xyz token=123")
        assert result == "key=*** secret=*** token=***"

    # --- no false positives ---

    def test_keyboard_not_redacted(self):
        """'keyboard' does not match 'key='."""
        assert redact_credentials("keyboard shortcut") == "keyboard shortcut"

    def test_tokenizer_not_redacted(self):
        """'tokenizer' does not match 'token='."""
        assert redact_credentials("tokenizer output") == "tokenizer output"

    def test_passwordless_not_redacted(self):
        """'passwordless' does not match 'password='."""
        assert redact_credentials("passwordless auth") == "passwordless auth"

    # --- case sensitivity ---

    def test_lowercase_bearer_still_redacts_sk(self):
        """sk- token inside lowercase 'bearer' still redacted by sk- pattern."""
        result = redact_credentials("bearer sk-abc123")
        assert result == "bearer ***"

    def test_uppercase_key_not_redacted(self):
        """KEY= is NOT redacted — patterns are case-sensitive for key names."""
        result = redact_credentials("KEY=supersecret")
        assert result == "KEY=supersecret"

    # --- partial values with spaces ---

    def test_password_with_spaces_in_value(self):
        """Only the first word of password value is redacted."""
        result = redact_credentials("password=value with spaces")
        assert result == "password=*** with spaces"


# ============================================================================
# is_command_allowed
# ============================================================================


class TestIsCommandAllowed:
    """Tests for is_command_allowed(command)."""

    def test_uvx_allowed(self):
        assert is_command_allowed("uvx") is True

    def test_npx_allowed(self):
        assert is_command_allowed("npx") is True

    def test_python_allowed(self):
        assert is_command_allowed("python") is True

    def test_node_allowed(self):
        assert is_command_allowed("node") is True

    def test_docker_allowed(self):
        assert is_command_allowed("docker") is True

    def test_sudo_denied(self):
        assert is_command_allowed("sudo") is False

    def test_su_denied(self):
        assert is_command_allowed("su") is False

    def test_unknown_command_allowed(self):
        """Any command not in DENIED_COMMANDS is allowed."""
        assert is_command_allowed("some-random-binary") is True
