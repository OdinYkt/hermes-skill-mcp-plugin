"""Tests for plugin entry point (__init__.py)."""
from __future__ import annotations

import sys
from unittest.mock import ANY, MagicMock, patch

from conftest import PLUGIN_PATH, import_plugin_module

register = import_plugin_module("__init__").register
check_mcp_sdk_available = import_plugin_module("_config").check_mcp_sdk_available


def test_register_registers_tool_and_hook(monkeypatch):
    """register(ctx) calls ctx.register_tool and ctx.register_hook with correct params."""
    monkeypatch.syspath_prepend(PLUGIN_PATH)
    ctx = MagicMock()

    register(ctx)

    ctx.register_tool.assert_called_once()
    call_kwargs = ctx.register_tool.call_args.kwargs
    assert call_kwargs["name"] == "skill_mcp"
    assert call_kwargs["toolset"] == "skill-mcp"
    assert call_kwargs["is_async"] is True
    assert call_kwargs["emoji"] == "\U0001f50c"
    assert "schema" in call_kwargs
    assert callable(call_kwargs["handler"])
    assert callable(call_kwargs["check_fn"])

    ctx.register_hook.assert_called_once()
    hook_args = ctx.register_hook.call_args.args
    assert hook_args[0] == "transform_tool_result"
    assert callable(hook_args[1])


def test_check_fn_returns_false_without_sdk():
    """check_mcp_sdk_available returns False when mcp SDK not importable."""
    original_import = __builtins__["__import__"]

    def _mock_import(name, *args, **kwargs):
        if name == "mcp" or name.startswith("mcp."):
            raise ImportError("No module named '{}'".format(name))
        return original_import(name, *args, **kwargs)

    with patch.dict("sys.modules", {"mcp": None}):
        with patch("builtins.__import__", side_effect=_mock_import):
            result = check_mcp_sdk_available()

    assert result is False


def test_no_import_error_without_mcp(monkeypatch):
    """Plugin __init__ importable when mcp SDK not installed — no ImportError."""
    monkeypatch.delitem(sys.modules, "__init__", raising=False)
    monkeypatch.setitem(sys.modules, "mcp", None)

    mod = import_plugin_module("__init__")
    assert hasattr(mod, "register")
    assert callable(mod.register)
