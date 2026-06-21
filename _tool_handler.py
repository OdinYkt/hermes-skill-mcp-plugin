"""Async handler for the skill_mcp tool.

Module Interface
----------------
SKILL_MCP_SCHEMA : dict
    OpenAI function-calling schema for the skill_mcp tool.
create_handler(manager, skill_dirs=None) -> Callable
    Returns async handler function compatible with Hermes registry.
    skill_dirs: override skill search paths (default: platform defaults).
Handler: async def handler(args: dict, **kwargs) -> str
    Validates args, resolves skill MCP config, delegates to SkillMcpManager,
    returns standardised JSON result.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re as _re
from pathlib import Path as _Path
from typing import Any, Callable

try:
    from ._config import check_mcp_sdk_available, parse_mcp_config
    from ._security import redact_credentials
except ImportError:
    from _config import check_mcp_sdk_available, parse_mcp_config  # type: ignore[no-redef]
    from _security import redact_credentials  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exception hierarchy (shared interface for SkillMcpManager)
# ---------------------------------------------------------------------------


class McpError(Exception):
    """Base exception for MCP-related errors raised by SkillMcpManager."""


class McpConnectionError(McpError):
    """Connection to MCP server failed (command not found, timeout, etc.)."""


class McpToolNotFoundError(McpError):
    """Requested tool/resource/prompt not found on the MCP server."""


class McpToolExecutionError(McpError):
    """MCP tool execution failed with a runtime error."""


class McpServerExitedError(McpError):
    """MCP server process exited unexpectedly during a call."""


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SKILL_MCP_SCHEMA: dict = {
    "name": "skill_mcp",
    "description": (
        "Invoke MCP server operations from skill-embedded MCPs. "
        "Requires skill_name + mcp_name + exactly one of: tool_name, resource_name, prompt_name."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "skill_name": {"type": "string", "description": "Skill name as returned by skill_view"},
            "mcp_name": {"type": "string", "description": "MCP server name from skill's mcp.yaml"},
            "tool_name": {"type": "string", "description": "MCP tool to call"},
            "resource_name": {"type": "string", "description": "MCP resource URI to read"},
            "prompt_name": {"type": "string", "description": "MCP prompt to get"},
            "arguments": {"type": "object", "description": "Tool/prompt arguments as JSON object"},
            "grep": {"type": "string", "description": "Regex pattern to filter output lines"},
        },
        "required": ["skill_name", "mcp_name"],
    },
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_handler(
    manager: Any,  # SkillMcpManager
    skill_dirs: list[str] | None = None,
) -> Callable[..., Any]:
    """Return async handler for the skill_mcp tool.

    Args:
        manager: SkillMcpManager instance for connection lifecycle.
        skill_dirs: Override skill search paths.
            Default: ``[~/.hermes/skills, ~/.hermes/optional-skills]``.

    Returns:
        Async callable ``handler(args, **kwargs) -> str``.
    """
    resolved_skill_dirs: list[_Path] = _resolve_skill_dirs(skill_dirs)

    async def handler(args: dict, **kwargs: Any) -> str:
        return await _handle_skill_mcp(args, manager, resolved_skill_dirs, **kwargs)

    return handler


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_skill_dirs(skill_dirs: list[str] | None) -> list[_Path]:
    """Return resolved list of skill directories."""
    if skill_dirs is not None:
        return [_Path(d).expanduser().resolve() for d in skill_dirs]
    home = _Path.home()
    return [
        home / ".hermes" / "skills",
        home / ".hermes" / "optional-skills",
    ]


async def _handle_skill_mcp(
    args: dict,
    manager: Any,
    skill_dirs: list[_Path],
    **kwargs: Any,
) -> str:
    """Core handler logic for skill_mcp tool."""

    # -- 1. Argument validation -------------------------------------------------
    err = _validate_args(args)
    if err:
        return err

    skill_name = args["skill_name"]
    mcp_name = args["mcp_name"]

    # -- 2. MCP SDK availability check -----------------------------------------
    if not check_mcp_sdk_available():
        return _build_error(
            "MCP_SDK_MISSING",
            "MCP SDK not installed. Run: pip install mcp",
            retryable=False,
        )

    # -- 3. Skill lookup --------------------------------------------------------
    skill_dir = _find_skill_dir(skill_name, skill_dirs)
    if skill_dir is None:
        return _build_error(
            "SKILL_NOT_FOUND",
            f"Skill '{skill_name}' not found in skill directories.",
            retryable=False,
        )

    # -- 4. MCP config resolution ----------------------------------------------
    mcp_configs = parse_mcp_config(skill_dir)

    if not mcp_configs:
        return _build_error(
            "NO_MCP_CONFIG",
            f"Skill '{skill_name}' has no MCP servers configured.",
            retryable=False,
        )

    if mcp_name not in mcp_configs:
        available = ", ".join(sorted(mcp_configs.keys()))
        return _build_error(
            "MCP_NOT_FOUND",
            f"MCP server '{mcp_name}' not found in skill '{skill_name}'. Available: {available}",
            retryable=False,
        )

    config = mcp_configs[mcp_name]
    session_id = kwargs.get("session_id", "default")

    # -- 5. Session check -------------------------------------------------------
    if not session_id:
        return _build_error(
            "NO_SESSION",
            "No active session available for skill MCP call.",
            retryable=False,
        )

    # -- 6. Get or create MCP client -------------------------------------------
    client: Any
    try:
        client = await manager.get_or_create_client(
            session_id, skill_name, mcp_name, config
        )
    except McpConnectionError as exc:
        return _build_error(
            "MCP_CONNECT_FAILED",
            redact_credentials(str(exc)),
            retryable=True,
        )
    except McpServerExitedError as exc:
        return _build_error(
            "MCP_SERVER_EXITED",
            redact_credentials(str(exc)),
            retryable=True,
        )
    except RuntimeError as exc:
        msg = str(exc).lower()
        if "not support tools" in msg or "capabilit" in msg:
            return _build_error(
                "MCP_TOOLS_UNAVAILABLE",
                redact_credentials(str(exc)),
                retryable=False,
            )
        if "protocol" in msg or "version" in msg:
            return _build_error(
                "MCP_UNSUPPORTED_PROTOCOL",
                redact_credentials(str(exc)),
                retryable=False,
            )
        return _build_error(
            "MCP_CONNECT_FAILED",
            redact_credentials(str(exc)),
            retryable=True,
        )

    # -- 7. Execute MCP operation with timeout ---------------------------------
    tool_name = args.get("tool_name")
    resource_name = args.get("resource_name")
    prompt_name = args.get("prompt_name")
    call_arguments = args.get("arguments", {})
    timeout = config.get("timeout", 60)

    try:
        if tool_name:
            result = await asyncio.wait_for(
                client.call_tool(name=tool_name, arguments=call_arguments),
                timeout=timeout,
            )
        elif resource_name:
            result = await asyncio.wait_for(
                client.read_resource(uri=resource_name),
                timeout=timeout,
            )
        elif prompt_name:
            result = await asyncio.wait_for(
                client.get_prompt(name=prompt_name, arguments=call_arguments),
                timeout=timeout,
            )
        else:
            return _build_error(
                "INVALID_ARGS",
                "No operation specified.",
                retryable=False,
            )
    except asyncio.TimeoutError:
        return _build_error(
            "MCP_TOOL_TIMEOUT",
            f"Tool call timed out after {timeout}s on MCP server '{mcp_name}'.",
            retryable=True,
        )
    except McpToolNotFoundError as exc:
        return _build_error(
            "MCP_TOOL_NOT_FOUND",
            redact_credentials(str(exc)),
            retryable=False,
        )
    except McpToolExecutionError as exc:
        return _build_error(
            "MCP_TOOL_ERROR",
            redact_credentials(str(exc)),
            retryable=False,
        )
    except McpServerExitedError as exc:
        return _build_error(
            "MCP_SERVER_EXITED",
            redact_credentials(str(exc)),
            retryable=True,
        )

    # -- 7. Extract & filter output --------------------------------------------
    data = _extract_content(result)

    grep_pattern = args.get("grep")
    if grep_pattern and data:
        try:
            regex = _re.compile(grep_pattern)
            lines = data.split("\n")
            filtered = [line for line in lines if regex.search(line)]
            data = "\n".join(filtered)
        except _re.error:
            # Invalid regex → output unfiltered
            pass

    return json.dumps({"ok": True, "data": data})


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


def _validate_args(args: dict) -> str | None:
    """Validate handler arguments. Returns error JSON string or None."""
    skill_name = args.get("skill_name", "")
    if not isinstance(skill_name, str) or not skill_name:
        return _build_error(
            "INVALID_ARGS",
            "skill_name is required.",
            retryable=False,
        )

    mcp_name = args.get("mcp_name", "")
    if not isinstance(mcp_name, str) or not mcp_name:
        return _build_error(
            "INVALID_ARGS",
            "mcp_name is required.",
            retryable=False,
        )

    tool_name = args.get("tool_name")
    resource_name = args.get("resource_name")
    prompt_name = args.get("prompt_name")

    provided = [n for n in (tool_name, resource_name, prompt_name) if n]
    if len(provided) == 0:
        return _build_error(
            "INVALID_ARGS",
            "At least one of tool_name, resource_name, or prompt_name is required.",
            retryable=False,
        )

    if len(provided) > 1:
        return _build_error(
            "INVALID_ARGS",
            "Exactly one of tool_name, resource_name, or prompt_name is required.",
            retryable=False,
        )

    return None


# ---------------------------------------------------------------------------
# Skill directory lookup
# ---------------------------------------------------------------------------


def _find_skill_dir(skill_name: str, skill_dirs: list[_Path]) -> _Path | None:
    """Search skill_dirs for a directory named *skill_name* containing SKILL.md."""
    for base in skill_dirs:
        candidate = base / skill_name
        if candidate.is_dir() and (candidate / "SKILL.md").is_file():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Response formatting
# ---------------------------------------------------------------------------


def _build_error(error_code: str, message: str, *, retryable: bool) -> str:
    """Build a standardised error response JSON string."""
    return json.dumps(
        {
            "ok": False,
            "error_code": error_code,
            "message": message,
            "retryable": retryable,
        }
    )


# ---------------------------------------------------------------------------
# Content extraction
# ---------------------------------------------------------------------------


def _extract_content(result: Any) -> str:
    """Extract text content from an MCP result object.

    Handles ``CallToolResult``, ``ReadResourceResult``,
    ``GetPromptResult``, and plain strings.
    """
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if hasattr(result, "content"):
        parts: list[str] = []
        for item in result.content:
            if isinstance(item, str):
                parts.append(item)
            elif hasattr(item, "text"):
                parts.append(item.text)
            elif hasattr(item, "data"):
                parts.append(str(item.data))
        return "\n".join(parts) if parts else str(result)
    if hasattr(result, "messages"):
        return str(result.messages)
    return str(result)
