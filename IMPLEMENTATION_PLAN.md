# hermes-skill-mcp Implementation Plan v3

> **For agentic workers:** REQUIRED SUB-SKILL: subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.
>
> **Role:** Coordinator delegates tasks to subagents with behavioral specs. Subagents implement, test, commit. Coordinator verifies results.

**Goal:** Hermes plugin — skills carry MCP servers via `mcp.yaml`. Agent calls `skill_mcp(skill_name, mcp_name, tool_name, arguments)`. No config.yaml editing. No restart.

**Architecture:** 6 modules, async handler, lazy MCP connections keyed `{session_id}:{skill_name}:{mcp_name}`, `transform_tool_result` hook for `skill_view` augmentation, toolset `"skill-mcp"`.

**Tech Stack:** Python 3.11+, `mcp` SDK, `pyyaml`, `pytest` + `pytest-asyncio`

**Spec:** `BDD.md` (55 scenarios, 11 features)

---

## File Map

```
hermes-skill-mcp/
├── plugin.yaml              # [EXISTS] plugin manifest
├── BDD.md                   # [EXISTS] behavior spec
├── __init__.py               # [CREATE] register(ctx) entry point
├── pyproject.toml            # [CREATE] pip-installable metadata
├── _config.py                # [CREATE] mcp.yaml parser
├── _connection.py            # [CREATE] SkillMcpManager
├── _security.py              # [CREATE] env filter, redaction, denylist
├── _tool_handler.py          # [CREATE] skill_mcp async handler
├── _skill_view_hook.py       # [CREATE] transform_tool_result hook
└── tests/
    ├── conftest.py           # [CREATE] shared fixtures
    ├── test_config.py
    ├── test_security.py
    ├── test_connection.py
    ├── test_tool_handler.py
    ├── test_skill_view_hook.py
    ├── test_plugin_entry.py
    └── test_e2e.py
```

## Dependency Graph

```
Phase 0: Task 0 [Hermes API verification + scaffold]
    │
    ├─→ Phase 1 [PARALLEL]: Task 1 (config), Task 2 (security)
    │
    ├─→ Phase 2 [SEQUENTIAL]: 
    │       Task 3 (connection) [blocked by Task 1 + Task 2]
    │           │
    │           ├─→ Task 4 (tool handler)
    │           └─→ Task 5 (skill_view hook) [can run parallel with Task 4]
    │
    ├─→ Phase 3: Task 6 (plugin entry) [blocked by Task 3,4,5]
    │
    └─→ Phase 4 [PARALLEL]: Task 7 (e2e), Task 8 (edge/stress), Task 9 (polish)
```

---

## Task 0: Hermes API Verification + Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `tests/conftest.py`
- Create: `tests/test_hermes_api_contract.py` [disposable — verifies assumptions]
- Document: findings block in plan (this task updates the plan)

**Goal:** Verify all assumptions about Hermes plugin API before any implementation. Set up project structure.

### Behavioral Contract

**0.1 Plugin Registration API**
- Inspect 2+ existing Hermes plugins (honcho, hindsight, mem0) in `plugins/memory/`
- Confirm: `ctx.register_tool()` exact signature (param names, order, defaults)
- Confirm: `is_async` parameter exists and semantics
- Confirm: `check_fn` return value semantics — does it gate the toolset or individual tool?
- Confirm: handler call signature — `handler(args: dict, **kwargs)` — what keys in kwargs?
- Confirm: handler return type — JSON string? Dict? Both accepted?

**0.2 Hook API**
- Inspect `transform_tool_result` hook contract:
  - What kwargs does the hook receive? Name all keys.
  - Return semantics: `str` replaces result, `None` passes through, other types?
  - Is `tool_name` always present? Is it reliable for detecting `skill_view` calls?
- Confirm hook is invoked AFTER `post_tool_call`, BEFORE result appended to context

**0.3 Toolset Behavior**
- Confirm: toolset `"skill-mcp"` — is custom toolset name accepted?
- Confirm: how user enables custom toolsets (`hermes tools enable skill-mcp`)?
- Confirm: `check_fn` for toolset — is it per-toolset (first registration wins)?

