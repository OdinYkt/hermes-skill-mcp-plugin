"""Lazy MCP connection manager for hermes-skill-mcp plugin.

Manages persistent MCP client sessions via AsyncExitStack lifecycle.
Connections are created on first use and cached by session/skill/server key.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

logger = logging.getLogger(__name__)


class SkillMcpManager:
    """Manages lazy, persistent MCP client connections.

    Connections are keyed by ``{session_id}:{skill_name}:{mcp_name}``.
    Each connection is held open via ``contextlib.AsyncExitStack`` so that
    both the transport and the ClientSession stay alive across multiple
    tool calls.

    MCP SDK imports are deferred — no import error at module load time
    if the ``mcp`` package is not installed.
    """

    def __init__(self) -> None:
        # cache: key → (ClientSession, AsyncExitStack)
        self._cache: dict[str, tuple[Any, contextlib.AsyncExitStack]] = {}
        # Per-key locks to prevent concurrent creation of same connection
        self._locks: dict[str, asyncio.Lock] = {}
        # Per-key idle cleanup tasks
        self._idle_tasks: dict[str, asyncio.Task[None]] = {}
        self._sleep = asyncio.sleep

    @staticmethod
    def _make_key(session_id: str, skill_name: str, mcp_name: str) -> str:
        """Build the cache key for a connection."""
        return f"{session_id}:{skill_name}:{mcp_name}"

    async def get_or_create_client(
        self,
        session_id: str,
        skill_name: str,
        mcp_name: str,
        config: dict[str, Any],
    ) -> Any:
        """Get a cached MCP client session or create a new one.

        Args:
            session_id: Hermes session identifier.
            skill_name: Skill directory name.
            mcp_name: MCP server name from ``mcp.yaml``.
            config: Normalized server config dict from
                :func:`_config.parse_mcp_config`.

        Returns:
            An initialized ``mcp.ClientSession`` ready for tool calls.

        Raises:
            RuntimeError: If the ``mcp`` SDK is not installed.
            RuntimeError: If the server lacks ``tools`` capability.
            Exception: Connection/initialization errors propagate directly.
        """
        key = self._make_key(session_id, skill_name, mcp_name)

        # Fast path: cached
        if key in self._cache:
            session, _stack = self._cache[key]
            self._schedule_idle_disconnect(
                key,
                session_id,
                skill_name,
                mcp_name,
                config.get("idle_timeout", 300),
            )
            return session

        # Serialize creation for the same key
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()

        async with self._locks[key]:
            # Double-check after acquiring lock
            if key in self._cache:
                session, _stack = self._cache[key]
                return session

            # Deferred MCP SDK import
            try:
                from mcp import ClientSession
            except ImportError:
                raise RuntimeError("MCP SDK not installed") from None

            stack = contextlib.AsyncExitStack()

            try:
                if "command" in config:
                    # --- stdio transport ---
                    from mcp.client.stdio import (
                        StdioServerParameters,
                        stdio_client,
                    )
                    from _security import filter_mcp_environment, is_command_allowed

                    if not is_command_allowed(config["command"]):
                        raise RuntimeError(
                            f"Command '{config['command']}' is not allowed for MCP server '{mcp_name}'"
                        )

                    server_params = StdioServerParameters(
                        command=config["command"],
                        args=config.get("args", []),
                        env=filter_mcp_environment(config.get("env", {})),
                    )
                    read, write = await stack.enter_async_context(
                        stdio_client(server_params)
                    )
                elif "url" in config:
                    # --- HTTP transport ---
                    from mcp.client.streamable_http import streamablehttp_client

                    read, write, _get_session_id = await stack.enter_async_context(
                        streamablehttp_client(
                            config["url"],
                            headers=config.get("headers", {}),
                            timeout=config.get("connect_timeout", 10),
                        )
                    )
                else:
                    raise RuntimeError(
                        "Config must have 'command' (stdio) or 'url' (HTTP)"
                    )

                session = await stack.enter_async_context(
                    ClientSession(read, write)
                )

                # Initialize and verify capabilities
                init_result = await session.initialize()

                # Check for tools capability
                caps = init_result.capabilities
                if caps is None or caps.tools is None:
                    await stack.aclose()
                    raise RuntimeError(
                        f"MCP server '{mcp_name}' does not support tools"
                    )

                # Cache successful connection
                self._cache[key] = (session, stack)
                self._schedule_idle_disconnect(
                    key,
                    session_id,
                    skill_name,
                    mcp_name,
                    config.get("idle_timeout", 300),
                )
                logger.info(
                    "MCP connection established: %s (skill=%s, mcp=%s)",
                    session_id,
                    skill_name,
                    mcp_name,
                )
                return session

            except Exception:
                # Clean up partial stack on failure
                await stack.aclose()
                raise

    async def disconnect(
        self, session_id: str, skill_name: str, mcp_name: str
    ) -> None:
        """Close and remove a specific connection.

        Idempotent — calling on an already-disconnected key is a no-op.
        """
        key = self._make_key(session_id, skill_name, mcp_name)
        if key not in self._cache:
            self._idle_tasks.pop(key, None)
            return

        _session, stack = self._cache.pop(key)
        task = self._idle_tasks.pop(key, None)
        if task is not None:
            task.cancel()
        await stack.aclose()
        logger.debug(
            "MCP connection closed: %s (skill=%s, mcp=%s)",
            session_id,
            skill_name,
            mcp_name,
        )
        # Clean up lock if it exists
        self._locks.pop(key, None)

    async def shutdown_all(self) -> None:
        """Close all cached connections and clear internal state."""
        keys = list(self._cache.keys())
        for key in keys:
            _session, stack = self._cache.pop(key)
            try:
                await stack.aclose()
            except Exception as exc:
                logger.warning(
                    "Error closing MCP connection %s: %s", key, exc
                )
        self._cache.clear()
        for task in self._idle_tasks.values():
            task.cancel()
        self._idle_tasks.clear()
        self._locks.clear()
        logger.info("All MCP connections shut down (%d total)", len(keys))

    def get_connected_servers(self) -> list[str]:
        """Return list of active connection keys (for debugging)."""
        return list(self._cache.keys())

    def _schedule_idle_disconnect(
        self,
        key: str,
        session_id: str,
        skill_name: str,
        mcp_name: str,
        idle_timeout: float,
    ) -> None:
        if idle_timeout <= 0:
            return

        existing = self._idle_tasks.pop(key, None)
        if existing is not None:
            existing.cancel()

        async def _idle_worker() -> None:
            try:
                await self._sleep(idle_timeout)
                if key in self._cache and self._idle_tasks.get(key) is task:
                    await self.disconnect(session_id, skill_name, mcp_name)
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(_idle_worker())
        self._idle_tasks[key] = task
