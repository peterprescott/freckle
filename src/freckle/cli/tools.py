"""Tools command for installing and checking tool installations.

Supports both:
- Legacy hardcoded managers (git, zsh, tmux, nvim)
- Declarative tools defined in .freckle.yaml
"""

import os
from typing import Optional

import typer

from ..managers import GitManager, NvimManager, TmuxManager, ZshManager
from ..system import SystemPackageManager
from ..tools_registry import get_tools_from_config
from .helpers import env, get_config

# Map of tool names to manager classes (legacy support)
TOOL_MANAGERS = {
    "git": GitManager,
    "zsh": ZshManager,
    "tmux": TmuxManager,
    "nvim": NvimManager,
}


def register(app: typer.Typer) -> None:
    """Register tools commands with the app."""
    app.command(name="tools")(tools)
    app.command(name="tools-list")(tools_list)
    app.command(name="tools-install")(tools_install)


def tools(
    install: bool = typer.Option(
        False,
        "--install",
        "-i",
        help="Install missing tools and run setup hooks",
    ),
    tool_name: Optional[str] = typer.Argument(
        None, help="Specific tool to check/install"
    ),
):
    """Check or install configured tools (legacy managers).

    Shows the installation status of configured tools.
    Use --install to install missing tools and run setup hooks.

    Examples:
        freckle tools            # Show status of all tools
        freckle tools --install  # Install missing + run hooks
        freckle tools nvim       # Check nvim specifically
        freckle tools nvim -i    # Install/setup nvim
    """
    config = get_config()

    # Get configured tools from config, or default to all
    configured_tools = config.get("tools", list(TOOL_MANAGERS.keys()))

    # If tools is a dict (new format), extract keys for legacy check
    if isinstance(configured_tools, dict):
        # New declarative format - suggest using tools-list
        typer.echo(
            "Note: Declarative tools detected. "
            "Use 'freckle tools-list' for new-style tools."
        )
        typer.echo("")
        # Still check legacy managers
        configured_tools = list(TOOL_MANAGERS.keys())

    # Filter to specific tool if requested
    if tool_name:
        if tool_name not in TOOL_MANAGERS:
            typer.echo(f"Unknown tool: {tool_name}", err=True)
            typer.echo(f"Available tools: {', '.join(TOOL_MANAGERS.keys())}")
            raise typer.Exit(1)
        configured_tools = [tool_name]

    pkg_mgr = SystemPackageManager(env)

    typer.echo("\n--- Tool Status ---")
    typer.echo(f"Platform: {env.os_info['pretty_name']}")
    typer.echo("")

    missing_tools = []
    installed_managers = []

    for tool in configured_tools:
        if tool not in TOOL_MANAGERS:
            continue

        manager_class = TOOL_MANAGERS[tool]
        manager = manager_class(env, pkg_mgr)

        info = pkg_mgr.get_binary_info(manager.bin_name)

        if info["found"]:
            version = info["version"]
            # Trim long version strings
            if len(version) > 50:
                version = version[:47] + "..."
            typer.echo(f"  ✓ {manager.name}: {version}")
            installed_managers.append(manager)
        else:
            typer.echo(f"  ✗ {manager.name}: not installed")
            missing_tools.append((tool, manager))

    typer.echo("")

    if not install:
        if missing_tools:
            typer.echo(
                f"{len(missing_tools)} tool(s) missing. "
                "Run 'freckle tools --install' to install."
            )
        else:
            typer.echo("All tools are installed.")
        return

    # Install missing tools
    if missing_tools:
        typer.echo(f"Installing {len(missing_tools)} tool(s)...\n")

        for tool, manager in missing_tools:
            typer.echo(f"  Installing {manager.name}...")
            try:
                manager.setup()
                typer.echo(f"  ✓ {manager.name} installed")
            except Exception as e:
                typer.echo(f"  ✗ {manager.name} failed: {e}", err=True)

        typer.echo("")

    # Run setup hooks for already-installed tools
    if installed_managers:
        typer.echo("Running setup hooks...\n")

        for manager in installed_managers:
            try:
                manager._post_install()
                typer.echo(f"  ✓ {manager.name} configured")
            except Exception as e:
                typer.echo(f"  ✗ {manager.name} setup failed: {e}", err=True)

    typer.echo("\nDone.")