**0.4 Project Scaffold**
- `pyproject.toml` with deps: `mcp>=1.0`, `pyyaml>=6.0`, `pytest`, `pytest-asyncio`
- `tests/conftest.py` with fixtures:
  - `temp_skills_dir` → `Path` to temp directory
  - `skill_with_mcp(name, mcp_config: dict)` → creates `SKILL.md` + `mcp.yaml`, returns `Path`
  - `skill_without_mcp(name)` → creates only `SKILL.md`, returns `Path`
  - `mock_mcp_client()` → `MagicMock` with `list_tools`, `call_tool`, `close` as `AsyncMock`
  - `mock_plugin_context()` → `MagicMock` with `register_tool`, `register_hook`

### Acceptance Criteria
- [ ] At least 2 existing plugins inspected, API contract documented
- [ ] `test_hermes_api_contract.py` passes assertions about plugin API shape
- [ ] `pyproject.toml` installs deps: `pip install -e .` succeeds
- [ ] `conftest.py` fixtures importable, each fixture returns correct types
- [ ] Finding: if Hermes API differs from assumptions → plan updated BEFORE proceeding

### BDD Coverage
- F1.1, F1.2, F1.3 (plugin discovery — verified against real API)

---

## Task 1: Config Parser

**Files:**
- Create: `_config.py`
- Create: `tests/test_config.py`

**Dependencies:** Task 0 (conftest fixtures, Hermes API contract known)

**Goal:** Parse `mcp.yaml` from skill directory into validated server config dict. No MCP connections — pure data parsing.

### Module Interface

```
_config.py
├── check_mcp_sdk_available() -> bool
│       Returns True if `import mcp` succeeds. Used as check_fn for toolset.
│
└── parse_mcp_config(skill_dir: Path) -> dict[str, dict]
        Reads skill_dir/mcp.yaml, validates, normalizes, returns {server_name: server_config}.
        Returns {} if no mcp.yaml, parse error, or invalid schema.
```

### Behavioral Contract

**parse_mcp_config(skill_dir)**

| Given | When | Then |
|-------|------|------|
| `mcp.yaml` with `command: "uvx"`, `args: ["mcp-server-sqlite"]` | parsed | `{"sqlite": {"command": "uvx", "args": ["mcp-server-sqlite"], "timeout": 60, "connect_timeout": 10, "idle_timeout": 300}}` |
| `mcp.yaml` with `url: "https://..."` | parsed | transport = HTTP (no `command` key) |
| `mcp.yaml` with `${API_KEY}` in values | parsed | `${API_KEY}` expanded from `os.environ` |
| `mcp.yaml` with `args: ["./server.py"]` | parsed | `"./server.py"` resolved to absolute path relative to `mcp.yaml` dir |
| `mcp.yaml` with `args: ["../../../etc/passwd"]` | parsed | server entry rejected (path escapes skill dir) |
| No `mcp.yaml` exists | parsed | returns `{}` |
| `mcp.yaml` is invalid YAML | parsed | returns `{}`, warning logged |
| `mcp.yaml` has unknown fields (e.g. `sampling`) | parsed | unknown fields silently ignored |
| `mcp.yaml` has 40 servers | parsed | truncated to 32, warning logged |
| Server entry missing both `command` and `url` | parsed | entry rejected |
| Server entry has both `command` and `url` | parsed | entry rejected |

**Default values filled:**
- `timeout`: 60 (per-tool-call timeout, seconds)
- `connect_timeout`: 10 (connection timeout, seconds)
- `idle_timeout`: 300 (idle cleanup timeout, seconds)

**check_mcp_sdk_available()**
- Returns `True` when `import mcp` succeeds
- Returns `False` when `import mcp` raises `ImportError`
- Must not cache result — called each time

### Error Handling Contract
- Never raises exceptions to caller
- Parse failures → log warning, return `{}`
- Individual server entry failures → log warning, skip entry, continue parsing others

### Test Requirements
- [ ] All Given/When/Then scenarios above
- [ ] Empty `mcp.yaml` (file exists, no content)
- [ ] `mcp.yaml` missing in skill dir
- [ ] Config with multiple servers
- [ ] Environment variable expansion (and no expansion without `${}` syntax)
- [ ] Relative path resolution and escape rejection
- [ ] Max servers truncation
- [ ] Forward compatibility (unknown fields)

### BDD Coverage
- F2: Scenarios 2.1–2.12
- F10: Timeout defaults (2.1–2.3)
- F11: mcp.yaml schema

---

## Task 2: Security Module

**Files:**
- Create: `_security.py`
- Create: `tests/test_security.py`

