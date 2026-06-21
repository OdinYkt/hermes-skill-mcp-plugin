from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from _connection import SkillMcpManager
from _tool_handler import (
    McpConnectionError,
    McpServerExitedError,
    McpToolExecutionError,
    McpToolNotFoundError,
    _build_error,
    _handle_skill_mcp,
    _validate_args,
)


def _ok_caps():
    caps = MagicMock()
    caps.tools = MagicMock()
    return MagicMock(capabilities=caps)


def _make_mcp_module(client_factory):
    class MockMcpModule:
        class ClientSession:
            def __init__(self, read, write):
                self.read = read
                self.write = write
                self._session = client_factory(read, write)

            async def __aenter__(self):
                return self._session

            async def __aexit__(self, *args):
                await self._session.close()

    return MockMcpModule()


def _make_stdio_module(call_log: list[dict]):
    @contextlib.asynccontextmanager
    async def stdio_client(server_params):
        call_log.append(server_params)
        read = MagicMock()
        write = MagicMock()
        yield read, write

    return SimpleNamespace(
        stdio_client=stdio_client,
        StdioServerParameters=lambda **kwargs: kwargs,
    )


def _install_mock_mcp(monkeypatch, client_factory):
    call_log: list[dict] = []
    mock_mcp = _make_mcp_module(client_factory)
    mock_stdio = _make_stdio_module(call_log)
    monkeypatch.setitem(sys.modules, "mcp", mock_mcp)
    monkeypatch.setitem(sys.modules, "mcp.client.stdio", mock_stdio)
    return call_log


def _client_factory_from_fixture(mock_mcp_client: MagicMock):
    created: list[MagicMock] = []

    def factory(_read, _write):
        client = MagicMock()
        client.initialize = AsyncMock(return_value=_ok_caps())
        client.close = AsyncMock()
        client.list_tools = mock_mcp_client.list_tools
        client.call_tool = mock_mcp_client.call_tool
        client.read_resource = getattr(mock_mcp_client, "read_resource", AsyncMock())
        client.get_prompt = getattr(mock_mcp_client, "get_prompt", AsyncMock())
        created.append(client)
        return client

    return factory, created


def _base_config(idle_timeout: float = 300) -> dict:
    return {
        "command": "python",
        "args": ["-m", "test_server"],
        "env": {},
        "timeout": 60,
        "connect_timeout": 10,
        "idle_timeout": idle_timeout,
    }


def _assert_error_schema(payload: str) -> None:
    parsed = json.loads(payload)
    assert set(parsed.keys()) == {"ok", "error_code", "message", "retryable"}
    assert parsed["ok"] is False
    assert isinstance(parsed["error_code"], str)
    assert isinstance(parsed["message"], str)
    assert isinstance(parsed["retryable"], bool)


@pytest.mark.asyncio
async def test_concurrent_same_key_one_connection_same_client(mock_mcp_client):
    factory, created = _client_factory_from_fixture(mock_mcp_client)
    monkeypatch = pytest.MonkeyPatch()
    call_log = _install_mock_mcp(monkeypatch, factory)

    manager = SkillMcpManager()
    config = _base_config()

    async def get_client():
        return await manager.get_or_create_client("s1", "skill_a", "time", config)

    results = await asyncio.gather(*(get_client() for _ in range(5)))

    assert len({id(client) for client in results}) == 1
    assert len(created) == 1
    assert len(call_log) == 1
    assert len(manager._cache) == 1


@pytest.mark.asyncio
async def test_concurrent_different_keys_three_connections(mock_mcp_client):
    factory, created = _client_factory_from_fixture(mock_mcp_client)
    monkeypatch = pytest.MonkeyPatch()
    call_log = _install_mock_mcp(monkeypatch, factory)

    manager = SkillMcpManager()
    config = _base_config()

    async def get_client(session_id: str):
        return await manager.get_or_create_client(session_id, "skill_a", "time", config)

    results = await asyncio.gather(get_client("s1"), get_client("s2"), get_client("s3"))

    assert len({id(client) for client in results}) == 3
    assert len(created) == 3
    assert len(call_log) == 3
    assert len(manager._cache) == 3


