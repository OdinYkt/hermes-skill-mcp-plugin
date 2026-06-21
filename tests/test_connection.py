"""Tests for _connection.py — SkillMcpManager lazy MCP connections."""

from __future__ import annotations

import asyncio
import contextlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from _connection import SkillMcpManager


# ============================================================================
# Mock helpers
# ============================================================================


def _make_mock_stdio():
    """Return a mock that replaces ``mcp.client.stdio`` module."""

    class MockStdioModule:
        @staticmethod
        def stdio_client(server_params):
            """Async context manager yielding (read, write) streams."""
            read = MagicMock()
            write = MagicMock()

            @contextlib.asynccontextmanager
            async def cm():
                yield read, write

            return cm()

        @staticmethod
        def StdioServerParameters(**kwargs):
            return kwargs

    return MockStdioModule()


def _make_mock_mcp(has_tools: bool = True):
    """Return a mock that replaces the ``mcp`` package.

    Each ``ClientSession`` instance creates its own internal session mock.
    """
    _has_tools = has_tools

    def _make_init_result():
        result = MagicMock()
        if _has_tools:
            caps = MagicMock()
            caps.tools = MagicMock()
            result.capabilities = caps
        else:
            result.capabilities = None
        return result

    class MockMcpModule:

        class ClientSession:
            def __init__(self, read, write):
                self.read = read
                self.write = write
                self._session = MagicMock()
                self._session.initialize = AsyncMock(
                    return_value=_make_init_result()
                )

            async def __aenter__(self):
                return self._session

            async def __aexit__(self, *args):
                pass

    return MockMcpModule()


def _make_full_mocks(has_tools: bool = True):
    """Create complete mock chain: mcp + mcp.client.stdio.

    Returns (mock_mcp, mock_stdio)."""
    mock_mcp = _make_mock_mcp(has_tools=has_tools)
    mock_stdio = _make_mock_stdio()
    return mock_mcp, mock_stdio


def _stdlib_config() -> dict:
    """Return a minimal stdio config dict."""
    return {
        "command": "python",
        "args": ["-m", "test_server"],
        "env": {},
        "timeout": 60,
        "connect_timeout": 10,
        "idle_timeout": 300,
    }


# ============================================================================
# Basic lifecycle tests
# ============================================================================