**Dependencies:** Task 0 (conftest)

**Goal:** Environment filtering for MCP subprocesses, credential redaction in error messages, command denylist.

### Module Interface

```
_security.py
├── SAFE_BASELINE_VARS: set[str]
│       Env vars always inherited by MCP subprocess.
│       At minimum: PATH, HOME, USER, TMPDIR, LANG
│
├── DENIED_COMMANDS: set[str]
│       Commands rejected from mcp.yaml. At minimum: sudo, su
│
├── filter_mcp_environment(explicit_env: dict[str, str]) -> dict[str, str]
│       Merge safe os.environ vars + explicit_env. PATH/HOME/SHELL are appended, not replaced.
│
├── redact_credentials(text: str) -> str
│       Replace credential patterns with ***. Patterns: sk-*, ghp_*, Bearer *, key=*, token=*, password=*, secret=*
│
└── is_command_allowed(command: str) -> bool
        Returns False if command in DENIED_COMMANDS.
```

### Behavioral Contract

**filter_mcp_environment(explicit_env)**
- Inherits only `SAFE_BASELINE_VARS` from `os.environ`
- Adds all key-value pairs from `explicit_env`
- `PATH`, `HOME`, `SHELL` in `explicit_env` → appended with `os.pathsep`, not replaced
- Secret vars (`API_KEY`, `TOKEN`, `PASSWORD`) from `os.environ` NOT leaked

**redact_credentials(text)**
- `"Bearer sk-abc123"` → `"Bearer ***"`
- `"ghp_1234567890abcdef"` → `"***"`
- `"key=supersecret"` → `"key=***"`
- `"token=mysecrettoken"` → `"token=***"`
- `"password=hunter2"` → `"password=***"`
- `"secret=classified"` → `"secret=***"`
- `"Connection failed"` → `"Connection failed"` (no change)

**is_command_allowed(command)**
- `"sudo"` → `False`
- `"su"` → `False`
- `"uvx"` → `True`
- `"npx"` → `True`
- `"python"` → `True`

### Test Requirements
- [ ] All behavioral scenarios above
- [ ] `filter_mcp_environment` with empty explicit_env
- [ ] `filter_mcp_environment` with PATH override (append, not replace)
- [ ] `redact_credentials` with mixed content (secrets + normal text)
- [ ] `is_command_allowed` for allowed and denied commands

### BDD Coverage
- F7: Scenarios 7.1–7.7 (all security scenarios)

---

## Task 3: Connection Manager

**Files:**
- Create: `_connection.py`
- Create: `tests/test_connection.py`

**Dependencies:** Task 1 (_config types), Task 2 (_security env filter)

**Goal:** Manage lazy MCP connections — connect on first use, cache, cleanup on idle/session end. Handle both stdio and HTTP transports.

### Module Interface

```
_connection.py
└── class SkillMcpManager:
        __init__(self)
        get_or_create_client(self, session_id: str, skill_name: str, mcp_name: str, config: dict) -> MCPClientSession
                Get cached or create new MCP client. Connection key: {session_id}:{skill_name}:{mcp_name}
        disconnect(self, session_id: str, skill_name: str, mcp_name: str) -> None
                Close and remove specific connection.
        shutdown_all(self) -> None
                Close all connections. Called on plugin unload / session end.
        get_connected_servers(self) -> list[str]
                List active connection keys (for debugging).
```

### Behavioral Contract

**get_or_create_client**

| Given | When | Then |
|-------|------|------|
| First call for `(session_id, skill_name, mcp_name)` | called | spawns MCP subprocess (stdio) or opens HTTP connection; returns connected + initialized client |
| Second call with same key | called | returns cached client; no new subprocess |
| Different `session_id`, same `(skill_name, mcp_name)` | called | creates separate connection (different cache key) |
| Config has `command` (stdio) | called | uses `stdio_client` transport; env filtered via `filter_mcp_environment(config.env)` |
| Config has `url` (HTTP) | called | uses HTTP/StreamableHTTP transport; headers from config |
| MCP server already running (cached) | called | returns cached in <5ms overhead (excl. tool time) |
| Connection fails | called | raises with descriptive error (no fallback) |
| Two parallel calls with different keys | called | both execute concurrently (separate connections) |
| Two parallel calls with same key | called | one connection created, both get same client; no race condition |
| MCP SDK not installed | called | raises RuntimeError("MCP SDK not installed") |

