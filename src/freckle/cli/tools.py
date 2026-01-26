"""Tools command for installing and checking tool installations."""

from typing import Optional

import typer

from ..managers import GitManager, NvimManager, TmuxManager, ZshManager
from ..system import SystemPackageManager
from ..utils import setup_logging
from .helpers import env, get_config

# Map of tool names to manager classes
TOOL_MANAGERS = {
    "git": GitManager,
    "zsh": ZshManager,
    "tmux": TmuxManager,
    "nvim": NvimManager,
}


def register(app: typer.Typer) -> None:
    """Register the tools command with the app."""
    app.command()(tools)


def tools(
    install: bool = typer.Option(False, "--install", "-i", help="Install missing tools and run setup hooks"),
    tool_name: Optional[str] = typer.Argument(None, help="Specific tool to check/install"),
):
    """Check or install configured tools.
    
    Shows the installation status of all configured tools (git, zsh, tmux, nvim).
    Use --install to install any missing tools and run setup hooks for all tools.
    
    Examples:
        freckle tools              # Show status of all tools
        freckle tools --install    # Install missing tools and run all setup hooks
        freckle tools nvim         # Check nvim specifically
        freckle tools nvim -i      # Install/setup nvim
    """
    setup_logging()
    config = get_config()
    
    # Get configured tools from config, or default to all
    configured_tools = config.get("tools", list(TOOL_MANAGERS.keys()))
    
    # Filter to specific tool if requested
    if tool_name:
        if tool_name not in TOOL_MANAGERS:
            typer.echo(f"Unknown tool: {tool_name}", err=True)
            typer.echo(f"Available tools: {', '.join(TOOL_MANAGERS.keys())}")
            raise typer.Exit(1)
        configured_tools = [tool_name]
    
    pkg_mgr = SystemPackageManager(env)
    
    typer.echo(f"\n--- Tool Status ---")
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
            typer.echo(f"{len(missing_tools)} tool(s) missing. Run 'freckle tools --install' to install.")
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
    
    # Run setup hooks for already-installed tools (e.g., lazy.nvim for nvim)
    if installed_managers:
        typer.echo("Running setup hooks...\n")
        
        for manager in installed_managers:
            try:
                manager._post_install()
                typer.echo(f"  ✓ {manager.name} configured")
            except Exception as e:
                typer.echo(f"  ✗ {manager.name} setup failed: {e}", err=True)
    
    typer.echo("\nDone.")
