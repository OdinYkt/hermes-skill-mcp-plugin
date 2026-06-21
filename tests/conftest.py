"""Test fixtures and shared utilities."""
import importlib
import os
import subprocess
from pathlib import Path
import pytest

PLUGIN_PATH = "/opt/hermes/plugins/hermes_skill_mcp"


def import_plugin_module(module_name: str):
    """Import a module from the skill-mcp plugin directory."""
    plugin_path = Path(PLUGIN_PATH)
    file_name = module_name.split(".")[-1]
    spec = importlib.util.spec_from_file_location(
        module_name,
        plugin_path / "{}.py".format(file_name),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def plugin_dir():
    """Path to the installed skill-mcp plugin."""
    path = Path(PLUGIN_PATH)
    assert path.exists(), "Plugin not found at {}".format(path)
    return path


@pytest.fixture(scope="session")
def hermes_bin():
    """Ensure hermes CLI is available."""
    cmd_result = subprocess.run(
        ["which", "hermes"], capture_output=True, text=True,
    )
    assert cmd_result.returncode == 0, "hermes CLI not found"
    return cmd_result.stdout.strip()


@pytest.fixture(scope="module")
def e2e_config():
    """API credentials from environment."""
    return {
        "key": os.environ.get("HERMES_API_KEY", ""),
        "url": os.environ.get("HERMES_API_URL", ""),
        "model": os.environ.get("HERMES_API_MODEL", ""),
    }


@pytest.fixture
def temp_skills_dir(tmp_path):
    """Temporary skills directory."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    return skills_dir


@pytest.fixture
def skill_with_mcp(tmp_path):
    """Fixture factory: create temp skill dir with mcp.yaml."""
    import yaml

    def _create(skill_name, mcp_config=None):
        skill_dir = tmp_path / skill_name
        skill_dir.mkdir(exist_ok=True)
        (skill_dir / "SKILL.md").write_text("# {}\n".format(skill_name))
        if mcp_config is not None:
            mcp_yaml = skill_dir / "mcp.yaml"
            mcp_yaml.write_text(yaml.dump(mcp_config))
        return skill_dir
    return _create


@pytest.fixture
def skill_without_mcp(tmp_path):
    """Fixture factory: create temp skill dir without mcp.yaml."""

    def _create(skill_name):
        skill_dir = tmp_path / skill_name
        skill_dir.mkdir(exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            "# {}\n".format(skill_name),
        )
        return skill_dir

    return _create
