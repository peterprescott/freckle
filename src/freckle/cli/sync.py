"""Sync command for checking dotfiles status."""

import subprocess
import tempfile
from typing import Any, Dict, Optional, cast

import typer

from ..utils import validate_git_url
from .helpers import env, get_config, get_dotfiles_dir, get_dotfiles_manager


def register(app: typer.Typer) -> None:
    """Register sync command with the app."""
    app.command()(sync)


def _preview_first_sync(repo_url: str, branch: Optional[str]) -> None:
    """Preview what files would be affected by first sync."""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Clone to temp location (shallow for speed)
            subprocess.run(
                ["git", "clone", "--bare", "--depth=1", repo_url, tmpdir],
                capture_output=True,
                check=True,
            )

            # Get file list from remote
            branch_to_use = branch or "main"
            result = subprocess.run(
                ["git", "--git-dir", tmpdir, "ls-tree", "-r",
                 "--name-only", branch_to_use],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                # Try 'master' if 'main' failed
                result = subprocess.run(
                    ["git", "--git-dir", tmpdir, "ls-tree", "-r",
                     "--name-only", "master"],
                    capture_output=True,
                    text=True,
                )

            if result.returncode != 0:
                typer.echo("Could not fetch file list from remote.")
                return

            remote_files = [
                f for f in result.stdout.strip().split("\n") if f
            ]

            if not remote_files:
                typer.echo("No files found in remote repository.")
                return

            # Compare with local
            would_overwrite = []
            would_create = []

            for f in remote_files:
                local_path = env.home / f
                if local_path.exists():
                    would_overwrite.append(f)
                else:
                    would_create.append(f)

            if would_overwrite:
                typer.echo(
                    f"Files that would be OVERWRITTEN "
                    f"({len(would_overwrite)}):"
                )
                typer.echo("  (backups will be created)")
                for f in would_overwrite[:20]:
                    local_path = env.home / f
                    if local_path.is_file():
                        lines = len(local_path.read_text().splitlines())
                        typer.echo(f"  - {f} ({lines} lines)")
                    else:
                        typer.echo(f"  - {f}")
                if len(would_overwrite) > 20:
                    remaining = len(would_overwrite) - 20
                    typer.echo(f"  ... and {remaining} more")
                typer.echo("")

            if would_create:
                typer.echo(
                    f"Files that would be CREATED ({len(would_create)}):"
                )
                for f in would_create[:20]:
                    typer.echo(f"  + {f}")
                if len(would_create) > 20:
                    remaining = len(would_create) - 20
                    typer.echo(f"  ... and {remaining} more")

            typer.echo(
                f"\nTotal: {len(remote_files)} files "
                f"({len(would_overwrite)} overwrite, "
                f"{len(would_create)} create)"
            )

    except subprocess.CalledProcessError:
        typer.echo("Could not preview remote repository.")
        typer.echo("(The repository may require authentication)")
    except Exception as e:
        typer.echo(f"Preview failed: {e}")


def sync(
    repo: Optional[str] = typer.Option(
        None, "--repo", "-r", help="Override dotfiles repository URL"
    ),
    branch: Optional[str] = typer.Option(
        None, "--branch", "-b", help="Override git branch"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Show what would happen without acting"
    ),
    preview: bool = typer.Option(
        False, "--preview", "-p", help="Preview what files would be affected"
    ),
):
    """Check dotfiles sync status.

    Checks the current state of your dotfiles and reports any changes.
    If there are local changes, suggests 'freckle backup'.
    If remote has updates, suggests 'freckle update'.

    On first run, clones your dotfiles repository.
    """
    config = get_config()

    # Override from CLI
    if repo:
        if not validate_git_url(repo):
            typer.echo(f"Invalid repository URL: {repo}", err=True)
            raise typer.Exit(1)
        dotfiles_config = cast(Dict[str, Any], config.data["dotfiles"])
        dotfiles_config["repo_url"] = repo
    if branch:
        dotfiles_config = cast(Dict[str, Any], config.data["dotfiles"])
        dotfiles_config["branch"] = branch

    repo_url = config.get("dotfiles.repo_url")
    if not repo_url:
        typer.echo(
            "No dotfiles repository URL found. Run 'freckle init' first.",
            err=True,
        )
        raise typer.Exit(1)

    dotfiles_dir = get_dotfiles_dir(config)
    branch_name = config.get_branch()

    is_first_run = not dotfiles_dir.exists()
    action_name = "Setup" if is_first_run else "Sync"

    if dry_run:
        typer.echo("\n--- DRY RUN (no changes will be made) ---")

    typer.echo(f"\n--- freckle {action_name} ---")
    typer.echo(f"Platform: {env.os_info['pretty_name']}")

    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo("Failed to initialize dotfiles manager.", err=True)
        raise typer.Exit(1)

    # Treat --preview as --dry-run
    if preview:
        dry_run = True

    try:
        if is_first_run:
            if dry_run:
                typer.echo("\n--- PREVIEW (no changes will be made) ---\n")
                typer.echo(f"Would sync from: {repo_url}")
                typer.echo(f"Would clone to: {dotfiles_dir}\n")

                # Try to show what files would be affected
                _preview_first_sync(repo_url, config.get_branch())
                typer.echo("\n--- Preview Complete ---\n")
                return
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
                    ahead = report.get("ahead_count", 0)
                    typer.echo(
                        f"\n  (Local is {ahead} commit(s) ahead of remote)"
                    )

                typer.echo("\nTo backup these changes, run: freckle backup")
            elif not local_changes and is_behind:
                behind_count = report.get("behind_count", 0)
                typer.echo(
                    f"↓ Remote ({branch_name}) has "
                    f"{behind_count} new commit(s)."
                )
                typer.echo("\nTo update your local files, run: freckle update")
            elif local_changes and is_behind:
                typer.echo(
                    "‼ CONFLICT: You have local changes "
                    "AND remote has new commits."
                )
                typer.echo(f"  Local Commit : {report['local_commit']}")
                typer.echo(f"  Remote Commit: {report['remote_commit']}")
                typer.echo(
                    f"  Behind by: {report.get('behind_count', 0)} commit(s)"
                )

                typer.echo("\nLocal changes:")
                for f in report["changed_files"]:
                    typer.echo(f"    - {f}")

                typer.echo("\nOptions to resolve conflict:")
                typer.echo(
                    "  - To keep local changes and backup: freckle backup"
                )
                typer.echo(
                    "  - To discard local and update: "
                    "freckle update --force"
                )
            elif is_ahead and not local_changes:
                ahead_count = report.get("ahead_count", 0)
                typer.echo(
                    f"↑ Local is {ahead_count} commit(s) ahead of remote."
                )
                typer.echo("\nTo push, run: freckle backup")
            elif report.get("remote_branch_missing") and not local_changes:
                typer.echo("↑ Local branch has no remote counterpart.")
                typer.echo("\nTo push, run: freckle backup")

        typer.echo(f"\n--- {action_name} Complete! ---\n")

    except Exception as e:
        from .helpers import logger

        logger.error(f"Freckle failed: {e}")
        raise typer.Exit(1)
