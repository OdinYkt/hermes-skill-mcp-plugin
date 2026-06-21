# Hermes-Skill-MCP Production Readiness Plan v2

**State**: 144/150 tests, 5 fail. BDD: 41 IMPLEMENTED, 11 PARTIAL, 14 MISSING.
**Goal**: Production-ready — 135 tests, 0 failures, README, wemake clean.

## Root Causes of 5 Failing Tests

| Test | Root Cause | Fix |
|---|---|---|
| test_sdk_not_installed | _import_mcp propagates raw ImportError | Wrap in RuntimeError |
| test_server_lacks_tools | Cache created before capability check | try/finally pop cache in _establish_connection |
| test_connection_failure_not_cached | Transport failure before list_tools guard | Same cache fix |
| test_connect (skill_mcp) | anyio scope in Docker, redundant | Remove in Wave 3 |
| test_no_mcp_config_error | skill_without_mcp fixture missing SKILL.md | Fix fixture |

---

## Prerequisite — Build test image (before Wave 1)

**QA**: `docker build --no-cache -f Dockerfile.test -t hermes-test:debug . && echo OK`
**Expected**: Image built, all subsequent `docker run --rm hermes-test:debug ...` commands work.

---

## Wave 1 — Code Fixes + Independent Tests
### Task 0: Cache invalidation in _establish_connection
**File**: `_connection.py:204-231`
**Change**: Wrap entire body in try/finally. Pop `manager._clients[conn_key]` on any exception.
**QA**: `docker build -f Dockerfile.test -t hermes-test:debug . && docker run --rm hermes-test:debug pytest tests/test_connection.py::TestErrorHandling -v --tb=short`
**Expected**: test_server_lacks_tools_capability_raises PASS, test_connection_failure_not_cached PASS

### Task 1: _import_mcp RuntimeError on ImportError
**File**: `_connection.py:102-121`
**Change**: Wrap `from mcp import ...` in try/except ImportError → raise RuntimeError("MCP SDK not installed. Run: pip install mcp")
**QA**: `docker run --rm hermes-test:debug pytest tests/test_connection.py::TestErrorHandling::test_sdk_not_installed_raises_runtime_error -v --tb=short`
**Expected**: PASS with RuntimeError match

### Task 2: Error code rename MCP_TOOLS_UNAVAILABLE → MCP_CAPABILITY_MISSING
**File**: `_tool_handler.py:81,373`
**Change**: Rename constant + update reference. Verify no other uses.
**QA**: `grep -r "MCP_TOOLS_UNAVAILABLE" . --include="*.py" | grep -v .venv | grep -v __pycache__`
**Expected**: 0 results

### Task 3: Fix skill_without_mcp fixture
**File**: `tests/conftest.py:65-71`
**Change**: Add `(skill_dir / "SKILL.md").write_text("# {}\n".format(skill_name))` after mkdir.
**QA**: `docker run --rm hermes-test:debug pytest tests/test_tool_handler.py::TestSkillNotFound::test_no_mcp_config_error -v --tb=short`
**Expected**: PASS, error_code == "NO_MCP_CONFIG"

### Task 9: Add Feature 2.4-2.5 tests
**File**: `tests/test_config.py` (append)
**Tests**: test_duplicate_server_names_yaml_behavior, test_cross_skill_duplicate_resolution
**QA**: `docker run --rm hermes-test:debug pytest tests/test_config.py -v -k "duplicate_server_names or cross_skill_duplicate"`
**Expected**: 2 tests PASS

### Task 12: Add Feature 7.4/7.7 tests
**File**: `tests/test_security.py` (append)
**Tests**: test_path_appended_not_replaced, test_args_not_shell_expanded
**QA**: `docker run --rm hermes-test:debug pytest tests/test_security.py -v -k "path_appended or args_not_shell_expanded"`
**Expected**: 2 tests PASS

### Task 14: Add Feature 10 perf tests
**File**: `tests/test_performance.py` (new)
**Tests**: test_parse_latency_under_50ms, test_cached_overhead_under_50ms (both @pytest.mark.slow)
**QA**: `docker run --rm hermes-test:debug pytest tests/test_performance.py -v -m slow`
**Expected**: 2 tests PASS

---

## Wave 2 — Test Verification + New Integration Tests

### Task 4-7: Verify failing tests pass after Wave 1
**QA**: `docker run --rm hermes-test:debug pytest tests/test_connection.py::TestErrorHandling tests/test_tool_handler.py::TestSkillNotFound::test_no_mcp_config_error -v --tb=short`
**Expected**: all 4 tests PASS (test_sdk_not_installed, test_server_lacks_tools, test_connection_failure_not_cached, test_no_mcp_config_error)

### Task 10: Add HTTP transport test (Feature 3.3)
**File**: `tests/test_connection.py` (append)
**Test**: test_http_transport_creates_connection
**QA**: `docker run --rm hermes-test:debug pytest tests/test_connection.py -v -k "test_http_transport"`
**Expected**: 1 test PASS

### Task 11: Add idle/timeout lifecycle tests (Feature 5.1/5.4/5.5)
**File**: `tests/test_connection.py` (append)
**Tests**: test_lazy_no_connect_until_call, test_idle_cleanup_disconnects, test_shutdown_cancels_idle_tasks
**QA**: `docker run --rm hermes-test:debug pytest tests/test_connection.py -v -k "lazy_no_connect or idle_cleanup or shutdown_cancels" --tb=short`
**Expected**: 3 tests PASS

### Task 13: Add timeout enforcement tests (Feature 9.1/9.2)
**File**: `tests/test_connection.py` (append)
**Tests**: test_connect_timeout_respected, test_tool_timeout_respected
**QA**: `docker run --rm hermes-test:debug pytest tests/test_connection.py -v -k "timeout" --tb=short`
**Expected**: 2 tests PASS + existing timeout tests still pass

---

## Wave 3 — Cleanup + Plugin Tests

### Task 8: Add test_plugin_entry.py (Feature 1)
**File**: `tests/test_plugin_entry.py` (new)
**Tests**: test_register_registers_tool_and_hook, test_check_fn_false_without_sdk, test_no_import_error_without_mcp
**QA**: `docker run --rm hermes-test:debug pytest tests/test_plugin_entry.py -v`
**Expected**: 3 tests PASS

### Task 15: Remove redundant tests
**File**: `tests/test_skill_mcp.py`
**Remove**: TestMcpConnection (3 methods), TestPluginInstallation (4 methods), TestHermesCLI (3 methods). Keep: TestMcpConfigParsing, TestSkillViewHook, TestAgentE2E. Move test_plugin_imports_cleanly to test_plugin_entry.py.
**QA**: `docker run --rm hermes-test:debug pytest tests/test_skill_mcp.py -v`
**Expected**: remaining tests PASS, no ImportError or missing class errors

---

## Wave 4 — Documentation + Final Verification

### Task 16: README.md
**Content**: Plugin purpose, install instructions, mcp.yaml example, test run command, BDD coverage matrix.
**QA**: `cat README.md | head -10`
**Expected**: File exists, contains install + test instructions.

### Task 17: Final Docker verification
**QA**: `./scripts/run-tests.sh 2>&1 | tail -5`
**Expected**: `155+ passed, 0 failed, X skipped` (some tests skip without API key, perf tests skip without -m slow flag)
**Also**: `docker run --rm hermes-test:debug flake8 /opt/hermes/plugins/skill-mcp/*.py --max-line-length=80 | grep -v ".venv" | grep -v "noqa"`
**Expected**: 0 wemake violations on source files.
