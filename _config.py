"""mcp.yaml config parser for hermes-skill-mcp plugin.

Reads skill_dir/mcp.yaml, validates, normalizes, returns {server_name: server_config}.
Returns {} if no mcp.yaml, parse error, or invalid schema.
Never raises exceptions to caller.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Fields recognized in a server entry. Unknown fields silently ignored.
KNOWN_FIELDS: frozenset[str] = frozenset({
    "command",
    "args",
    "env",
    "url",
    "headers",
    "timeout",
    "connect_timeout",
    "idle_timeout",
})

# Default timeout values (seconds)
DEFAULT_TIMEOUT = 60
DEFAULT_CONNECT_TIMEOUT = 10
DEFAULT_IDLE_TIMEOUT = 300

# Max servers per mcp.yaml
MAX_SERVERS = 32

# Pattern for ${VAR} environment variable references
_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_mcp_sdk_available() -> bool:
    """Return True if ``import mcp`` succeeds, False otherwise.

    Used as ``check_fn`` for the ``skill-mcp`` toolset in Hermes.
    Result is NOT cached — each call re-checks the import.
    """
    try:
        import mcp  # noqa: F401
        return True
    except ImportError:
        return False


def parse_mcp_config(skill_dir: Path) -> dict[str, dict[str, Any]]:
    """Read *skill_dir*/mcp.yaml, validate, normalize, return server configs.

    Args:
        skill_dir: Path to a skill directory that MAY contain ``mcp.yaml``.

    Returns:
        ``{server_name: server_config}``.  Returns ``{}`` if ``mcp.yaml``
        does not exist, cannot be parsed, or contains no valid entries.
        Never raises an exception.
    """
    config_path = skill_dir / "mcp.yaml"

    # -- 1. No mcp.yaml → silent skip ----------------------------------------
    if not config_path.is_file():
        return {}

    # -- 2. Read & parse YAML -------------------------------------------------
    raw: dict[str, Any]
    try:
        import yaml
        raw_text = config_path.read_text(encoding="utf-8")
        raw = yaml.safe_load(raw_text)
    except Exception as exc:
        logger.warning(
            "skill-mcp: failed to parse mcp.yaml in %s: %s", skill_dir, exc
        )
        return {}

    if raw is None or not isinstance(raw, dict):
        return {}

    # -- 3. Process each server entry ----------------------------------------
    result: dict[str, dict[str, Any]] = {}

    for server_name, entry in raw.items():
        if not isinstance(server_name, str):
            logger.warning(
                "skill-mcp: non-string server name %r in %s — skipped",
                server_name,
                config_path,
            )
            continue
        if not isinstance(entry, dict):
            logger.warning(
                "skill-mcp: server entry for %r in %s is not a dict — skipped",
                server_name,
                config_path,
            )
            continue

        # -- 3a. Max servers check -------------------------------------------
        if len(result) >= MAX_SERVERS:
            logger.warning(
                "skill-mcp: too many MCP servers (%d), max %d. Truncated.",
                len(raw),
                MAX_SERVERS,
            )
            break

        # -- 3b. Validate command/url exclusivity ----------------------------
        has_command = "command" in entry
        has_url = "url" in entry
        if has_command == has_url:  # both True or both False
            logger.warning(
                "skill-mcp: server '%s' in %s must have exactly one of "
                "'command' or 'url' — skipped",
                server_name,
                config_path,
            )
            continue

        # -- 3c. Build normalized entry --------------------------------------
        normalized, resolved_paths = _build_normalized_entry(
            entry, config_path, skill_dir
        )

        # -- 3d. Path escape check -------------------------------------------
        if not _validate_paths(resolved_paths, skill_dir, server_name, config_path):
            continue
            continue  # rejected, warning already logged

        result[server_name] = normalized

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_normalized_entry(
    entry: dict[str, Any],
    config_path: Path,
    skill_dir: Path,
) -> tuple[dict[str, Any], set[Path]]:
    """Build a normalized server entry from raw YAML dict.

    Fills defaults, filters to known fields, expands env vars,
    resolves relative paths.  Returns (normalized_entry, resolved_paths).
    """
    normalized: dict[str, Any] = {}

    # -- Known fields --------------------------------------------------------
    for field in KNOWN_FIELDS:
        if field in entry:
            normalized[field] = entry[field]

    # -- Defaults -----------------------------------------------------------
    normalized.setdefault("args", [])
    normalized.setdefault("env", {})
    normalized.setdefault("headers", {})
    normalized.setdefault("timeout", DEFAULT_TIMEOUT)
    normalized.setdefault("connect_timeout", DEFAULT_CONNECT_TIMEOUT)
    normalized.setdefault("idle_timeout", DEFAULT_IDLE_TIMEOUT)

    # -- Env var expansion --------------------------------------------------
    normalized = _expand_env_vars(normalized)

    # -- Resolve relative paths in command/args -----------------------------
    normalized, resolved = _resolve_relative_paths(normalized, config_path.parent)

    return normalized, resolved


def _expand_env_vars(obj: Any) -> Any:
    """Recursively expand ``${VAR}`` references in strings using ``os.environ``."""
    if isinstance(obj, str):
        def _replacer(match: re.Match[str]) -> str:
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))
        return _ENV_VAR_PATTERN.sub(_replacer, obj)
    if isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_vars(item) for item in obj]
    return obj


def _resolve_relative_paths(
    config: dict[str, Any],
    base_dir: Path,
) -> tuple[dict[str, Any], set[Path]]:
    """Resolve relative paths in *command* and *args* to absolute paths.

    Only values that look like relative filesystem paths (contain a path
    separator and do not start with ``/``) are resolved.  Plain command
    names like ``uvx`` or ``python`` are left unchanged.

    Returns the updated config and a set of resolved paths (for later
    escape validation).
    """
    resolved: set[Path] = set()

    # Resolve command — only if it looks like a relative path
    if "command" in config:
        cmd = config["command"]
        if _is_relative_path(cmd):
            abs_cmd = (base_dir / cmd).resolve()
            config["command"] = str(abs_cmd)
            resolved.add(abs_cmd)

    # Resolve args
    if "args" in config:
        resolved_args: list[str] = []
        for arg in config["args"]:
            if _is_relative_path(arg):
                abs_arg = (base_dir / arg).resolve()
                resolved_args.append(str(abs_arg))
                resolved.add(abs_arg)
            else:
                resolved_args.append(arg)
        config["args"] = resolved_args

    return config, resolved


def _validate_paths(
    resolved_paths: set[Path],
    skill_dir: Path,
    server_name: str,
    config_path: Path,
) -> bool:
    """Check that resolved relative paths do not escape the skill directory.

    Only paths that were resolved from relative entries are checked.
    Absolute paths (e.g. ``/data/db.sqlite``) are trusted as explicit
    user intent and are NOT escape-checked.
    """
    skill_root = skill_dir.resolve()

    for p in resolved_paths:
        try:
            p.relative_to(skill_root)
        except ValueError:
            logger.warning(
                "skill-mcp: path '%s' escapes skill directory "
                "for server '%s' in %s — entry rejected",
                p,
                server_name,
                config_path,
            )
            return False

    return True


def _is_relative_path(value: str) -> bool:
    """Return True if *value* looks like a relative filesystem path."""
    return ("/" in value or "\\" in value) and not Path(value).is_absolute()
