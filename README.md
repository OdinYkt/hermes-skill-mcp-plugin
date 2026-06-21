# hermes-skill-mcp

Let Hermes skills bring their own MCP servers. Drop a `mcp.yaml` next to
any `SKILL.md` and the agent can call those servers through one tool —
no config editing, no restart.

## Install

```bash
git clone https://github.com/aqa-vibes/hermes-skill-mcp-plugin.git \
  ~/.hermes/plugins/skill-mcp
hermes plugins enable skill-mcp
```

To update later: `cd ~/.hermes/plugins/skill-mcp && git pull`

## Usage

1. Add `mcp.yaml` beside a `SKILL.md`:

```yaml
sqlite:
  command: "uvx"
  args: ["mcp-server-sqlite"]
  timeout: 30
```

2. The agent can now call:

```
skill_mcp(skill_name="my-skill", mcp_name="sqlite",
          tool_name="query", arguments={"sql": "SELECT 1"})
```

Also supports `resource_name` and `prompt_name` for MCP resources and
prompts. Set `grep` to filter output lines.

## Context overhead

Without the plugin: agent has no access to skill MCP servers. With the
plugin: one tool (`skill_mcp`) added to toolset `skill-mcp`. The tool
description is ~80 tokens.

> **TODO:** measure actual context token difference with/without plugin
> enabled. Compare system prompt size, tool schema overhead, and per-turn
> context for a typical 3-tool skill.

## What's tested

135 tests pass in Docker, 0 failures. `./scripts/run-tests.sh` if you
want to verify locally.

| Area | Coverage |
|---|---|
| Config parsing (12 scenarios) | ✅ env expansion, path resolution, defaults, validation |
| Security (7 scenarios) | ✅ env filtering, credential redaction, denylist |
| Connection lifecycle (9 scenarios) | ✅ lazy connect, session keys, concurrent locking, shutdown |
| Error handling (15 scenarios) | ✅ all BDD error codes mapped |
| skill_view augmentation (6 scenarios) | ✅ static MCP list in skill display |
| Timeouts | 🟡 HTTP passes timeout; stdio connect_timeout not enforced |
| HTTP transport | 🟡 config parsing tested; runtime HTTP not covered |
| Duplicate YAML keys | ❌ YAML lib silently overwrites; no detection |

## Known limitations

- **Duplicate YAML keys**: PyYAML overwrites silently. If `mcp.yaml`
  defines the same server name twice, the second entry wins. BDD 2.4
  wants a warning — not implemented.
- **stdio connect_timeout**: only HTTP transport respects it. stdio
  connections don't have a timeout wrapper.
- **No auto-update**: `git pull` in the plugin directory. Hermes has no
  plugin manager.
- **No perf benchmarks**: parse latency and cached overhead are not
  measured yet.

## Files

```
src/hermes_skill_mcp/
├── __init__.py          register(ctx)
├── _config.py           mcp.yaml → dict
├── _security.py         env filter, redact, denylist
├── _connection.py       MCP client cache, stdio/HTTP, lifecycle
├── _tool_handler.py     async skill_mcp handler, 15 error codes
├── _skill_view_hook.py  append MCP list to skill_view output
└── plugin.yaml          Hermes manifest
```

## License

MIT
