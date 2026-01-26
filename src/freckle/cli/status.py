"""Status command for freckle CLI."""

import typer

from ..dotfiles import DotfilesManager
from ..tools_registry import get_tools_from_config
from .helpers import env, get_config, get_dotfiles_dir


def register(app: typer.Typer) -> None:
    """Register the status command with the app."""
    app.command()(status)


def status():
    """Show current setup status and check for updates."""
    config = get_config()

    repo_url = config.get("dotfiles.repo_url")
    dotfiles_dir = get_dotfiles_dir(config)
    branch = config.get("dotfiles.branch")

    typer.echo("\n--- freckle Status ---")
    typer.echo(
        f"OS     : {env.os_info['pretty_name']} ({env.os_info['machine']})"
    )
    typer.echo(f"Kernel : {env.os_info['release']}")
    typer.echo(f"User   : {env.user}")

    dotfiles = None
    if repo_url:
        dotfiles = DotfilesManager(repo_url, dotfiles_dir, env.home, branch)

    # Get tools from declarative config
    registry = get_tools_from_config(config)
    tools = registry.list_tools()

    # Freckle config status
    config_path = env.home / ".freckle.yaml"
    typer.echo("\nConfiguration:")
    if config_path.exists():
        if dotfiles:
            file_status = dotfiles.get_file_sync_status(".freckle.yaml")
            status_str = {
                "up-to-date": "✓ up-to-date",
                "modified": "⚠ modified locally",
                "behind": "↓ update available (behind remote)",
                "untracked": "✗ not tracked in dotfiles",
                "missing": "✓ local only",
                "not-found": "✓ local only",
                "error": "⚠ error checking status",
            }.get(file_status, f"status: {file_status}")
            typer.echo(f"  .freckle.yaml : {status_str}")
        else:
            typer.echo("  .freckle.yaml : ✓ exists (dotfiles not configured)")
    else:
        typer.echo("  .freckle.yaml : ✗ not found (run 'freckle init')")

    # Collect all config files associated with tools
    tool_config_files = set()

    if tools:
        typer.echo("\nConfigured Tools:")
        for tool in tools:
            if tool.is_installed():
                version = tool.get_version() or "installed"
                if len(version) > 40:
                    version = version[:37] + "..."
                typer.echo(f"  {tool.name}:")
                typer.echo(f"    Status : ✓ {version}")
            else:
                typer.echo(f"  {tool.name}: ✗ not installed")
                continue

            if dotfiles and tool.config_files:
                for cfg in tool.config_files:
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
            if f != ".freckle.yaml" and f not in tool_config_files
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
                effective_branch = report.get("branch", branch)

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
                    typer.echo("    To push it: freckle backup")
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
