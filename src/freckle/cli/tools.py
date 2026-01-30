"""Tools command for installing and checking tool installations."""

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple

import typer

from ..tools_registry import get_tools_from_config
from .helpers import env, get_config, get_dotfiles_manager
from .output import console, error, muted, plain, success, warning
from .profile.helpers import get_current_branch


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

    # Filter by active profile's modules
    all_tools, active_modules = _get_profile_tools(registry)

    if not all_tools:
        plain("No tools configured in .freckle.yaml")
        plain("")
        plain("Add tools to your config like:")
        plain("")
        muted("  tools:")
        muted("    starship:")
        muted("      description: Cross-shell prompt")
        muted("      install:")
        muted("        brew: starship")
        muted("        cargo: starship")
        muted("      verify: starship --version")
        return

    # Filter to specific tool if requested
    if tool_name:
        tool = registry.get_tool(tool_name)
        if not tool:
            error(f"Tool '{tool_name}' not found in config.")
            plain("")
            plain("Available tools:")
            for t in all_tools:
                muted(f"  - {t.name}")
            raise typer.Exit(1)
        all_tools = [tool]

    # Get available package managers
    available_pms = registry.get_available_managers()

    plain("Configured tools:")
    plain("")

    installed_count = 0
    not_installed = []

    for tool in all_tools:
        if tool.is_installed():
            version = tool.get_version() or "installed"
            # Truncate long versions
            if len(version) > 40:
                version = version[:37] + "..."
            console.print(f"  [green]✓[/green] {tool.name:15} {version}")
            installed_count += 1
        else:
            # Show which package managers could install this
            installable_via = [
                pm for pm in tool.install.keys()
                if pm in available_pms or pm == "script"
            ]
            if installable_via:
                via = ", ".join(installable_via)
                console.print(
                    f"  [red]✗[/red] {tool.name:15} not installed (via: {via})"
                )
            else:
                console.print(
                    f"  [red]✗[/red] {tool.name:15} not installed (no method)"
                )
            not_installed.append(tool.name)

    plain("")
    plain(f"Installed: {installed_count}/{len(all_tools)}")

    if not_installed:
        plain("")
        plain("To install missing tools:")
        for name in not_installed:
            muted(f"  freckle tools install {name}")


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
        error("Provide a tool name or use --all")
        raise typer.Exit(1)

    tool = registry.get_tool(tool_name)

    if not tool:
        error(f"Tool '{tool_name}' not found in config.")
        plain("")
        plain("Available tools:")
        for t in registry.list_tools():
            muted(f"  - {t.name}")
        raise typer.Exit(1)

    _install_single_tool(registry, tool, force)


def _install_single_tool(registry, tool, force: bool) -> bool:
    """Install a single tool. Returns True on success."""
    if tool.is_installed():
        version = tool.get_version() or "unknown"
        plain(f"{tool.name} is already installed ({version})")
        return True

    plain(f"Installing {tool.name}...")
    if tool.description:
        muted(f"  {tool.description}")
    plain("")

    # Show available install methods
    available_pms = registry.get_available_managers()
    for pm, package in tool.install.items():
        if pm in available_pms:
            muted(f"  Available: {pm} ({package})")
        elif pm == "script":
            muted(f"  Available: curated script ({package})")

    plain("")

    # Handle script confirmation
    if "script" in tool.install and not force:
        # Check if we might need to use script
        has_pm = any(pm in available_pms for pm in tool.install.keys())
        if not has_pm:
            warning("This tool requires a curated script installation.")
            if not typer.confirm("Proceed with script installation?"):
                plain("Cancelled.")
                return False

            # Set env var for script confirmation
            os.environ["FRECKLE_CONFIRM_SCRIPTS"] = "1"

    install_success = registry.install_tool(tool, confirm_script=force)

    if install_success:
        plain("")
        success(f"{tool.name} installed successfully")

        # Verify installation
        if tool.is_installed():
            version = tool.get_version()
            if version:
                muted(f"  Version: {version}")
        return True
    else:
        plain("")
        error(f"Failed to install {tool.name}")
        return False


def _get_profile_tools(registry):
    """Get tools filtered by active profile's modules."""
    config = get_config()
    all_tools = registry.list_tools()

    # Get active profile's modules
    dotfiles = get_dotfiles_manager(config)
    current_branch = get_current_branch(config=config, dotfiles=dotfiles)
    if current_branch:
        active_modules = config.get_profile_modules(current_branch)
    else:
        active_modules = []

    if active_modules:
        filtered = [t for t in all_tools if t.name in active_modules]
        return filtered, active_modules
    return all_tools, []


