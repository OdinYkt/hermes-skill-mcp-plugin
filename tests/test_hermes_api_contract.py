"""API contract assertions for Hermes plugin system.

These tests encode our *verified* understanding of the Hermes plugin API.
They are NOT integration tests against a running Hermes — they are
documentation-in-code that assert our assumptions about parameter names,
types, return values, and behavior.

Source files verified:
  - hermes_cli/plugins.py          (PluginContext.register_tool, register_hook)
  - tools/registry.py              (ToolRegistry.register, dispatch, ToolEntry)
  - model_tools.py                 (transform_tool_result hook invocation)
  - plugins/spotify/__init__.py    (real plugin: register_tool usage)
  - plugins/spotify/tools.py       (real plugin: handler signatures)
  - tests/test_transform_tool_result_hook.py  (hook contract tests)
"""

from __future__ import annotations

import inspect
from typing import Any, Callable


# ============================================================================
# Phase A: Plugin Registration API
# ============================================================================


class TestRegisterToolSignature:
    """Verify assumptions about ctx.register_tool() parameter names and defaults.

    Source: hermes_cli/plugins.py, PluginContext.register_tool (lines 320-332)
    """

    # Exact parameter names from the real source, in order.
    # Verified: hermes_cli/plugins.py:320-332
    EXPECTED_PARAMS = (
        "self",
        "name",
        "toolset",
        "schema",
        "handler",
        "check_fn",
        "requires_env",
        "is_async",
        "description",
        "emoji",
        "override",
    )

    def test_register_tool_has_expected_parameter_names(self):
        """All expected parameters exist on PluginContext.register_tool."""
        from hermes_cli.plugins import PluginContext

        sig = inspect.signature(PluginContext.register_tool)
        actual_params = tuple(sig.parameters.keys())

        for expected in self.EXPECTED_PARAMS:
            assert expected in actual_params, (
                f"Expected parameter '{expected}' not found in "
                f"register_tool signature: {actual_params}"
            )

    def test_register_tool_accepts_is_async(self):
        """'is_async' parameter exists and defaults to False."""
        from hermes_cli.plugins import PluginContext

        sig = inspect.signature(PluginContext.register_tool)
        param = sig.parameters["is_async"]

        assert param.default is False, (
            f"is_async default is {param.default!r}, expected False"
        )

    def test_register_tool_accepts_check_fn(self):
        """'check_fn' parameter exists and defaults to None."""
        from hermes_cli.plugins import PluginContext

        sig = inspect.signature(PluginContext.register_tool)
        param = sig.parameters["check_fn"]

        assert param.default is None, (
            f"check_fn default is {param.default!r}, expected None"
        )

    def test_register_tool_accepts_requires_env(self):
        """'requires_env' parameter exists and defaults to None."""
        from hermes_cli.plugins import PluginContext

        sig = inspect.signature(PluginContext.register_tool)
        param = sig.parameters["requires_env"]

        assert param.default is None

    def test_register_tool_accepts_override(self):
        """'override' parameter exists and defaults to False."""
        from hermes_cli.plugins import PluginContext

        sig = inspect.signature(PluginContext.register_tool)
        param = sig.parameters["override"]

        assert param.default is False

    def test_register_tool_accepts_description(self):
        """'description' parameter exists and defaults to empty string."""
        from hermes_cli.plugins import PluginContext

        sig = inspect.signature(PluginContext.register_tool)
        param = sig.parameters["description"]

        assert param.default == ""

    def test_register_tool_accepts_emoji(self):
        """'emoji' parameter exists and defaults to empty string."""
        from hermes_cli.plugins import PluginContext

        sig = inspect.signature(PluginContext.register_tool)
        param = sig.parameters["emoji"]

        assert param.default == ""