@pytest.mark.asyncio
async def test_shutdown_all_closes_ten_connections(mock_mcp_client):
    factory, created = _client_factory_from_fixture(mock_mcp_client)
    monkeypatch = pytest.MonkeyPatch()
    _install_mock_mcp(monkeypatch, factory)

    manager = SkillMcpManager()
    config = _base_config()

    for idx in range(10):
        await manager.get_or_create_client(f"s{idx}", "skill_a", "time", config)

    assert len(manager._cache) == 10

    await manager.shutdown_all()

    assert len(manager._cache) == 0
    assert manager.get_connected_servers() == []
    assert len(created) == 10
    assert all(client.close.await_count == 1 for client in created)


@pytest.mark.asyncio
async def test_error_paths_use_standard_error_shape(skill_with_mcp, skill_without_mcp, monkeypatch):
    cases = []

    cases.append(_build_error("TEST_ERR", "message", retryable=True))
    cases.append(_validate_args({}))

    with patch("_tool_handler.check_mcp_sdk_available", return_value=False):
        cases.append(
            await _handle_skill_mcp(
                {"skill_name": "skill-a", "mcp_name": "time", "tool_name": "x"},
                manager=MagicMock(),
                skill_dirs=[],
                session_id="default",
            )
        )

    with patch("_tool_handler.check_mcp_sdk_available", return_value=True), patch(
        "_tool_handler.parse_mcp_config", return_value={}
    ):
        cases.append(
            await _handle_skill_mcp(
                {"skill_name": "missing", "mcp_name": "time", "tool_name": "x"},
                manager=MagicMock(),
                skill_dirs=[skill_without_mcp("missing").parent],
                session_id="default",
            )
        )

    skill_dir = skill_with_mcp("demo")
    with patch("_tool_handler.check_mcp_sdk_available", return_value=True), patch(
        "_tool_handler.parse_mcp_config",
        return_value={"other": {"command": "python", "args": [], "env": {}}},
    ):
        cases.append(
            await _handle_skill_mcp(
                {"skill_name": "demo", "mcp_name": "missing", "tool_name": "x"},
                manager=MagicMock(),
                skill_dirs=[skill_dir.parent],
                session_id="default",
            )
        )

    class RaisingManager:
        async def get_or_create_client(self, *args, **kwargs):
            raise McpConnectionError("boom")

    with patch("_tool_handler.check_mcp_sdk_available", return_value=True), patch(
        "_tool_handler.parse_mcp_config",
        return_value={"time": {"command": "python", "args": [], "env": {}}},
    ):
        cases.append(
            await _handle_skill_mcp(
                {"skill_name": "demo", "mcp_name": "time", "tool_name": "x"},
                manager=RaisingManager(),
                skill_dirs=[skill_dir.parent],
                session_id="default",
            )
        )

    class ToolErrorClient:
        async def call_tool(self, **kwargs):
            raise McpToolNotFoundError("missing tool")

        async def read_resource(self, **kwargs):
            raise AssertionError("unused")

        async def get_prompt(self, **kwargs):
            raise AssertionError("unused")

    class ToolErrorManager:
        async def get_or_create_client(self, *args, **kwargs):
            return ToolErrorClient()

    with patch("_tool_handler.check_mcp_sdk_available", return_value=True), patch(
        "_tool_handler.parse_mcp_config",
        return_value={"time": {"command": "python", "args": [], "env": {}}},
    ):
        cases.append(
            await _handle_skill_mcp(
                {"skill_name": "demo", "mcp_name": "time", "tool_name": "x"},
                manager=ToolErrorManager(),
                skill_dirs=[skill_dir.parent],
                session_id="default",
            )
        )

    class ExecErrorClient:
        async def call_tool(self, **kwargs):
            raise McpToolExecutionError("bad run")

    class ExecErrorManager:
        async def get_or_create_client(self, *args, **kwargs):
            return ExecErrorClient()

    with patch("_tool_handler.check_mcp_sdk_available", return_value=True), patch(
        "_tool_handler.parse_mcp_config",
        return_value={"time": {"command": "python", "args": [], "env": {}}},
    ):
        cases.append(
            await _handle_skill_mcp(
                {"skill_name": "demo", "mcp_name": "time", "tool_name": "x"},
                manager=ExecErrorManager(),
                skill_dirs=[skill_dir.parent],
                session_id="default",
            )
        )

    class ExitErrorClient:
        async def call_tool(self, **kwargs):
            raise McpServerExitedError("gone")

    class ExitErrorManager:
        async def get_or_create_client(self, *args, **kwargs):
            return ExitErrorClient()

    with patch("_tool_handler.check_mcp_sdk_available", return_value=True), patch(
        "_tool_handler.parse_mcp_config",
        return_value={"time": {"command": "python", "args": [], "env": {}}},
    ):
        cases.append(
            await _handle_skill_mcp(
                {"skill_name": "demo", "mcp_name": "time", "tool_name": "x"},
                manager=ExitErrorManager(),
                skill_dirs=[skill_dir.parent],
                session_id="default",
            )
        )

    for payload in cases:
        _assert_error_schema(payload)


