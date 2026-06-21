"""transform_tool_result hook for skill_view augmentation.

Appends static MCP server config when skill_view is called for a skill
with mcp.yaml. No MCP handshake — static config display only.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


def create_hook(skill_dirs: list[str] | None = None) -> Callable[..., str | None]:
    """Return a transform_tool_result hook function.

    Args:
        skill_dirs: Skill directory paths (reserved for future use).
                    Currently unused — the hook reads the path from the
                    skill_view result directly.

    Returns:
        Hook function compatible with Hermes transform_tool_result contract.
        Returns str to replace result, or None to pass through.
    """
    # skill_dirs is accepted for API compatibility but not used — the hook
    # gets the skill path from the skill_view result's "path" field.
    _ = skill_dirs

    def hook(**kwargs: Any) -> str | None:
        try:
            return _transform(kwargs)
        except Exception:
            # Fail-open: exceptions are caught, original result preserved.
            logger.debug("skill_view hook error", exc_info=True)
            return None

    return hook


def _transform(kwargs: dict[str, Any]) -> str | None:
    """Core transform logic. Separated for clean exception boundary."""
    # -- 1. Only transform skill_view tool results ---------------------------
    tool_name = kwargs.get("tool_name")
    if tool_name != "skill_view":
        return None

    result = kwargs.get("result")
    if not isinstance(result, str):
        return None

    # -- 2. Parse result as JSON ---------------------------------------------
    try:
        parsed = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(parsed, dict):
        return None

    # -- 3. Check for "path" field and ok status -----------------------------
    if "path" not in parsed:
        return None

    # Error-status skill_view result → pass through
    if parsed.get("ok") is False:
        return None

    skill_path = Path(parsed["path"])
    if not skill_path.is_dir():
        return None

    # -- 4. Read mcp.yaml from skill path ------------------------------------
    from _config import parse_mcp_config

    config = parse_mcp_config(skill_path)
    if not config:
        return None

    # -- 5. Build MCP section ------------------------------------------------
    skill_name = skill_path.name
    mcp_section = _build_mcp_section(config, skill_name)

    # -- 6. Append to result -------------------------------------------------
    return result + "\n\n" + mcp_section


def _build_mcp_section(config: dict[str, dict[str, Any]], skill_name: str) -> str:
    """Build the MCP Servers section from parsed config.

    Args:
        config: Parsed mcp.yaml config (from parse_mcp_config).
        skill_name: Name of the skill (directory basename).

    Returns:
        Formatted markdown string with MCP server information.
    """
    lines: list[str] = ["## MCP Servers", ""]

    for server_name, server_config in config.items():
        lines.append(f"### {server_name}")
        lines.append("")
        lines.append("*Static config — connect on first `skill_mcp` call.*")
        lines.append("")
        lines.append("**Configuration:**")

        if "url" in server_config:
            # HTTP server
            lines.append(f"  url: {server_config['url']}")
            headers = server_config.get("headers", {})
            if headers:
                header_str = _format_headers(headers)
                lines.append(f"  headers: {header_str}")
        else:
            # Stdio server
            command = server_config.get("command", "")
            args = server_config.get("args", [])
            if args:
                lines.append(f"  command: {command} {' '.join(args)}")
            else:
                lines.append(f"  command: {command}")

        lines.append(f"  timeout: {server_config.get('timeout', 60)}s")
        lines.append(f"  connect_timeout: {server_config.get('connect_timeout', 10)}s")
        lines.append(f"  idle_timeout: {server_config.get('idle_timeout', 300)}s")
        lines.append("")
        lines.append(
            f'Use `skill_mcp(skill_name="{skill_name}", '
            f'mcp_name="{server_name}", '
            f'tool_name="...", '
            f'arguments={{...}})` to invoke.'
        )
        lines.append("")

    return "\n".join(lines)


def _format_headers(headers: dict[str, str]) -> str:
    """Format headers dict for display, redacting credential values.

    Args:
        headers: Header key-value pairs from mcp.yaml.

    Returns:
        Comma-separated string like "Authorization: Bearer ***, X-Custom: ***".
    """
    parts: list[str] = []
    for key, value in headers.items():
        redacted = _redact_header_value(str(value))
        parts.append(f"{key}: {redacted}")
    return ", ".join(parts)


def _redact_header_value(value: str) -> str:
    """Redact a single header value by masking credentials.

    Uses _security.redact_credentials if available, otherwise falls back
    to simple masking.
    """
    try:
        from _security import redact_credentials

        redacted = redact_credentials(value)
        if redacted != value:
            return redacted
    except ImportError:
        pass

    # Fallback: mask long values
    if len(value) > 8:
        return value[:4] + "***"
    return "***"