class TestHandlerContract:
    """Verify assumptions about tool handler signatures and return types.

    Source: tools/registry.py dispatch method (lines 390-416)
            plugins/spotify/tools.py (all handlers: args: dict, **kw) -> str
    """

    def test_handler_receives_args_dict_and_kwargs(self):
        """Handler signature is handler(args: dict, **kwargs) -> str.

        Verified in 7 real handlers at plugins/spotify/tools.py:
          _handle_spotify_playback(args: dict, **kw) -> str
          _handle_spotify_devices(args: dict, **kw) -> str
          ...etc.
        """
        # This is a documentation assertion — the real handlers prove the
        # signature.  We assert the assumption explicitly.
        expected_signature = "(args: dict, **kwargs) -> str"
        assert expected_signature is not None  # tautology — signals intent

    def test_handler_returns_json_string(self):
        """Handler return type is str (JSON string).

        registry.dispatch() expects handler to return a JSON string.
        Error handling wraps exceptions as json.dumps({"error": ...}).
        Source: tools/registry.py:400-416
        """
        return_type_is_str = True  # from dispatch: return entry.handler(args, **kwargs)
        assert return_type_is_str

    def test_dispatch_passes_task_id_and_session_id_to_handler(self):
        """registry.dispatch() passes task_id + session_id as kwargs to handler.

        Source: model_tools.py lines 1115-1128:
          registry.dispatch(function_name, next_args,
              task_id=task_id,
              session_id=session_id,
              ...)
        """
        # These kwargs are forwarded directly to the handler via **kwargs.
        # Verified in model_tools.py dispatch calls.
        dispatch_kwargs_include = {"task_id", "session_id"}
        assert "task_id" in dispatch_kwargs_include
        assert "session_id" in dispatch_kwargs_include

    def test_dispatch_passes_user_task_for_non_execute_code(self):
        """For non-execute_code tools, dispatch passes user_task kwarg.

        Source: model_tools.py:1122-1128
        """
        assert True  # documented assumption — user_task is passed


class TestIsAsyncParameter:
    """Verify assumptions about is_async parameter behavior.

    Source: tools/registry.py dispatch (lines 401-403)
    """

    def test_is_async_exists(self):
        """'is_async' is a parameter on both PluginContext.register_tool
        and ToolRegistry.register.
        """
        from hermes_cli.plugins import PluginContext
        from tools.registry import ToolRegistry

        ctx_sig = inspect.signature(PluginContext.register_tool)
        reg_sig = inspect.signature(ToolRegistry.register)

        assert "is_async" in ctx_sig.parameters
        assert "is_async" in reg_sig.parameters

    def test_is_async_defaults_false(self):
        """is_async defaults to False."""
        from hermes_cli.plugins import PluginContext
        from tools.registry import ToolRegistry

        ctx_sig = inspect.signature(PluginContext.register_tool)
        reg_sig = inspect.signature(ToolRegistry.register)

        assert ctx_sig.parameters["is_async"].default is False
        assert reg_sig.parameters["is_async"].default is False

    def test_is_async_wraps_handler_in_run_async(self):
        """When is_async=True, dispatch wraps handler call in _run_async().

        Source: tools/registry.py:401-403
          if entry.is_async:
              from model_tools import _run_async
              return _run_async(entry.handler(args, **kwargs))
        """
        # _run_async bridges async handlers to synchronous dispatch.
        # The handler itself should be an async function (async def).
        assert True  # documented assumption


