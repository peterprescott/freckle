"""Sync, backup, and update commands for freckle CLI."""

from pathlib import Path
from typing import List, Optional

import typer

from ..utils import setup_logging, validate_git_url
from .helpers import env, get_config, get_dotfiles_manager, get_dotfiles_dir


def register(app: typer.Typer) -> None:
    """Register sync commands with the app."""
    app.command()(sync)
    app.command()(backup)
    app.command()(update)


def sync(
    repo: Optional[str] = typer.Option(None, "--repo", "-r", help="Override dotfiles repository URL"),
    branch: Optional[str] = typer.Option(None, "--branch", "-b", help="Override git branch"),
):
    """Check dotfiles sync status.
    
    Checks the current state of your dotfiles and reports any changes.
    If there are local changes, suggests 'freckle backup'.
    If remote has updates, suggests 'freckle update'.
    
    On first run, clones your dotfiles repository.
    """
    setup_logging()
    config = get_config()
    
    # Override from CLI
    if repo:
        if not validate_git_url(repo):
            typer.echo(f"Invalid repository URL: {repo}", err=True)
            raise typer.Exit(1)
        config.data["dotfiles"]["repo_url"] = repo
    if branch:
        config.data["dotfiles"]["branch"] = branch

    repo_url = config.get("dotfiles.repo_url")
    if not repo_url:
        typer.echo("No dotfiles repository URL found. Run 'freckle init' first.", err=True)
        raise typer.Exit(1)

    dotfiles_dir = get_dotfiles_dir(config)
    branch_name = config.get("dotfiles.branch")

    is_first_run = not dotfiles_dir.exists()
    action_name = "Setup" if is_first_run else "Sync"
    
    typer.echo(f"\n--- freckle {action_name} ---")
    typer.echo(f"Platform: {env.os_info['pretty_name']}")
    
    dotfiles = get_dotfiles_manager(config)

    try:
        if is_first_run:
            typer.echo(f"[*] Initial setup of dotfiles from {repo_url}...")
            dotfiles.setup()
        else:
            report = dotfiles.get_detailed_status()
            
            if report.get("fetch_failed"):
                typer.echo("⚠ Could not connect to remote (offline mode)")
            
            local_changes = report["has_local_changes"]
            is_behind = report.get("is_behind", False)
            is_ahead = report.get("is_ahead", False)

            if not local_changes and not is_behind and not is_ahead:
                typer.echo("✓ Dotfiles are up-to-date.")
            elif local_changes and not is_behind:
                typer.echo("⚠ You have local changes that are not backed up:")
                for f in report["changed_files"]:
                    typer.echo(f"    - {f}")
                
                if is_ahead:
                    typer.echo(f"\n  (Local is {report.get('ahead_count', 0)} commit(s) ahead of remote)")
                
                typer.echo("\nTo backup these changes, run: freckle backup")
            elif not local_changes and is_behind:
                behind_count = report.get('behind_count', 0)
                typer.echo(f"↓ Remote repository ({branch_name}) has {behind_count} new commit(s).")
                typer.echo("\nTo update your local files, run: freckle update")
            elif local_changes and is_behind:
                typer.echo("‼ CONFLICT: You have local changes AND remote has new commits.")
                typer.echo(f"  Local Commit : {report['local_commit']}")
                typer.echo(f"  Remote Commit: {report['remote_commit']}")
                typer.echo(f"  Behind by: {report.get('behind_count', 0)} commit(s)")
                
                typer.echo("\nLocal changes:")
                for f in report["changed_files"]:
                    typer.echo(f"    - {f}")
                    
                typer.echo("\nOptions to resolve conflict:")
                typer.echo("  - To keep local changes and backup: freckle backup")
                typer.echo("  - To discard local changes and update: freckle update --force")
            elif is_ahead and not local_changes:
                ahead_count = report.get('ahead_count', 0)
                typer.echo(f"↑ Local is {ahead_count} commit(s) ahead of remote.")
                typer.echo("\nTo push, run: freckle backup")
            elif report.get("remote_branch_missing") and not local_changes:
                typer.echo("↑ Local branch has no remote counterpart.")
                typer.echo("\nTo push, run: freckle backup")
        
        typer.echo(f"\n--- {action_name} Complete! ---\n")
        
    except Exception as e:
        from .helpers import logger
        logger.error(f"Freckle failed: {e}")
        raise typer.Exit(1)


def _build_commit_message(prefix: str, changed_files: List[str], platform: str) -> str:
    """Build a descriptive commit message including changed files."""
    lines = [f"{prefix} from {platform}"]
    
    if changed_files:
        lines.append("")
        lines.append("Changed files:")
        for f in changed_files:
            lines.append(f"  - {f}")
    
    return "\n".join(lines)