def tools_list():
    """List all configured tools and their installation status.

    Shows tools defined in .freckle.yaml under the 'tools' section.

    Example:
        freckle tools-list
    """
    config = get_config()
    registry = get_tools_from_config(config)

    tools = registry.list_tools()

    if not tools:
        typer.echo("No tools configured in .freckle.yaml")
        typer.echo("")
        typer.echo("Add tools to your config like:")
        typer.echo("")
        typer.echo("  tools:")
        typer.echo("    starship:")
        typer.echo("      description: Cross-shell prompt")
        typer.echo("      install:")
        typer.echo("        brew: starship")
        typer.echo("        cargo: starship")
        typer.echo("      verify: starship --version")
        return

    # Get available package managers
    available_pms = registry.get_available_managers()

    typer.echo("Configured tools:")
    typer.echo("")

    installed_count = 0
    not_installed = []

    for tool in tools:
        if tool.is_installed():
            version = tool.get_version() or "installed"
            # Truncate long versions
            if len(version) > 40:
                version = version[:37] + "..."
            typer.echo(f"  ✓ {tool.name:15} {version}")
            installed_count += 1
        else:
            # Show which package managers could install this
            installable_via = [
                pm for pm in tool.install.keys()
                if pm in available_pms or pm == "script"
            ]
            if installable_via:
                via = ", ".join(installable_via)
                typer.echo(f"  ✗ {tool.name:15} not installed (via: {via})")
            else:
                typer.echo(f"  ✗ {tool.name:15} not installed (no method)")
            not_installed.append(tool.name)

    typer.echo("")
    typer.echo(f"Installed: {installed_count}/{len(tools)}")

    if not_installed:
        typer.echo("")
        typer.echo("To install missing tools:")
        for name in not_installed:
            typer.echo(f"  freckle tools-install {name}")


def tools_install(
    tool_name: str = typer.Argument(..., help="Tool name to install"),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Skip confirmation for script installations"
    ),
):
    """Install a configured tool.

    Tries package managers in order of preference:
    1. brew (if available)
    2. apt (if available)
    3. cargo/pip/npm (if available)
    4. Curated script (with confirmation)

    Example:
        freckle tools-install starship
    """
    config = get_config()
    registry = get_tools_from_config(config)

    tool = registry.get_tool(tool_name)

    if not tool:
        typer.echo(f"Tool '{tool_name}' not found in config.", err=True)
        typer.echo("")
        typer.echo("Available tools:")
        for t in registry.list_tools():
            typer.echo(f"  - {t.name}")
        raise typer.Exit(1)

    if tool.is_installed():
        version = tool.get_version() or "unknown"
        typer.echo(f"{tool.name} is already installed ({version})")
        return

    typer.echo(f"Installing {tool.name}...")
    if tool.description:
        typer.echo(f"  {tool.description}")
    typer.echo("")

    # Show available install methods
    available_pms = registry.get_available_managers()
    for pm, package in tool.install.items():
        if pm in available_pms:
            typer.echo(f"  Available: {pm} ({package})")
        elif pm == "script":
            typer.echo(f"  Available: curated script ({package})")

    typer.echo("")

    # Handle script confirmation
    if "script" in tool.install and not force:
        # Check if we might need to use script
        has_pm = any(pm in available_pms for pm in tool.install.keys())
        if not has_pm:
            typer.echo(
                "This tool requires a curated script installation."
            )
            if not typer.confirm("Proceed with script installation?"):
                typer.echo("Cancelled.")
                return

            # Set env var for script confirmation
            os.environ["FRECKLE_CONFIRM_SCRIPTS"] = "1"

    success = registry.install_tool(tool, confirm_script=force)

    if success:
        typer.echo("")
        typer.echo(f"✓ {tool.name} installed successfully")

        # Verify installation
        if tool.is_installed():
            version = tool.get_version()
            if version:
                typer.echo(f"  Version: {version}")
    else:
        typer.echo("")
        typer.echo(f"✗ Failed to install {tool.name}", err=True)
        raise typer.Exit(1)
