"""Tools command for installing and checking tool installations."""

import os
from typing import List, Optional

import typer

from ..tools_registry import get_tools_from_config
from .helpers import get_config


def _complete_tool_name(incomplete: str) -> List[str]:
    """Autocomplete tool names from config."""
    try:
        config = get_config()
        registry = get_tools_from_config(config)
        tools = registry.list_tools()
        return [t.name for t in tools if t.name.startswith(incomplete)]
    except Exception:
        return []


# Create tools sub-app
tools_app = typer.Typer(
    name="tools",
    help="Manage tool installations.",
    no_args_is_help=False,  # Allow 'freckle tools' to list
)


def register(app: typer.Typer) -> None:
    """Register tools command group with the app."""
    app.add_typer(tools_app, name="tools")


@tools_app.callback(invoke_without_command=True)
def tools_callback(
    ctx: typer.Context,
):
    """List configured tools and their installation status.

    Use 'freckle tools install <name>' to install a tool.
    Use 'freckle tools install --all' to install all missing tools.
    """
    # Only run list if no subcommand was invoked
    if ctx.invoked_subcommand is None:
        tools_list(None)


def tools_list(tool_name: Optional[str] = None):
    """List configured tools and their installation status."""
    config = get_config()
    registry = get_tools_from_config(config)

    all_tools = registry.list_tools()

    if not all_tools:
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

    # Filter to specific tool if requested
    if tool_name:
        tool = registry.get_tool(tool_name)
        if not tool:
            typer.echo(f"Tool '{tool_name}' not found in config.", err=True)
            typer.echo("")
            typer.echo("Available tools:")
            for t in all_tools:
                typer.echo(f"  - {t.name}")
            raise typer.Exit(1)
        all_tools = [tool]

    # Get available package managers
    available_pms = registry.get_available_managers()

    typer.echo("Configured tools:")
    typer.echo("")

    installed_count = 0
    not_installed = []

    for tool in all_tools:
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
    typer.echo(f"Installed: {installed_count}/{len(all_tools)}")

    if not_installed:
        typer.echo("")
        typer.echo("To install missing tools:")
        for name in not_installed:
            typer.echo(f"  freckle tools install {name}")


@tools_app.command(name="install")
def tools_install(
    tool_name: Optional[str] = typer.Argument(
        None,
        help="Tool name to install (omit if using --all)",
        autocompletion=_complete_tool_name,
    ),
    all_tools: bool = typer.Option(
        False, "--all", "-a",
        help="Install all missing tools"
    ),
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

    Examples:
        freckle tools install starship
        freckle tools install --all
    """
    config = get_config()
    registry = get_tools_from_config(config)

    if all_tools:
        _install_all_tools(registry, force)
        return

    if not tool_name:
        typer.echo("Error: provide a tool name or use --all", err=True)
        raise typer.Exit(1)

    tool = registry.get_tool(tool_name)

    if not tool:
        typer.echo(f"Tool '{tool_name}' not found in config.", err=True)
        typer.echo("")
        typer.echo("Available tools:")
        for t in registry.list_tools():
            typer.echo(f"  - {t.name}")
        raise typer.Exit(1)

    _install_single_tool(registry, tool, force)


def _install_single_tool(registry, tool, force: bool) -> bool:
    """Install a single tool. Returns True on success."""
    if tool.is_installed():
        version = tool.get_version() or "unknown"
        typer.echo(f"{tool.name} is already installed ({version})")
        return True

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
                return False

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
        return True
    else:
        typer.echo("")
        typer.echo(f"✗ Failed to install {tool.name}", err=True)
        return False


def _install_all_tools(registry, force: bool):
    """Install all missing tools."""
    all_tools = registry.list_tools()

    if not all_tools:
        typer.echo("No tools configured in .freckle.yaml")
        return

    # Find missing tools
    missing = [t for t in all_tools if not t.is_installed()]

    if not missing:
        typer.echo("All configured tools are already installed.")
        typer.echo("")
        for tool in all_tools:
            version = tool.get_version() or "installed"
            if len(version) > 40:
                version = version[:37] + "..."
            typer.echo(f"  ✓ {tool.name:15} {version}")
        return

    typer.echo(f"Installing {len(missing)} missing tool(s)...")
    typer.echo("")

    succeeded = 0
    failed = []

    for tool in missing:
        typer.echo(f"{'─' * 40}")
        if _install_single_tool(registry, tool, force):
            succeeded += 1
        else:
            failed.append(tool.name)
        typer.echo("")

    typer.echo(f"{'─' * 40}")
    typer.echo("")
    typer.echo(f"Installed: {succeeded}/{len(missing)}")

    if failed:
        typer.echo(f"Failed: {', '.join(failed)}")
        raise typer.Exit(1)