class TestBasicLifecycle:
    """First call creates, second reuses, disconnect, shutdown."""

    @pytest.mark.asyncio
    async def test_first_call_creates_connection(self):
        mock_mcp, mock_stdio = _make_full_mocks()

        with patch.dict(sys.modules, {"mcp": mock_mcp, "mcp.client.stdio": mock_stdio}):
            manager = SkillMcpManager()
            config = _stdlib_config()
            session = await manager.get_or_create_client(
                "s1", "skill_a", "time", config
            )

        assert session is not None
        assert len(manager._cache) == 1

    @pytest.mark.asyncio
    async def test_second_call_reuses_cached_connection(self):
        mock_mcp, mock_stdio = _make_full_mocks()

        with patch.dict(sys.modules, {"mcp": mock_mcp, "mcp.client.stdio": mock_stdio}):
            manager = SkillMcpManager()
            config = _stdlib_config()

            s1 = await manager.get_or_create_client(
                "s1", "skill_a", "time", config
            )
            s2 = await manager.get_or_create_client(
                "s1", "skill_a", "time", config
            )

        assert s1 is s2
        assert len(manager._cache) == 1

    @pytest.mark.asyncio
    async def test_different_session_ids_produce_different_keys(self):
        mock_mcp, mock_stdio = _make_full_mocks()

        with patch.dict(sys.modules, {"mcp": mock_mcp, "mcp.client.stdio": mock_stdio}):
            manager = SkillMcpManager()
            config = _stdlib_config()

            s1 = await manager.get_or_create_client(
                "s1", "skill_a", "time", config
            )
            s2 = await manager.get_or_create_client(
                "s2", "skill_a", "time", config
            )

        assert s1 is not s2
        assert len(manager._cache) == 2

    @pytest.mark.asyncio
    async def test_disconnect_removes_from_cache(self):
        mock_mcp, mock_stdio = _make_full_mocks()

        with patch.dict(sys.modules, {"mcp": mock_mcp, "mcp.client.stdio": mock_stdio}):
            manager = SkillMcpManager()
            config = _stdlib_config()

            await manager.get_or_create_client(
                "s1", "skill_a", "time", config
            )
            assert len(manager._cache) == 1

            await manager.disconnect("s1", "skill_a", "time")

        assert len(manager._cache) == 0
        assert manager.get_connected_servers() == []

    @pytest.mark.asyncio
    async def test_disconnect_idempotent(self):
        mock_mcp, mock_stdio = _make_full_mocks()

        with patch.dict(sys.modules, {"mcp": mock_mcp, "mcp.client.stdio": mock_stdio}):
            manager = SkillMcpManager()
            config = _stdlib_config()

            await manager.get_or_create_client(
                "s1", "skill_a", "time", config
            )
            await manager.disconnect("s1", "skill_a", "time")
            await manager.disconnect("s1", "skill_a", "time")

        assert len(manager._cache) == 0

    @pytest.mark.asyncio
    async def test_shutdown_all_closes_all_connections(self):
        mock_mcp, mock_stdio = _make_full_mocks()

        with patch.dict(sys.modules, {"mcp": mock_mcp, "mcp.client.stdio": mock_stdio}):
            manager = SkillMcpManager()
            config = _stdlib_config()

            await manager.get_or_create_client(
                "s1", "skill_a", "time", config
            )
            await manager.get_or_create_client(
                "s2", "skill_b", "github", config
            )
            assert len(manager._cache) == 2

            await manager.shutdown_all()

        assert len(manager._cache) == 0
        assert manager.get_connected_servers() == []

    @pytest.mark.asyncio
    async def test_shutdown_all_on_empty_manager(self):
        manager = SkillMcpManager()
        await manager.shutdown_all()
        assert manager.get_connected_servers() == []

    @pytest.mark.asyncio
    async def test_get_connected_servers_lists_keys(self):
        mock_mcp, mock_stdio = _make_full_mocks()

        with patch.dict(sys.modules, {"mcp": mock_mcp, "mcp.client.stdio": mock_stdio}):
            manager = SkillMcpManager()
            config = _stdlib_config()

            await manager.get_or_create_client(
                "s1", "skill_a", "time", config
            )
            await manager.get_or_create_client(
                "s2", "skill_a", "time", config
            )

            servers = manager.get_connected_servers()
            assert "s1:skill_a:time" in servers
            assert "s2:skill_a:time" in servers
            assert len(servers) == 2


# ============================================================================
# Concurrency tests
# ============================================================================