**disconnect**
- Removes connection from cache
- Closes transport (terminates subprocess for stdio, closes HTTP session)
- Idempotent: calling on already-disconnected key is no-op

**shutdown_all**
- Closes all cached connections
- Terminates all subprocesses — no zombie processes
- Clears all internal state

### Connection Lifecycle Requirements

- **Lazy**: No connection until first `get_or_create_client` call
- **Persistent**: Connection stays alive across multiple tool calls
- **Context manager**: Must use `contextlib.AsyncExitStack` to hold `stdio_client` + `ClientSession` contexts open
- **Initialization**: After transport connect, must call `session.initialize()` and verify server capabilities include `tools`
- **Capability check**: If server lacks `tools` capability → reject with clear error, don't cache
- **Idle cleanup**: Connection idle for `idle_timeout` seconds (from config, default 300) → auto-disconnect
- **Cleanup timer**: Must be cancellable. Must not fire during active tool call
- **Thread safety**: Connection cache operations must be async-safe under concurrent calls

### Error Handling Contract

| Error condition | Behavior |
|----------------|----------|
| Command not on PATH | Raise descriptive error with hints |
| Connection timeout (connect_timeout exceeded) | Raise timeout error |
| Server rejects initialize (wrong protocol version) | Raise with protocol version details |
| Server lacks tools capability | Raise, do not cache |
| Process crashes mid-connection | Next call creates fresh connection (stale cache invalidated) |

### Test Requirements

- [ ] All behavioral scenarios above
- [ ] Mock `stdio_client` + `ClientSession` — verify context manager lifecycle (enter/exit counts)
- [ ] Parallel calls with different keys → concurrent execution, no interference
- [ ] Parallel calls with same key → one connection, no race
- [ ] `shutdown_all` closes all connections
- [ ] `disconnect` removes from cache, closes transport
- [ ] Idle cleanup: mock timer, verify connection closed after timeout
- [ ] Server crash: verify cache invalidated, next call creates fresh

### BDD Coverage
- F5: All connection lifecycle scenarios (5.1–5.9)
- F3.1, F3.3: Connect flow (stdio + HTTP)

---

## Task 4: Tool Handler

**Files:**
- Create: `_tool_handler.py`
- Create: `tests/test_tool_handler.py`

**Dependencies:** Task 3 (SkillMcpManager interface), Task 1 (config types)

**Goal:** Async handler for `skill_mcp` tool. Validates args, finds skill MCP config, delegates to SkillMcpManager, returns standardized JSON result.

### Module Interface

```
_tool_handler.py
├── SKILL_MCP_SCHEMA: dict
│       OpenAI function-calling schema for skill_mcp tool.
│       Parameters: skill_name (required), mcp_name (required), tool_name, resource_name, prompt_name, arguments, grep
│
├── create_handler(manager: SkillMcpManager, skill_dirs: list[str] | None = None) -> Callable
│       Returns async handler function compatible with Hermes registry.
│       skill_dirs: override skill search paths (default: [~/.hermes/skills/, ~/.hermes/optional-skills/])
│
└── Handler behavior:
        async def handler(args: dict, **kwargs) -> str
            args keys: skill_name, mcp_name, tool_name?, resource_name?, prompt_name?, arguments?, grep?
            kwargs keys: session_id, task_id
            Returns: JSON string — {"ok": true, "data": ...} or {"ok": false, "error_code": "...", "message": "...", "retryable": bool}
```

### Behavioral Contract

**Argument Validation (before any I/O)**

| Given | When | Then |
|-------|------|------|
| `skill_name` missing/empty | handler called | `{"ok": false, "error_code": "INVALID_ARGS", ...}` |
| `mcp_name` missing/empty | handler called | same |
| Neither `tool_name`, `resource_name`, `prompt_name` | handler called | same |
| Both `tool_name` and `resource_name` | handler called | same |
| `tool_name` provided | handler called | proceeds to skill lookup |

**Skill/MCP Resolution**

| Given | When | Then |
|-------|------|------|
| `skill_name` not found in any `skill_dirs` | lookup | `{"ok": false, "error_code": "SKILL_NOT_FOUND", "message": "Skill 'X' not found in skill directories."}` |
| Skill found but no `mcp.yaml` | lookup | `{"ok": false, "error_code": "NO_MCP_CONFIG", ...}` |
| `mcp_name` not in skill's `mcp.yaml` | lookup | `{"ok": false, "error_code": "MCP_NOT_FOUND", "message": "... Available: sqlite, github"}` |