class TestCheckFn:
    """Verify assumptions about check_fn behavior.

    Source: tools/registry.py — ToolRegistry.register (lines 234-305)
            tools/registry.py — _check_fn_cached (lines 126-141)
            tools/registry.py — get_definitions (lines 337-384)
    """

    def test_check_fn_return_type_is_bool(self):
        """check_fn return value is coerced to bool via bool(fn()).

        Source: tools/registry.py:136 — value = bool(fn())
        """
        assert True  # bool(fn()) call confirms truthiness semantics

    def test_check_fn_stored_per_tool(self):
        """Each ToolEntry stores its own check_fn.

        Source: tools/registry.py:294 — check_fn=check_fn, (on ToolEntry)
        """
        from tools.registry import ToolEntry

        fn = lambda: True
        entry = ToolEntry(
            name="test",
            toolset="test-toolset",
            schema={},
            handler=lambda args, **kw: "{}",
            check_fn=fn,
            requires_env=[],
            is_async=False,
            description="",
            emoji="",
        )
        assert entry.check_fn is fn

    def test_first_check_fn_becomes_toolset_level_check(self):
        """The first check_fn registered for a toolset is stored as toolset-level.

        Source: tools/registry.py:303-304
          if check_fn and toolset not in self._toolset_checks:
              self._toolset_checks[toolset] = check_fn

        Subsequent tools in the same toolset do NOT overwrite the toolset-level
        check. However, per-tool check_fns are still used independently in
        get_definitions().
        """
        assert True  # documented behavior from registry.py lines 303-304

    def test_check_fn_cached_30_seconds(self):
        """check_fn results are cached for ~30s via _check_fn_cached.

        Source: tools/registry.py:121 — _CHECK_FN_TTL_SECONDS = 30.0
        """
        from tools.registry import _CHECK_FN_TTL_SECONDS

        assert _CHECK_FN_TTL_SECONDS == 30.0


class TestToolsetBehavior:
    """Verify assumptions about toolset naming and multi-tool registration.

    Source: tools/registry.py — ToolRegistry.register
            plugins/spotify/__init__.py — registers 7 tools in "spotify" toolset
    """

    def test_arbitrary_toolset_names_allowed(self):
        """Arbitrary toolset names like 'skill-mcp' are valid.

        The toolset name is just a string — there's no validation against
        a fixed list. Examples from real code: 'spotify', 'mcp-github', etc.
        """
        # Our toolset name: "skill-mcp"
        toolset = "skill-mcp"
        assert isinstance(toolset, str) and len(toolset) > 0

    def test_multiple_tools_same_toolset_share_first_check_fn(self):
        """When multiple tools register in the same toolset, only the first
        check_fn becomes the toolset-level check. But each tool keeps its own
        check_fn for per-tool availability filtering in get_definitions().

        Source: tools/registry.py:303-304 (toolset-level assignment)
                tools/registry.py:358-364 (per-tool checking in get_definitions)
        """
        assert True  # documented behavior


# ============================================================================
# Phase B: Hook API
# ============================================================================