def do_backup(
    message: Optional[str] = None,
    no_push: bool = False,
    quiet: bool = False,
    scheduled: bool = False,
) -> bool:
    """Internal backup logic. Returns True on success."""
    config = get_config()
    
    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        if not quiet:
            typer.echo("No dotfiles repository configured. Run 'freckle init' first.", err=True)
        return False
    
    dotfiles_dir = get_dotfiles_dir(config)
    
    if not dotfiles_dir.exists():
        if not quiet:
            typer.echo("Dotfiles repository not found. Run 'freckle sync' first.", err=True)
        return False
    
    report = dotfiles.get_detailed_status()
    
    if not report["has_local_changes"] and not report.get("is_ahead", False):
        if not quiet:
            typer.echo("✓ Nothing to backup - already up-to-date.")
        return True
    
    changed_files = report.get("changed_files", [])
    
    if report["has_local_changes"] and not quiet:
        typer.echo("Backing up changed file(s):")
        for f in changed_files:
            typer.echo(f"  - {f}")
    
    if report.get("is_ahead", False) and not quiet:
        typer.echo(f"Pushing {report.get('ahead_count', 0)} unpushed commit(s)...")
    
    # Build commit message
    if message:
        commit_msg = message
    else:
        prefix = "Scheduled backup" if scheduled else "Backup"
        commit_msg = _build_commit_message(prefix, changed_files, env.os_info['pretty_name'])
    
    if report["has_local_changes"]:
        if no_push:
            # Commit only - use git directly
            try:
                dotfiles._git("add", "-A")
                dotfiles._git("commit", "-m", commit_msg)
                result = {"success": True, "committed": True, "pushed": False}
            except Exception as e:
                result = {"success": False, "error": str(e)}
        else:
            result = dotfiles.commit_and_push(commit_msg)
    else:
        # Just push existing commits
        result = dotfiles.push() if not no_push else {"success": True}
    
    if result["success"]:
        if not quiet:
            if no_push:
                typer.echo("✓ Changes committed locally.")
            else:
                typer.echo("✓ Backed up successfully.")
        return True
    elif result.get("committed") and not result.get("pushed"):
        if not quiet:
            typer.echo(f"⚠ Committed locally but push failed: {result['error']}")
        return True  # Partial success
    else:
        if not quiet:
            typer.echo(f"✗ Backup failed: {result.get('error', 'Unknown error')}", err=True)
        return False


def backup(
    message: Optional[str] = typer.Option(None, "-m", "--message", help="Custom commit message"),
    no_push: bool = typer.Option(False, "--no-push", help="Commit locally but don't push"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress output (for scripts/cron)"),
    scheduled: bool = typer.Option(False, "--scheduled", hidden=True, help="Mark as scheduled backup"),
):
    """Commit and push local changes to remote.
    
    Commits any uncommitted changes in your dotfiles and pushes them
    to the remote repository. The commit message includes a list of
    changed files for easy reference.
    """
    setup_logging()
    success = do_backup(message=message, no_push=no_push, quiet=quiet, scheduled=scheduled)
    if not success:
        raise typer.Exit(1)


def update(
    force: bool = typer.Option(False, "--force", "-f", help="Discard local changes and update"),
):
    """Pull and apply remote changes.
    
    Updates your local dotfiles to match the remote repository.
    If you have local changes, use --force to discard them.
    """
    setup_logging()
    config = get_config()
    
    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo("No dotfiles repository configured. Run 'freckle init' first.", err=True)
        raise typer.Exit(1)
    
    dotfiles_dir = get_dotfiles_dir(config)
    
    if not dotfiles_dir.exists():
        typer.echo("Dotfiles repository not found. Run 'freckle sync' first.", err=True)
        raise typer.Exit(1)
    
    report = dotfiles.get_detailed_status()
    
    if report["has_local_changes"] and not force:
        typer.echo("⚠ You have local changes:")
        for f in report["changed_files"]:
            typer.echo(f"    - {f}")
        typer.echo("\nUse --force to discard these changes and update.")
        raise typer.Exit(1)
    
    if not report.get("is_behind", False):
        typer.echo("✓ Already up-to-date with remote.")
        return
    
    behind_count = report.get('behind_count', 0)
    typer.echo(f"Fetching {behind_count} new commit(s) from remote...")
    
    dotfiles.force_checkout()
    typer.echo("✓ Updated to latest remote version.")