class TestConcurrency:
    """Parallel calls with same/different keys."""

    @pytest.mark.asyncio
    async def test_concurrent_different_keys_run_in_parallel(self):
        mock_mcp, mock_stdio = _make_full_mocks()

        with patch.dict(sys.modules, {"mcp": mock_mcp, "mcp.client.stdio": mock_stdio}):
            manager = SkillMcpManager()
            config = _stdlib_config()

            async def get(key_suffix: str):
                return await manager.get_or_create_client(
                    f"s_{key_suffix}", "skill_a", "time", config
                )

            results = await asyncio.gather(
                get("a"), get("b"), get("c"),
            )

        assert len(results) == 3
        assert len(manager._cache) == 3

    @pytest.mark.asyncio
    async def test_concurrent_same_key_gets_same_connection(self):
        """Two parallel calls with same key → one connection created, both get same session."""
        mock_mcp, mock_stdio = _make_full_mocks()

        with patch.dict(sys.modules, {"mcp": mock_mcp, "mcp.client.stdio": mock_stdio}):
            manager = SkillMcpManager()
            config = _stdlib_config()

            async def get():
                return await manager.get_or_create_client(
                    "s1", "skill_a", "time", config
                )

            s1, s2 = await asyncio.gather(get(), get())

        assert s1 is s2
        assert len(manager._cache) == 1

    @pytest.mark.asyncio
    async def test_mixed_concurrent_calls(self):
        """Mix of same-key and different-key concurrent calls."""
        mock_mcp, mock_stdio = _make_full_mocks()

        with patch.dict(sys.modules, {"mcp": mock_mcp, "mcp.client.stdio": mock_stdio}):
            manager = SkillMcpManager()
            config = _stdlib_config()

            async def get(sid: str):
                return await manager.get_or_create_client(
                    sid, "skill_a", "time", config
                )

            a1, b, a2 = await asyncio.gather(
                get("a"), get("b"), get("a"),
            )

        # Same session key gets same client object
        assert a1 is a2
        # Different session keys are stored separately in cache
        assert len(manager._cache) == 2
        assert a1 is not b
        assert len(manager._cache) == 2


# ============================================================================
# Error handling tests
# ============================================================================


class TestErrorHandling:
    """MCP SDK not installed, connection failures, capability checks."""

    @pytest.mark.asyncio
    async def test_mcp_sdk_not_installed_raises_runtime_error(self, monkeypatch):
        manager = SkillMcpManager()
        config = _stdlib_config()

        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "mcp" or name.startswith("mcp."):
                raise ImportError("No module named 'mcp'")
            return original_import(name, *args, **kwargs)

        with monkeypatch.context() as m:
            m.setattr("builtins.__import__", mock_import)
            with pytest.raises(RuntimeError, match="MCP SDK not installed"):
                await manager.get_or_create_client(
                    "s1", "skill_a", "time", config
                )

    @pytest.mark.asyncio
    async def test_server_lacks_tools_capability_raises(self):
        mock_mcp, mock_stdio = _make_full_mocks(has_tools=False)

        with patch.dict(sys.modules, {"mcp": mock_mcp, "mcp.client.stdio": mock_stdio}):
            manager = SkillMcpManager()
            config = _stdlib_config()

            with pytest.raises(RuntimeError, match="does not support tools"):
                await manager.get_or_create_client(
                    "s1", "skill_a", "time", config
                )

        assert len(manager._cache) == 0

    @pytest.mark.asyncio
    async def test_connection_failure_not_cached(self):
        """If stdio_client raises, connection is not cached."""
        mock_mcp = _make_mock_mcp()
        mock_stdio = MagicMock()
        mock_stdio.stdio_client = MagicMock(side_effect=RuntimeError("Subprocess failed"))

        with patch.dict(sys.modules, {"mcp": mock_mcp, "mcp.client.stdio": mock_stdio}):
            manager = SkillMcpManager()
            config = _stdlib_config()

            with pytest.raises(RuntimeError, match="Subprocess failed"):
                await manager.get_or_create_client(
                    "s1", "skill_a", "time", config
                )

        assert len(manager._cache) == 0

    @pytest.mark.asyncio
    async def test_get_connected_servers_empty_initially(self):
        manager = SkillMcpManager()
        assert manager.get_connected_servers() == []


# ============================================================================
# Key format tests
# ============================================================================


class TestKeyFormat:
    """Cache key format is {session_id}:{skill_name}:{mcp_name}."""

    def test_make_key_format(self):
        manager = SkillMcpManager()
        key = manager._make_key("abc123", "data-tool", "sqlite")
        assert key == "abc123:data-tool:sqlite"

    def test_key_format_with_colons_in_name(self):
        """Colons in session_id/skill_name/mcp_name are fine — they are part of the key."""
        manager = SkillMcpManager()
        key = manager._make_key("ses:1", "sk:ill", "mc:p")
        assert key == "ses:1:sk:ill:mc:p"
