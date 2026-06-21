"""
hermes-skill-mcp: Dynamic MCP server loading from Hermes skills.

A Hermes Agent plugin that lets skills declare their own MCP servers
via a ``mcp.yaml`` sidecar file. The plugin registers a single
``skill_mcp`` tool that connects to MCP servers on demand —
no global config.yaml editing, no agent restart, no tool schema bloat.

Quick Start:
    1. Install: ``git clone <repo> ~/.hermes/plugins/skill-mcp/``
    2. Add ``mcp.yaml`` beside any SKILL.md
    3. Agent calls ``skill_mcp(mcp_name="...", tool_name="...", arguments='...')``

See BDD.md for full behavior specification.
"""


def register(ctx):
    """Called by Hermes PluginManager at plugin discovery.

    Creates one SkillMcpManager instance. Registers:
    - skill_mcp tool in "skill-mcp" toolset
    - transform_tool_result hook

    All imports deferred — no module-level ImportError without mcp SDK.
    """
    try:
        from ._config import check_mcp_sdk_available
        from ._connection import SkillMcpManager
        from ._tool_handler import SKILL_MCP_SCHEMA, create_handler
        from ._skill_view_hook import create_hook
    except ImportError:
        from _config import check_mcp_sdk_available  # type: ignore[no-redef]
        from _connection import SkillMcpManager  # type: ignore[no-redef]
        from _tool_handler import SKILL_MCP_SCHEMA, create_handler  # type: ignore[no-redef]
        from _skill_view_hook import create_hook  # type: ignore[no-redef]
    manager = SkillMcpManager()

    ctx.register_tool(
        name="skill_mcp",
        toolset="skill-mcp",
        schema=SKILL_MCP_SCHEMA,
        handler=create_handler(manager),
        check_fn=check_mcp_sdk_available,
        is_async=True,
        emoji="🔌",
    )

    ctx.register_hook("transform_tool_result", create_hook())
