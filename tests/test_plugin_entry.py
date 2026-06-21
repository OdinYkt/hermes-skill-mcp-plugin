"""Tests for hermes-skill-mcp plugin entry point (__init__.py).

Verifies register() behavioral contract against mock PluginContext.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


class TestRegisterBehavior:
    """Tests for register(ctx) function."""

    def test_register_calls_register_tool_with_correct_params(
        self, mock_plugin_context: MagicMock,
    ) -> None:
        """register(ctx) calls ctx.register_tool with correct name, toolset, is_async, emoji."""
        from __init__ import register

        register(mock_plugin_context)

        mock_plugin_context.register_tool.assert_called_once()
        _, kwargs = mock_plugin_context.register_tool.call_args
        assert kwargs["name"] == "skill_mcp"
        assert kwargs["toolset"] == "skill-mcp"
        assert kwargs["is_async"] is True
        assert kwargs["emoji"] == "\U0001f50c"

    def test_register_calls_register_hook_with_transform_tool_result(
        self, mock_plugin_context: MagicMock,
    ) -> None:
        """register(ctx) calls ctx.register_hook with 'transform_tool_result'."""
        from __init__ import register

        register(mock_plugin_context)

        mock_plugin_context.register_hook.assert_called_once()
        args, _kwargs = mock_plugin_context.register_hook.call_args
        assert args[0] == "transform_tool_result"

    def test_same_manager_instance_used(
        self, mock_plugin_context: MagicMock,
    ) -> None:
        """Only one SkillMcpManager created; same instance passed to create_handler."""
        manager_mock = MagicMock()
        handler_mock = MagicMock()
        hook_mock = MagicMock()

        with patch(
            "_connection.SkillMcpManager", return_value=manager_mock,
        ) as mock_mgr_cls, patch(
            "_tool_handler.create_handler", return_value=handler_mock,
        ) as mock_create_handler, patch(
            "_skill_view_hook.create_hook", return_value=hook_mock,
        ) as mock_create_hook:
            from __init__ import register

            register(mock_plugin_context)

            # One manager instance created
            mock_mgr_cls.assert_called_once()

            # create_handler received exactly that manager
            mock_create_handler.assert_called_once_with(manager_mock)

            # create_hook was called
            mock_create_hook.assert_called_once()

            # register_tool called with the handler from create_handler
            mock_plugin_context.register_tool.assert_called_once()
            assert (
                mock_plugin_context.register_tool.call_args[1]["handler"]
                == handler_mock
            )

    def test_check_fn_returns_true_when_mcp_installed(self) -> None:
        """check_fn returns True when mcp SDK is available."""
        from _config import check_mcp_sdk_available

        assert check_mcp_sdk_available() is True

    def test_module_importable_without_mcp_sdk(self) -> None:
        """No module-level import mcp — import does not raise ImportError."""
        init_path = Path(__file__).resolve().parent.parent / "__init__.py"
        source = init_path.read_text(encoding="utf-8")

        lines = source.split("\n")

        for line in lines:
            stripped = line.strip()
            # Check for module-level (indent 0) mcp import
            if stripped.startswith("import mcp") or stripped.startswith("from mcp"):
                if line.startswith((" ", "\t")) or stripped.startswith("#"):
                    continue
                raise AssertionError(
                    f"Module-level mcp import found: {line!r}"
                )

    def test_plugin_can_be_imported(self) -> None:
        """Plugin module can be imported and register is callable."""
        import __init__

        assert hasattr(__init__, "register")
        assert callable(__init__.register)
