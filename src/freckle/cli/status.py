"""Status command for freckle CLI."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Optional

import typer

from ..tools_registry import ToolDefinition, get_tools_from_config
from .helpers import env, get_config, get_config_path, get_dotfiles_manager
from .profile.helpers import get_current_branch


@dataclass
class ToolStatus:
    """Result of checking a tool's installation status."""

    tool: ToolDefinition
    is_installed: bool
    version: Optional[str] = None


def check_tool_status(tool: ToolDefinition) -> ToolStatus:
    """Check if a tool is installed and get its version (thread-safe)."""
    is_installed = tool.is_installed()
    version = None
    if is_installed:
        version = tool.get_version() or "installed"
        if len(version) > 40:
            version = version[:37] + "..."
    return ToolStatus(tool=tool, is_installed=is_installed, version=version)


def check_tools_parallel(tools: List[ToolDefinition]) -> List[ToolStatus]:
    """Check all tools in parallel and return results in original order."""
    if not tools:
        return []

    # Use ThreadPoolExecutor for I/O-bound subprocess calls
    results = {}
    with ThreadPoolExecutor(max_workers=min(8, len(tools))) as executor:
        future_to_tool = {
            executor.submit(check_tool_status, tool): tool for tool in tools
        }
        for future in as_completed(future_to_tool):
            tool = future_to_tool[future]
            try:
                results[tool.name] = future.result()
            except Exception:
                # If check fails, mark as not installed
                results[tool.name] = ToolStatus(
                    tool=tool, is_installed=False, version=None
                )

    # Return in original order
    return [results[tool.name] for tool in tools]


def register(app: typer.Typer) -> None:
    """Register the status command with the app."""
    app.command()(status)