**Tool Execution (delegates to SkillMcpManager)**

| Given | When | Then |
|-------|------|------|
| Valid args, connection succeeds, tool exists | execute | `{"ok": true, "data": <tool result as string>}` |
| `tool_name` → call `session.call_tool(name=tool_name, arguments=arguments)` | execute | tool result extracted from MCP response content |
| `resource_name` → call `session.read_resource(uri=resource_name)` | execute | resource content returned |
| `prompt_name` → call `session.get_prompt(name=prompt_name, arguments=arguments)` | execute | prompt messages returned |
| `grep` parameter provided | after execute | output filtered: only lines matching regex returned |
| `grep` pattern invalid regex | after execute | output returned unfiltered |

**Error Handling (from MCP)**

| Error | Error Code | Retryable |
|-------|-----------|-----------|
| MCP SDK not installed | `MCP_SDK_MISSING` | false |
| Connection failed (command not found, timeout) | `MCP_CONNECT_FAILED` | true |
| Tool not found on server | `MCP_TOOL_NOT_FOUND` | false |
| Tool execution error | `MCP_TOOL_ERROR` | false |
| Server process exited mid-call | `MCP_SERVER_EXITED` | true |
| Unsupported protocol version | `MCP_UNSUPPORTED_PROTOCOL` | false |
| Server lacks tools capability | `MCP_TOOLS_UNAVAILABLE` | false |

**Response Format (strict)**
- Success: `{"ok": true, "data": <string>}`
- Error: `{"ok": false, "error_code": <string from table above>, "message": <human-readable>, "retryable": <bool>}`
- All fields present in every response
- Error messages redacted via `redact_credentials()` before returning

### Test Requirements

- [ ] All behavioral scenarios above (validation, resolution, execution, errors)
- [ ] Handler with mock `SkillMcpManager` (fake, not mock SDK)
- [ ] Every error code from table above triggered and verified
- [ ] Response format assertions: all 4 error fields present
- [ ] `grep` filtering: matching lines included, non-matching excluded
- [ ] `grep` with invalid regex: output unfiltered
- [ ] Mutual exclusivity: tool_name + resource_name, tool_name + prompt_name, neither
- [ ] `arguments` passed through to MCP call correctly
- [ ] Schema test: `SKILL_MCP_SCHEMA` structure matches required fields

### BDD Coverage
- F3: Happy path (3.1–3.6)
- F4: Error cases (4.1–4.15)
- F8: Tool schema (8.1–8.2)

---

## Task 5: skill_view Hook

**Files:**
- Create: `_skill_view_hook.py`
- Create: `tests/test_skill_view_hook.py`

**Dependencies:** Task 1 (_config.parse_mcp_config), Task 0 (hook contract verified)

**Goal:** `transform_tool_result` hook that appends static MCP server info when `skill_view` is called for a skill with `mcp.yaml`. No MCP handshake — static config display only.

### Module Interface

```
_skill_view_hook.py
└── create_hook(skill_dirs: list[str] | None = None) -> Callable
        Returns hook function compatible with Hermes transform_tool_result.
        Hook signature matches Hermes contract (discovered in Task 0).
```

### Behavioral Contract

**Hook Behavior**

| Given | When | Then |
|-------|------|------|
| Hook invoked with `tool_name="skill_view"`, valid JSON result with `path` field | called | parses result, reads `mcp.yaml` from path, appends "## MCP Servers" section, returns modified result string |
| Hook invoked with `tool_name="terminal"` (any non-skill_view) | called | returns `None` — no modification |
| `skill_view` result is not valid JSON | called | returns original result unmodified |
| `skill_view` result has no `path` field | called | returns original result unmodified |
| `mcp.yaml` not found at path | called | returns original result unmodified |
| `mcp.yaml` has multiple servers | called | all servers listed with static config |
| `skill_view` result has error status (`"ok": false`) | called | returns original result unmodified |

**MCP Section Format (appended to result)**

```
## MCP Servers

### {server_name}

*Static config — connect on first `skill_mcp` call.*

**Configuration:**
  command: {command} {args}
  timeout: {timeout}s
  connect_timeout: {connect_timeout}s
  idle_timeout: {idle_timeout}s

Use `skill_mcp(skill_name="{name}", mcp_name="{server_name}", tool_name="...", arguments={...})` to invoke.
```