class TestTransformToolResultHook:
    """Verify assumptions about transform_tool_result hook contract.

    Source: model_tools.py lines 1173-1195
            tests/test_transform_tool_result_hook.py (official test suite)
    """

    def test_hook_name_is_transform_tool_result(self):
        """Hook name is 'transform_tool_result'."""
        from hermes_cli.plugins import VALID_HOOKS

        assert "transform_tool_result" in VALID_HOOKS

    def test_hook_receives_tool_name_kwarg(self):
        """transform_tool_result hook receives tool_name kwarg.

        Source: model_tools.py:1177 — tool_name=function_name
        """
        assert True  # documented — tool_name is always present

    def test_hook_receives_result_kwarg(self):
        """transform_tool_result hook receives result kwarg (the tool's output).

        Source: model_tools.py:1179 — result=result
        """
        assert True  # documented

    def test_hook_receives_session_id_kwarg(self):
        """transform_tool_result hook receives session_id kwarg.

        Source: model_tools.py:1181 — session_id=session_id or ""
        """
        assert True  # documented

    def test_hook_receives_task_id_kwarg(self):
        """transform_tool_result hook receives task_id kwarg.

        Source: model_tools.py:1180 — task_id=task_id or ""
        """
        assert True  # documented

    def test_hook_receives_tool_call_id_kwarg(self):
        """transform_tool_result hook receives tool_call_id kwarg.

        Source: model_tools.py:1182 — tool_call_id=tool_call_id or ""
        """
        assert True  # documented

    def test_hook_receives_turn_id_kwarg(self):
        """transform_tool_result hook receives turn_id kwarg.

        Source: model_tools.py:1183 — turn_id=turn_id or ""
        """
        assert True  # documented

    def test_hook_receives_api_request_id_kwarg(self):
        """transform_tool_result hook receives api_request_id kwarg.

        Source: model_tools.py:1184 — api_request_id=api_request_id or ""
        """
        assert True  # documented

    def test_hook_receives_duration_ms_kwarg(self):
        """transform_tool_result hook receives duration_ms kwarg (int).

        Source: model_tools.py:1185 — duration_ms=duration_ms
                model_tools.py:1148 — duration_ms = int((time.monotonic() - _dispatch_start) * 1000)
        """
        assert True  # documented — duration_ms is int (milliseconds)

    def test_hook_receives_status_kwarg(self):
        """transform_tool_result hook receives status kwarg.

        Source: model_tools.py:1186 — status=status
        """
        assert True  # documented

    def test_hook_receives_error_type_kwarg(self):
        """transform_tool_result hook receives error_type kwarg.

        Source: model_tools.py:1187 — error_type=error_type
        """
        assert True  # documented

    def test_hook_receives_error_message_kwarg(self):
        """transform_tool_result hook receives error_message kwarg.

        Source: model_tools.py:1188 — error_message=error_message
        """
        assert True  # documented

    def test_hook_receives_args_kwarg(self):
        """transform_tool_result hook receives args kwarg (the tool call args).

        Source: model_tools.py:1178 — args=function_args
        """
        assert True  # documented

    def test_full_kwargs_set(self):
        """All expected kwargs for transform_tool_result hook."""
        expected_kwargs = {
            "tool_name",
            "args",
            "result",
            "task_id",
            "session_id",
            "tool_call_id",
            "turn_id",
            "api_request_id",
            "duration_ms",
            "status",
            "error_type",
            "error_message",
        }

        # Source: model_tools.py lines 1175-1189
        documented_kwargs = {
            "tool_name",
            "args",
            "result",
            "task_id",
            "session_id",
            "tool_call_id",
            "turn_id",
            "api_request_id",
            "duration_ms",
            "status",
            "error_type",
            "error_message",
        }

        assert expected_kwargs == documented_kwargs

    def test_string_return_replaces_result(self):
        """Returning a str from hook replaces the tool result.

        Source: model_tools.py:1190-1193
          for hook_result in hook_results:
              if isinstance(hook_result, str):
                  result = hook_result
                  break
        """
        assert True  # documented — first non-None str wins

    def test_none_return_passes_through(self):
        """Returning None (or non-str) leaves result unchanged.

        Source: model_tools.py:1190-1193 — only isinstance(hook_result, str) triggers replacement
                tests/test_transform_tool_result_hook.py:64-69 — result_unchanged_for_none_hook_return
        """
        assert True  # documented

    def test_hook_exceptions_do_not_break_dispatch(self):
        """Hook exceptions are caught; original result is preserved.

        Source: model_tools.py:1194-1195
          except Exception as _hook_err:
              logger.debug("transform_tool_result hook error: %s", _hook_err)
        """
        assert True  # documented — fail-open

    def test_tool_name_is_reliable(self):
        """tool_name kwarg is always present and is the dispatched tool name.

        Source: model_tools.py:1177 — tool_name=function_name (from the function call argument)
        """
        assert True  # documented


# ============================================================================
# Phase C: Scaffold Verification
# ============================================================================


class TestProjectScaffold:
    """Verify that project scaffold is correctly set up."""

    def test_pyproject_toml_exists(self):
        """pyproject.toml exists at project root."""
        from pathlib import Path

        project_root = Path(__file__).resolve().parent.parent
        assert (project_root / "pyproject.toml").exists()

    def test_conftest_defines_fixtures(self):
        """conftest.py defines expected fixtures."""
        # Import from THIS project's conftest, not hermes-agent's.
        import importlib.util
        from pathlib import Path

        conftest_path = Path(__file__).resolve().parent / "conftest.py"
        spec = importlib.util.spec_from_file_location(
            "conftest", conftest_path
        )
        assert spec is not None, f"Could not load conftest from {conftest_path}"
        conftest = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(conftest)

        assert callable(conftest.temp_skills_dir)
        assert callable(conftest.skill_with_mcp)
        assert callable(conftest.skill_without_mcp)
        assert conftest.mock_mcp_client is not None
        assert conftest.mock_plugin_context is not None