def status():
    """Show current setup status and check for updates."""
    config = get_config()

    repo_url = config.get("dotfiles.repo_url")

    typer.echo("\n--- freckle Status ---")
    typer.echo(
        f"OS     : {env.os_info['pretty_name']} ({env.os_info['machine']})"
    )
    typer.echo(f"Kernel : {env.os_info['release']}")
    typer.echo(f"User   : {env.user}")

    dotfiles = None
    if repo_url:
        # get_dotfiles_manager now detects actual git branch
        dotfiles = get_dotfiles_manager(config)

    # Get tools from declarative config, filtered by active profile
    registry = get_tools_from_config(config)
    all_tools = registry.list_tools()

    # Filter by active profile's modules
    current_branch = get_current_branch(config=config, dotfiles=dotfiles)
    if current_branch:
        active_modules = config.get_profile_modules(current_branch)
    else:
        active_modules = []

    if active_modules:
        tools = [t for t in all_tools if t.name in active_modules]
    else:
        tools = all_tools

    # Freckle config status
    config_path = get_config_path()
    config_filename = config_path.name
    typer.echo("\nConfiguration:")
    if config_path.exists():
        if dotfiles:
            file_status = dotfiles.get_file_sync_status(config_filename)
            status_str = {
                "up-to-date": "✓ up-to-date",
                "modified": "⚠ modified locally",
                "behind": "↓ update available (behind remote)",
                "untracked": "✗ not tracked in dotfiles",
                "missing": "✓ local only",
                "not-found": "✓ local only",
                "error": "⚠ error checking status",
            }.get(file_status, f"status: {file_status}")
            typer.echo(f"  {config_filename} : {status_str}")
        else:
            typer.echo(f"  {config_filename} : ✓ exists (no dotfiles repo)")
    else:
        typer.echo(f"  {config_filename} : ✗ not found (run 'freckle init')")

    # Collect all config files associated with tools
    tool_config_files = set()

    if tools:
        typer.echo("\nConfigured Tools:")

        # Check all tools in parallel for faster status
        tool_statuses = check_tools_parallel(tools)

        for ts in tool_statuses:
            if ts.is_installed:
                typer.echo(f"  {ts.tool.name}:")
                typer.echo(f"    Status : ✓ {ts.version}")
            else:
                typer.echo(f"  {ts.tool.name}: ✗ not installed")
                continue

            if dotfiles and ts.tool.config_files:
                for cfg in ts.tool.config_files:
                    tool_config_files.add(cfg)
                    file_status = dotfiles.get_file_sync_status(cfg)
                    if file_status == "not-found":
                        continue

                    status_str = {
                        "up-to-date": "✓ up-to-date",
                        "modified": "⚠ modified locally",
                        "behind": "↓ update available (behind remote)",
                        "untracked": "✗ not tracked",
                        "missing": "✗ missing from home",
                        "error": "⚠ error checking status",
                    }.get(file_status, f"status: {file_status}")

                    typer.echo(f"    Config : {status_str} ({cfg})")

    # Show all other tracked files
    if dotfiles:
        all_tracked = dotfiles.get_tracked_files()
        other_tracked = [
            f
            for f in all_tracked
            if f not in (".freckle.yaml", ".freckle.yml")
            and f not in tool_config_files
        ]

        if other_tracked:
            typer.echo("\nOther Tracked Files:")
            for f in sorted(other_tracked):
                file_status = dotfiles.get_file_sync_status(f)
                status_str = {
                    "up-to-date": "✓",
                    "modified": "⚠ modified",
                    "behind": "↓ behind",
                    "missing": "✗ missing",
                    "error": "?",
                }.get(file_status, "?")
                typer.echo(f"  {status_str} {f}")

    # Global Dotfiles Status
    if not repo_url:
        typer.echo("\nDotfiles: Not configured (run 'freckle init')")
    elif dotfiles:
        typer.echo(f"\nDotfiles ({repo_url}):")
        try:
            report = dotfiles.get_detailed_status()
            if not report["initialized"]:
                typer.echo("  Status: Not initialized")
            else:
                branch_info = report.get("branch_info", {})
                effective_branch = report.get("branch", "main")

                reason = branch_info.get("reason", "exact")
                if reason == "exact":
                    typer.echo(f"  Branch: {effective_branch}")
                elif reason == "main_master_swap":
                    typer.echo(f"  Branch: {effective_branch}")
                    configured = branch_info.get("configured")
                    typer.echo(
                        f"    Note: '{configured}' not found, "
                        f"using '{effective_branch}'"
                    )
                elif reason == "not_found":
                    typer.echo(
                        f"  Branch: {effective_branch} "
                        "(configured, but not found!)"
                    )
                    available = branch_info.get("available", [])
                    if available:
                        typer.echo(
                            f"    Available branches: {', '.join(available)}"
                        )
                    else:
                        typer.echo(
                            "    No branches found - is this repo initialized?"
                        )
                else:
                    typer.echo(f"  Branch: {effective_branch}")
                    if branch_info.get("message"):
                        typer.echo(f"    Note: {branch_info['message']}")

                typer.echo(f"  Local Commit : {report['local_commit']}")

                if report.get("remote_branch_missing"):
                    typer.echo(
                        f"  Remote Commit: ✗ No origin/"
                        f"{effective_branch} branch!"
                    )
                    typer.echo(
                        f"    The local '{effective_branch}' branch "
                        "has no remote counterpart."
                    )
                    typer.echo("    To push it: freckle save")
                else:
                    remote = report.get("remote_commit", "N/A")
                    typer.echo(f"  Remote Commit: {remote}")

                if report.get("fetch_failed"):
                    typer.echo("  Remote Status: ⚠ Could not fetch (offline?)")

                if report["has_local_changes"]:
                    typer.echo("  Local Changes: Yes (uncommitted changes)")
                else:
                    typer.echo("  Local Changes: No")

                if report.get("remote_branch_missing"):
                    pass
                elif report.get("is_ahead"):
                    ahead = report.get("ahead_count", 0)
                    typer.echo(
                        f"  Ahead: Yes ({ahead} commits not pushed)"
                    )

                if report.get("is_behind"):
                    behind = report.get("behind_count", 0)
                    typer.echo(
                        f"  Behind: Yes ({behind} commits to pull)"
                    )
                elif not report.get("fetch_failed") and not report.get(
                    "remote_branch_missing"
                ):
                    typer.echo("  Behind: No (up to date)")

        except Exception as e:
            typer.echo(f"  Error checking status: {e}")
    typer.echo("")