- NO `list_tools()` call — no MCP handshake
- NO tool names/descriptions listed (unknown until first call)
- HTTP servers: show `url` + `headers` keys (credentials redacted) instead of `command`

### Test Requirements

- [ ] All behavioral scenarios above
- [ ] Hook with real `_config.parse_mcp_config` on temp skill with `mcp.yaml`
- [ ] Hook for skill without `mcp.yaml` — no MCP section
- [ ] Hook for non-skill_view tool — returns None
- [ ] Hook with malformed JSON — returns original string
- [ ] Hook with error-status skill_view result — pass through
- [ ] MCP section format verification — contains expected strings, no tool names
- [ ] Multiple servers listed

### BDD Coverage
- F6: All skill_view hook scenarios (6.1–6.6)

---

## Task 6: Plugin Entry Point

**Files:**
- Create/Modify: `__init__.py`
- Create: `tests/test_plugin_entry.py`

**Dependencies:** Task 3 (SkillMcpManager), Task 4 (handler), Task 5 (hook), Task 0 (API contract)

**Goal:** `register(ctx)` function — glues all modules, registers tool + hook. Single entry point called by Hermes PluginManager.

### Module Interface

```
__init__.py
└── register(ctx: PluginContext) -> None
        Called by Hermes at plugin discovery.
        Creates ONE SkillMcpManager instance.
        Registers skill_mcp tool in "skill-mcp" toolset.
        Registers transform_tool_result hook.
        All imports deferred to function body (not module level).
```

### Behavioral Contract

**register(ctx)**

| Given | When | Then |
|-------|------|------|
| Plugin discovered, `mcp` SDK installed | `register(ctx)` called | `ctx.register_tool(name="skill_mcp", toolset="skill-mcp", handler=..., check_fn=check_mcp_sdk_available, is_async=True)` called exactly once |
| Same `manager` instance passed to handler and hook | registered | handler and hook share one `SkillMcpManager` |
| `ctx.register_hook("transform_tool_result", ...)` called | registered | hook function registered for `transform_tool_result` event |
| `mcp` SDK NOT installed | `register(ctx)` called | `check_fn` returns `False` → tool registered but toolset unavailable to agent |
| Plugin imported | import | no `ImportError` even if `mcp` not installed (deferred imports) |

**Imports must be deferred:**
- All `from . import _config, _connection, ...` inside `register()` body
- No module-level imports that would fail without `mcp` SDK

### Test Requirements

- [ ] `register(mock_ctx)` — verify `register_tool` called with correct params
- [ ] `register(mock_ctx)` — verify `register_hook` called with event name + callable
- [ ] Same `SkillMcpManager` instance passed to handler and hook factories
- [ ] `check_fn` returns `True` when `mcp` importable
- [ ] `check_fn` returns `False` when `mcp` import fails (mock ImportError)
- [ ] Module importable without `mcp` SDK installed (mock sys.modules)

### BDD Coverage
- F1: Plugin discovery scenarios (1.1–1.3)

---

## Task 7: End-to-End Integration Tests

**Files:**
- Create: `tests/test_e2e.py`

**Dependencies:** All previous tasks complete

**Goal:** Verify full pipeline with real MCP server. Parse config → connect → call tool → get result. Verify gateway multi-user isolation.

### Test Requirements

**7.1 Real MCP Server Flow**
- [ ] Create temp skill with `mcp.yaml` pointing to `uvx mcp-server-time`
- [ ] `parse_mcp_config()` returns valid config
- [ ] `SkillMcpManager.get_or_create_client()` connects successfully
- [ ] `client.list_tools()` returns time tools
- [ ] `client.call_tool(name="get_current_time", ...)` returns time data
- [ ] Result contains recognizable time/date string
- [ ] `manager.shutdown_all()` cleans up — no zombie process
- [ ] Skip test gracefully if `uvx` or `mcp-server-time` not installed (mark skip, not fail)

**7.2 skill_view Hook Integration**
- [ ] `skill_view` result augmented with static MCP section
- [ ] Static section does NOT contain tool names (no handshake performed)
- [ ] Static section contains correct command + timeout

