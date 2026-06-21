# Hermes-Skill-MCP Production Readiness Plan

**State**: 144/150 tests, 5 fail. BDD: 41 IMPLEMENTED, 11 PARTIAL, 14 MISSING.

## Root Causes of 5 Failing Tests

| Test | Root Cause | Fix |
|---|---|---|
| test_sdk_not_installed | _import_mcp propagates raw ImportError | Wrap in RuntimeError |
| test_server_lacks_tools | Cache created before capability check | try/finally pop cache in _establish_connection |
| test_connection_failure_not_cached | Transport failure before list_tools guard | Same cache fix |
| test_connect (skill_mcp) | anyio scope in Docker, redundant | Remove in Phase 2 |
| test_no_mcp_config_error | skill_without_mcp fixture missing SKILL.md | Fix fixture |

## Execution Waves

### Wave 1 — Code Fixes + Independent Tests
- Task 0: Cache invalidation in _establish_connection
- Task 1: _import_mcp RuntimeError on ImportError
- Task 2: Error code rename MCP_TOOLS_UNAVAILABLE → MCP_CAPABILITY_MISSING
- Task 3: Fix skill_without_mcp fixture (add SKILL.md)
- Task 9: Add Feature 2.4-2.5 tests (duplicate YAML, cross-skill)
- Task 12: Add Feature 7.4/7.7 tests (PATH append, no shell)
- Task 14: Add Feature 10 perf tests

### Wave 2 — Test Verification + New Integration Tests
- Task 4-7: Verify 4 failing tests now pass
- Task 10: Add HTTP transport test (Feature 3.3)
- Task 11: Add idle/timeout tests (Feature 5.1/5.4/5.5)
- Task 13: Add timeout enforcement tests (Feature 9.1/9.2)

### Wave 3 — Cleanup + Plugin Tests
- Task 8: Add test_plugin_entry.py (Feature 1)
- Task 15: Remove redundant tests from test_skill_mcp.py

### Wave 4 — Documentation + Verification
- Task 16: README.md with install + BDD matrix
- Task 17: Final Docker verification → 155+ tests, 0 failures