@tools_app.command(name="config")
def tools_config(
    tool_name: str = typer.Argument(
        ...,
        help="Tool name to open config for",
        autocompletion=_complete_tool_name,
    ),
    list_only: bool = typer.Option(
        False, "--list", "-l",
        help="Just list config files, don't open"
    ),
):
    """Open a tool's config file in your editor.

    Uses $EDITOR or falls back to vim.

    Examples:
        freckle tools config git
        freckle tools config nvim
        freckle tools config starship --list
    """
    config = get_config()
    registry = get_tools_from_config(config)

    tool = registry.get_tool(tool_name)

    if not tool:
        error(f"Tool '{tool_name}' not found in config.")
        plain("")
        plain("Available tools:")
        for t in registry.list_tools():
            muted(f"  - {t.name}")
        raise typer.Exit(1)

    if not tool.config_files:
        plain(f"No config files defined for '{tool_name}'.")
        plain("")
        plain("Add config files in .freckle.yaml:")
        plain("")
        muted("  tools:")
        muted(f"    {tool_name}:")
        muted("      config:")
        muted(f"      - .config/{tool_name}/config")
        raise typer.Exit(1)

    # Resolve paths relative to home
    config_paths = []
    for cfg in tool.config_files:
        path = env.home / cfg
        config_paths.append(path)

    if list_only:
        plain(f"Config files for {tool_name}:")
        for path in config_paths:
            if path.exists():
                console.print(f"  [green]✓[/green] {path}")
            else:
                console.print(f"  [red]✗[/red] {path}")
        return

    # Filter to existing files
    existing = [p for p in config_paths if p.exists()]

    if not existing:
        plain(f"Config files for '{tool_name}' don't exist yet:")
        for path in config_paths:
            muted(f"  - {path}")
        plain("")
        if typer.confirm("Create them?"):
            for path in config_paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
                success(f"Created {path}", prefix="  ✓")
            existing = config_paths
        else:
            raise typer.Exit(1)

    # Open in editor
    editor = os.environ.get("EDITOR", "vim")

    plain(f"Opening {len(existing)} file(s) in {editor}...")

    try:
        subprocess.run([editor] + [str(p) for p in existing])
    except FileNotFoundError:
        error(f"Editor '{editor}' not found.")
        muted("Set $EDITOR or install vim.")
        raise typer.Exit(1)


def _install_tool_quiet(
    registry, tool, force: bool
) -> Tuple[str, bool, Optional[str]]:
    """Install a tool quietly, returning (name, success, version)."""
    # Set env var for script confirmation if force is True
    if force:
        os.environ["FRECKLE_CONFIRM_SCRIPTS"] = "1"

    try:
        success = registry.install_tool(tool, confirm_script=force)
        version = tool.get_version() if success else None
        return (tool.name, success, version)
    except Exception:
        return (tool.name, False, None)


def _install_all_tools(registry, force: bool):
    """Install all missing tools for the active profile in parallel."""
    profile_tools, active_modules = _get_profile_tools(registry)

    if not profile_tools:
        if active_modules:
            modules_str = ", ".join(active_modules)
            plain(f"No tools match profile modules: {modules_str}")
        else:
            plain("No tools configured in .freckle.yaml")
        return

    # Find missing tools
    missing = [t for t in profile_tools if not t.is_installed()]

    if not missing:
        plain("All configured tools are already installed.")
        plain("")
        for tool in profile_tools:
            version = tool.get_version() or "installed"
            if len(version) > 40:
                version = version[:37] + "..."
            console.print(f"  [green]✓[/green] {tool.name:15} {version}")
        return

    plain(f"Installing {len(missing)} missing tool(s) in parallel...")
    plain("")

    succeeded = []
    failed = []

    # Install tools in parallel
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(
                _install_tool_quiet, registry, tool, force
            ): tool
            for tool in missing
        }

        for future in as_completed(futures):
            name, ok, version = future.result()
            if ok:
                succeeded.append((name, version))
                ver_str = version[:37] + "..." if version and len(
                    version
                ) > 40 else (version or "installed")
                console.print(f"  [green]✓[/green] {name:15} {ver_str}")
            else:
                failed.append(name)
                console.print(f"  [red]✗[/red] {name:15} failed")

    plain("")
    plain(f"Installed: {len(succeeded)}/{len(missing)}")

    if failed:
        error(f"Failed: {', '.join(failed)}")
        raise typer.Exit(1)
