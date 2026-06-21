"""CLI entry point: hermes-skill-mcp install."""

import shutil
import sys
from pathlib import Path


def _print_usage() -> None:
    """Print usage and exit."""
    print(  # noqa: WPS421
        "Usage: hermes-skill-mcp install",
    )
    print(  # noqa: WPS421
        "       hermes-skill-mcp --version",
    )
    print(  # noqa: WPS421
        "       python -m hermes_skill_mcp install",
    )


def _handle_version() -> None:  # noqa: WPS221
    """Print version and return if --version flag."""
    is_version = (
        len(sys.argv) >= 2
        and sys.argv[1] in ("--version", "-V")
    )  # noqa: WPS221
    if is_version:
        from hermes_skill_mcp._metadata import PLUGIN_VERSION  # noqa: WPS433
        print(f"hermes-skill-mcp v{PLUGIN_VERSION}")  # noqa: WPS421
        sys.exit(0)


def main() -> None:  # noqa: WPS213
    """Install the plugin into ~/.hermes/plugins/skill-mcp/."""
    _handle_version()

    if len(sys.argv) < 2 or sys.argv[1] != "install":
        _print_usage()
        sys.exit(1)

    plugin_dir = Path.home() / ".hermes" / "plugins" / "skill-mcp"
    plugin_dir.mkdir(parents=True, exist_ok=True)

    source_dir = Path(__file__).parent
    plugin_yaml = source_dir / "plugin.yaml"
    if plugin_yaml.exists():
        shutil.copy2(plugin_yaml, plugin_dir / "plugin.yaml")
        print(f"Plugin registered at {plugin_dir}")  # noqa: WPS421
    else:
        print(  # noqa: WPS421
            f"plugin.yaml not found at {plugin_yaml}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
