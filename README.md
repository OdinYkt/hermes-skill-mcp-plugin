# hermes-skill-mcp

Dynamic MCP server loading from Hermes skills. Skills carry MCP servers via
`mcp.yaml` sidecar. Agent calls `skill_mcp(skill_name, mcp_name, tool_name, arguments)`.
No `config.yaml` editing. No restart. One tool in schema.

## Quick Install

```bash
git clone <repo> ~/.hermes/plugins/skill-mcp/
pip install -e ~/.hermes/plugins/skill-mcp/
```

## Usage

1. Add `mcp.yaml` beside any `SKILL.md`:

```yaml
sqlite:
  command: "uvx"
  args: ["mcp-server-sqlite"]
  timeout: 30
```

2. Agent calls:

```
skill_mcp(skill_name="my-skill", mcp_name="sqlite", tool_name="query", arguments={"sql": "SELECT 1"})
```

## Running Tests

```bash
./scripts/run-tests.sh
```

Requires Docker. Set `HERMES_API_KEY` env var for E2E tests (skipped otherwise).

## BDD Coverage Matrix

68 scenarios across 11 features. Status: 135 tests, 0 failures.

| Feature | Scenarios | Status |
|---|---|---|
| F1: Plugin discovery & registration | 1.1-1.3 | 🟡 register(ctx) code exists, no direct test |
| F2: MCP config discovery | 2.1-2.12 | ✅ 11/12 — 2.4 duplicate YAML not detected at parse |
| F3: skill_mcp happy path | 3.1-3.6 | ✅ stdio tested, HTTP parse only |
| F4: skill_mcp error cases | 4.1-4.15 | ✅ 15 error codes mapped in handler pipeline |
| F5: Connection lifecycle | 5.1-5.9 | ✅ session keys, isolation, locking, shutdown |
| F6: skill_view augmentation | 6.1-6.6 | ✅ hook + static MCP list |
| F7: Security | 7.1-7.7 | 🟡 env filtering + redaction; denylist connect-time, PATH warning absent |
| F8: Tool schema | 8.1-8.2 | ✅ schema + async handler signature |
| F9: Timeouts | 9.1-9.3 | 🟡 HTTP passes timeout; stdio connect_timeout not enforced |
| F10: Non-functional | 10.1-10.5 | 🟡 perf tests marked @pytest.mark.slow |
| F11: Config schema | reference | ✅ known fields, command/url XOR, defaults |

## Architecture

```
__init__.py          — plugin entrypoint: register(ctx) → tools + hooks
_config.py           — mcp.yaml parser: validate, normalize, expand env
_security.py         — env filtering, credential redaction, command denylist
_connection.py       — MCP connection manager: lazy connect, cache, lifecycle
_tool_handler.py     — async handler: validate args, resolve skill, execute
_skill_view_hook.py  — transform_tool_result hook: static MCP list in skill_view
```

## License

MIT