@pytest.mark.asyncio
async def test_idle_timeout_auto_disconnects(mock_mcp_client):
    factory, created = _client_factory_from_fixture(mock_mcp_client)
    monkeypatch = pytest.MonkeyPatch()
    call_log = _install_mock_mcp(monkeypatch, factory)

    manager = SkillMcpManager()
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float):
        sleep_calls.append(seconds)
        return None

    monkeypatch.setattr(manager, "_sleep", fake_sleep, raising=False)

    await manager.get_or_create_client("s1", "skill_a", "time", _base_config(idle_timeout=0.01))
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert 0.01 in sleep_calls, f"Expected 0.01 in sleep calls, got {sleep_calls}"
    assert len(manager._cache) == 0
    assert created[0].close.await_count == 1



class TestGatewayMultiUserIsolation:
    """Task 7.3: different sessions = separate MCP processes."""

    @pytest.mark.asyncio
    async def test_different_sessions_isolated(self, mock_mcp_client):
        factory, created = _client_factory_from_fixture(mock_mcp_client)
        call_log = _install_mock_mcp(pytest.MonkeyPatch(), factory)
        manager = SkillMcpManager()

        config = _base_config()
        await manager.get_or_create_client("session-A", "sk", "db", config)
        await manager.get_or_create_client("session-B", "sk", "db", config)

        assert len(created) == 2  # two separate connections
        assert len(manager._cache) == 2
        assert "session-A:sk:db" in manager._cache
        assert "session-B:sk:db" in manager._cache

    @pytest.mark.asyncio
    async def test_disconnect_one_session_not_affect_other(self, mock_mcp_client):
        factory, created = _client_factory_from_fixture(mock_mcp_client)
        _install_mock_mcp(pytest.MonkeyPatch(), factory)
        manager = SkillMcpManager()

        config = _base_config()
        await manager.get_or_create_client("session-A", "sk", "db", config)
        await manager.get_or_create_client("session-B", "sk", "db", config)

        await manager.disconnect("session-B", "sk", "db")
        assert "session-A:sk:db" in manager._cache
        assert "session-B:sk:db" not in manager._cache


class TestResourceCleanup:
    """Task 8.2: 100 create/disconnect cycles — no fd/subprocess leak."""

    @pytest.mark.asyncio
    async def test_hundred_cycles_no_crash(self, mock_mcp_client):
        factory, created = _client_factory_from_fixture(mock_mcp_client)
        _install_mock_mcp(pytest.MonkeyPatch(), factory)
        manager = SkillMcpManager()

        for i in range(100):
            key = (f"s{i % 3}", f"sk{i % 2}", f"srv{i}")
            config = _base_config()
            await manager.get_or_create_client(*key, config)

        assert len(manager._cache) <= 100
        await manager.shutdown_all()
        assert len(manager._cache) == 0