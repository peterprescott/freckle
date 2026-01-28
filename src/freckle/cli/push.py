"""Push command for pushing all local branches to remote."""

import subprocess
from typing import List

import typer

from .helpers import get_config, get_dotfiles_dir, get_dotfiles_manager
from .output import error, muted, plain, success, warning


def register(app: typer.Typer) -> None:
    """Register push command with the app."""
    app.command()(push)


def _get_local_branches(dotfiles) -> List[str]:
    """Get all local branches in the dotfiles repo."""
    try:
        result = dotfiles._git.run("branch", "--list")
        branches = [
            b.strip().lstrip("* ")
            for b in result.stdout.split("\n")
            if b.strip()
        ]
        return branches
    except subprocess.CalledProcessError:
        return []


def push(
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Show what would happen without acting"
    ),
):
    """Push all local branches to the remote repository.

    This pushes ALL local branches to origin, ensuring your dotfiles
    are synced across all machines for all profiles.

    Note: 'freckle save' commits locally but does not push.
    Use 'freckle push' after saving to sync to the cloud.

    Examples:
        freckle push           # Push all branches to remote
        freckle push --dry-run # Show what would be pushed
    """
    config = get_config()

    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        error("No dotfiles configured. Run 'freckle init' first.")
        raise typer.Exit(1)

    dotfiles_dir = get_dotfiles_dir(config)
    if not dotfiles_dir.exists():
        error("Dotfiles repository not found. Run 'freckle init' first.")
        raise typer.Exit(1)

    branches = _get_local_branches(dotfiles)

    if not branches:
        warning("No local branches found.")
        raise typer.Exit(1)

    if dry_run:
        plain("\n--- DRY RUN (no changes will be made) ---\n")
        plain(f"Would push {len(branches)} branch(es) to remote:")
        for branch in branches:
            muted(f"  - {branch}")
        plain("\n--- Dry Run Complete ---")
        return

    plain(f"Pushing {len(branches)} branch(es) to remote...")

    pushed = []
    failed = []

    for branch in branches:
        try:
            dotfiles._git.run_bare(
                "push", "origin", branch, check=True, timeout=60
            )
            pushed.append(branch)
            success(branch, prefix="  ✓")
        except subprocess.CalledProcessError:
            failed.append(branch)
            error(branch, prefix="  ✗")

    if pushed:
        success(f"Pushed {len(pushed)} branch(es)")

    if failed:
        warning(f"Failed to push {len(failed)} branch(es)")
        muted("  Check network connection or remote permissions")
        raise typer.Exit(1)
