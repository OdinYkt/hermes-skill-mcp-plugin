"""Security module for hermes-skill-mcp plugin.

Environment filtering for MCP subprocesses, credential redaction in error
messages, and command denylist enforcement.
"""

from __future__ import annotations

import os
import re


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAFE_BASELINE_VARS: frozenset[str] = frozenset(
    (
        "PATH",
        "HOME",
        "USER",
        "SHELL",
        "TMPDIR",
        "LANG",
    )
)
"""Environment variables always inherited by MCP subprocess."""

DENIED_COMMANDS: frozenset[str] = frozenset(("sudo", "su"))
"""Commands rejected from mcp.yaml."""


# ---------------------------------------------------------------------------
# Credential redaction patterns (compiled once)
# ---------------------------------------------------------------------------

# Order matters: patterns are applied sequentially.
# "Bearer" must come before individual token patterns (sk-*, ghp_*)
# so that "Bearer sk-abc123" becomes "Bearer ***" instead of "Bearer ***"
# (same output either way, but Bearer-first is more explicit).
CredentialPattern = tuple[re.Pattern[str], str]

_CREDENTIAL_PATTERNS: tuple[CredentialPattern, ...] = (
    (re.compile(r"Bearer\s+\S+"), "Bearer ***"),
    (re.compile(r"\bghp_[a-zA-Z0-9]+"), "***"),
    (re.compile(r"\bsk-[a-zA-Z0-9]+"), "***"),
    (re.compile(r"key=\S+"), "key=***"),
    (re.compile(r"token=\S+"), "token=***"),
    (re.compile(r"password=\S+"), "password=***"),
    (re.compile(r"secret=\S+"), "secret=***"),
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def filter_mcp_environment(explicit_env: dict[str, str]) -> dict[str, str]:
    """Merge safe os.environ vars with explicit_env for MCP subprocess.

    Only ``SAFE_BASELINE_VARS`` are inherited from ``os.environ``.
    ``PATH``, ``HOME``, ``SHELL`` from *explicit_env* are appended
    (joined with ``os.pathsep``), not replaced. All other explicit
    vars are set or overwritten directly.

    Args:
        explicit_env: Environment variables declared in ``mcp.yaml``.

    Returns:
        Merged environment dictionary safe for MCP subprocess launch.
    """
    merged_env: dict[str, str] = {}

    # 1. Inherit only safe baseline vars from process environment
    for key in SAFE_BASELINE_VARS:
        env_value = os.environ.get(key)
        if env_value is not None:
            merged_env[key] = env_value

    # 2. Merge explicit vars, appending PATH / HOME / SHELL
    append_vars = ("PATH", "HOME", "SHELL")
    for key, explicit_value in explicit_env.items():
        if key in append_vars and key in merged_env:
            merged_env[key] = merged_env[key] + os.pathsep + explicit_value
        else:
            merged_env[key] = explicit_value

    return merged_env


def redact_credentials(text: str) -> str:
    """Replace credential patterns in *text* with ``***``.

    Patterns covered:

    * ``sk-*`` – OpenAI / API key prefixes
    * ``ghp_*`` – GitHub personal access tokens
    * ``Bearer *`` – Bearer authorization tokens
    * ``key=*``, ``token=*``, ``password=*``, ``secret=*`` – key-value secrets

    Patterns are case-sensitive for keyword names (e.g. ``KEY=`` is **not**
    redacted).

    Args:
        text: Input string that may contain credentials.

    Returns:
        *text* with credential values replaced by ``***``.
    """
    redacted_text = text
    for pattern, replacement in _CREDENTIAL_PATTERNS:
        redacted_text = pattern.sub(replacement, redacted_text)
    return redacted_text


def is_command_allowed(command: str) -> bool:
    """Check whether *command* is permitted as an MCP server command.

    Args:
        command: The ``command`` field from an ``mcp.yaml`` server entry.

    Returns:
        ``False`` if *command* appears in :data:`DENIED_COMMANDS`,
        ``True`` otherwise.
    """
    return command not in DENIED_COMMANDS
