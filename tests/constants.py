"""Shared test constants and helpers."""
import os
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import yaml

PLUGIN_PATH = "/opt/hermes/plugins/hermes_skill_mcp"
SKILL_PATH = "/opt/data/skills/secret-skill"
SKILL_NAME = "secret-skill"
SERVER_NAME = "secret"
TOOL_NAME = "get_secret"
MAGIC_PHRASE = "zebra-moon-7xq9k"
CONFIG_PATH = "/opt/data/config.yaml"
SKILLS_DIR = "/opt/data/skills"
CLI_TIMEOUT = 30
E2E_TIMEOUT = 180
MODEL_KEY = "model"


def make_manager():
    """Create a fresh SkillMcpManager instance."""
    import sys
    from importlib import util as iutil

    plugin_dir = Path(PLUGIN_PATH)
    plugin_dir_str = str(plugin_dir)
    if plugin_dir_str not in sys.path:
        sys.path.insert(0, plugin_dir_str)

    # Pre-load _security so lazy imports in _connection.py work
    sec_spec = iutil.spec_from_file_location(
        "_security", plugin_dir / "_security.py",
    )
    sec_mod = iutil.module_from_spec(sec_spec)
    sys.modules["_security"] = sec_mod
    sec_spec.loader.exec_module(sec_mod)

    conn_spec = iutil.spec_from_file_location(
        "_connection", plugin_dir / "_connection.py",
    )
    conn_mod = iutil.module_from_spec(conn_spec)
    sys.modules["_connection"] = conn_mod
    conn_spec.loader.exec_module(conn_mod)
    return conn_mod.SkillMcpManager()


@asynccontextmanager
async def connected_manager(skill_name, server_name, server_config):
    """Async context manager: yields connected manager, auto-closes."""
    manager = make_manager()
    await _connect(manager, skill_name, server_name, server_config)
    try:
        yield manager
    finally:
        await manager.close()


async def _connect(  # noqa: WPS210
        manager, skill_name, server_name, server_config,
    ) -> None:
    """Connect manager to MCP server."""
    await manager.get_or_create_client(
        skill_name, server_name, server_config,
    )


def run_hermes_e2e(args: list, cfg: dict) -> str:
    """Run hermes CLI with API credentials, return stdout."""
    _write_config(cfg)
    cmd_result = subprocess.run(
        ["hermes"] + args,
        capture_output=True, text=True,
        timeout=E2E_TIMEOUT,
        env=os.environ.copy(),
    )
    if cmd_result.returncode != 0:
        pytest.fail("Agent failed: {}".format(cmd_result.stderr))
    return cmd_result.stdout.strip()


def _write_config(cfg: dict) -> None:
    """Write hermes config with API credentials."""
    config = {
        MODEL_KEY: {
            "default": cfg[MODEL_KEY],
            "provider": "custom",
            "api_key": cfg["key"],
            "base_url": cfg["url"],
        },
        "skills": {"external_dirs": [SKILLS_DIR]},
    }
    cfg_dir = Path("/root/.hermes")
    cfg_dir.mkdir(parents=True, exist_ok=True)
    with open(cfg_dir / "config.yaml", "w") as config_file:
        yaml.dump(config, config_file)