**7.3 Gateway Multi-User Isolation**
- [ ] Two different `session_id` values → two separate MCP processes spawned
- [ ] Each process responds independently
- [ ] Disconnecting one session does not affect the other

### BDD Coverage
- End-to-end: install → view → call → get result → cleanup
- F5.3: session isolation

---

## Task 8: Edge Cases & Stress Tests

**Files:**
- Create: `tests/test_edge_cases.py`

**Dependencies:** All previous tasks complete

**Goal:** Concurrency, cleanup, resource leak, and error format consistency tests.

### Test Requirements

**8.1 Concurrency**
- [ ] 5 parallel calls with same `(session_id, skill_name, mcp_name)` → one connection created, all get same client
- [ ] 5 parallel calls with different keys → 5 connections, no interference
- [ ] Parallel calls with mock MCP client that has internal delay → correct serialization

**8.2 Resource Cleanup**
- [ ] Create 10 connections → `shutdown_all()` → all closed, zero remaining
- [ ] 100 create/call/disconnect cycles → no subprocess leak, fd count returns to baseline
- [ ] Memory: 100 cycles with mock → Python object count growth < 10%

**8.3 Error Format Consistency**
- [ ] Every error path returns `{"ok": false, "error_code": str, "message": str, "retryable": bool}`
- [ ] No error path returns non-JSON, partial dict, or missing fields
- [ ] Test all error codes from Task 4 table

**8.4 Idle Cleanup**
- [ ] Mock timer: connection unused for `idle_timeout` seconds → disconnected
- [ ] Active connection (recently used) → not cleaned up
- [ ] Cleanup during active tool call → deferred until call completes

### BDD Coverage
- F5.7, F5.8: concurrency
- F9: Non-functional (memory, latency, platform)

---

## Task 9: Final Verification & Polish

**Files:** None (verification only)

**Dependencies:** All tasks complete

### Checklist

- [ ] Full test suite: `pytest tests/ -v` — all pass or explicitly skipped
- [ ] Placeholder scan: `grep -r "TODO\|TBD\|NotImplemented\|pass  #\|placeholder" *.py tests/` — zero findings
- [ ] Import chain: `python -c "import _config, _security, _connection, _tool_handler, _skill_view_hook"` succeeds
- [ ] BDD coverage: every Feature has passing tests
- [ ] Plugin dir structure matches File Map
- [ ] `pyproject.toml` installs: `pip install -e .` succeeds
- [ ] Plugin deployed to test Hermes: `cp -r . ~/.hermes/plugins/skill-mcp/`
- [ ] `hermes tools` shows `skill-mcp` toolset when `mcp` SDK installed
- [ ] `hermes tools` hides `skill-mcp` when `mcp` SDK missing
- [ ] Agent can complete: load skill → `skill_view` shows MCP → `skill_mcp` calls tool → result used

---

## Self-Review

### BDD Coverage Matrix

| Feature | Scenarios | Task |
|---------|-----------|------|
| F1: Plugin Discovery | 1.1–1.3 | Task 0 (API verify) + Task 6 |
| F2: Config Discovery | 2.1–2.12 | Task 1 |
| F3: Happy Path | 3.1–3.6 | Task 3 (connect) + Task 4 (handler) |
| F4: Error Cases | 4.1–4.15 | Task 4 |
| F5: Connection Lifecycle | 5.1–5.9 | Task 3 + Task 8 |
| F6: skill_view Hook | 6.1–6.6 | Task 5 |
| F7: Security | 7.1–7.7 | Task 2 |
| F8: Tool Schema | 8.1–8.2 | Task 4 |
| F9: Non-Functional | 9.1–9.5 | Task 8 |
| F10: Timeouts | 10.1–10.3 | Task 1 (config) + Task 3 (enforcement) |
| F11: mcp.yaml Schema | — | Task 1 |

### Placeholder Scan
- Zero `TODO`, `TBD`, `NotImplemented`, `placeholder` in plan
- All functions fully specified with behavioral contracts

### Type Consistency
- `SkillMcpManager` interface: consistent across Task 3,4,5,6
- `parse_mcp_config() -> dict[str, dict]`: consistent across Task 1,4,5
- Handler return: `str` (JSON) — consistent
- Hook return: `str | None` — consistent
- Error format: `{"ok", "error_code", "message", "retryable"}` — consistent across Task 4
- `check_mcp_sdk_available() -> bool`: consistent Task 1 → Task 6
