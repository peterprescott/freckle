"""Sync, backup, and update commands for freckle CLI."""

import subprocess
import tempfile
from typing import Any, Dict, List, Optional, cast

import typer

from ..utils import validate_git_url
from .helpers import env, get_config, get_dotfiles_dir, get_dotfiles_manager


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
                    typer.echo(f"  ... and {len(would_overwrite) - 20} more")
                typer.echo("")

            if would_create:
                typer.echo(f"Files that would be CREATED ({len(would_create)}):")  # noqa: E501
                for f in would_create[:20]:
                    typer.echo(f"  + {f}")
                if len(would_create) > 20:
                    typer.echo(f"  ... and {len(would_create) - 20} more")

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


def register(app: typer.Typer) -> None:
    """Register sync commands with the app."""
    app.command()(sync)
    app.command()(backup)
    app.command()(update)


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


def _build_commit_message(
    prefix: str, changed_files: List[str], platform: str
) -> str:
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
    dry_run: bool = False,
    skip_secret_check: bool = False,
) -> bool:
    """Internal backup logic. Returns True on success."""
    from freckle.secrets import SecretScanner

    config = get_config()

    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        if not quiet:
            typer.echo(
                "No dotfiles repository configured. Run 'freckle init' first.",
                err=True,
            )
        return False

    dotfiles_dir = get_dotfiles_dir(config)

    if not dotfiles_dir.exists():
        if not quiet:
            typer.echo(
                "Dotfiles repository not found. Run 'freckle sync' first.",
                err=True,
            )
        return False

    report = dotfiles.get_detailed_status()

    if not report["has_local_changes"] and not report.get("is_ahead", False):
        if not quiet:
            typer.echo("✓ Nothing to backup - already up-to-date.")
        return True

    changed_files = report.get("changed_files", [])

    # Check for secrets in changed files
    if changed_files and not skip_secret_check:
        secrets_config = config.get("secrets", {})
        scanner = SecretScanner(
            extra_block=secrets_config.get("block", []),
            extra_allow=secrets_config.get("allow", []),
        )
        secrets_found = scanner.scan_files(changed_files, env.home)

        if secrets_found:
            if not quiet:
                typer.echo(
                    f"✗ Refusing to commit. Found potential secrets "
                    f"in {len(secrets_found)} file(s):\n",
                    err=True,
                )
                for match in secrets_found:
                    typer.echo(f"  {match.file}", err=True)
                    typer.echo(f"    └─ {match.reason}", err=True)
                    if match.line:
                        typer.echo(f"       (line {match.line})", err=True)

                typer.echo(
                    "\nRemove these files with: "
                    "freckle remove <file> [file2] ...",
                    err=True,
                )
                typer.echo(
                    "Or to backup anyway: freckle backup --skip-secret-check",
                    err=True,
                )
            return False

    # Dry run - show what would happen
    if dry_run:
        typer.echo("\n--- DRY RUN (no changes will be made) ---\n")
        if report["has_local_changes"]:
            typer.echo("Would commit the following files:")
            for f in changed_files:
                typer.echo(f"  - {f}")
        if report.get("is_ahead", False):
            ahead = report.get("ahead_count", 0)
            typer.echo(f"\nWould push {ahead} commit(s) to remote.")
        elif report["has_local_changes"] and not no_push:
            typer.echo("\nWould push 1 new commit to remote.")
        if no_push:
            typer.echo("\n(--no-push: would not push to remote)")
        typer.echo("\n--- Dry Run Complete ---")
        return True

    if report["has_local_changes"] and not quiet:
        typer.echo("Backing up changed file(s):")
        for f in changed_files:
            typer.echo(f"  - {f}")

    if report.get("is_ahead", False) and not quiet:
        typer.echo(
            f"Pushing {report.get('ahead_count', 0)} unpushed commit(s)..."
        )

    # Build commit message
    if message:
        commit_msg = message
    else:
        prefix = "Scheduled backup" if scheduled else "Backup"
        commit_msg = _build_commit_message(
            prefix, changed_files, env.os_info["pretty_name"]
        )

    if report["has_local_changes"]:
        if no_push:
            # Commit only - use git directly
            try:
                dotfiles._git.run("add", "-A")
                dotfiles._git.run("commit", "-m", commit_msg)
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
            typer.echo(
                f"⚠ Committed locally but push failed: {result['error']}"
            )
        return True  # Partial success
    else:
        if not quiet:
            typer.echo(
                f"✗ Backup failed: {result.get('error', 'Unknown error')}",
                err=True,
            )
        return False


def backup(
    message: Optional[str] = typer.Option(
        None, "-m", "--message", help="Custom commit message"
    ),
    no_push: bool = typer.Option(
        False, "--no-push", help="Commit locally but don't push"
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress output (for scripts/cron)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Show what would happen without acting"
    ),
    skip_secret_check: bool = typer.Option(
        False,
        "--skip-secret-check",
        help="Backup even if secrets are detected (not recommended)",
    ),
    scheduled: bool = typer.Option(
        False, "--scheduled", hidden=True, help="Mark as scheduled backup"
    ),
):
    """Commit and push local changes to remote.

    Commits any uncommitted changes in your dotfiles and pushes them
    to the remote repository. The commit message includes a list of
    changed files for easy reference.
    """
    success = do_backup(
        message=message,
        skip_secret_check=skip_secret_check,
        no_push=no_push,
        quiet=quiet,
        scheduled=scheduled,
        dry_run=dry_run,
    )
    if not success:
        raise typer.Exit(1)


def update(
    force: bool = typer.Option(
        False, "--force", "-f", help="Discard local changes and update"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Show what would happen without acting"
    ),
):
    """Pull and apply remote changes.

    Updates your local dotfiles to match the remote repository.
    If you have local changes, use --force to discard them.
    """
    config = get_config()

    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo(
            "No dotfiles repository configured. Run 'freckle init' first.",
            err=True,
        )
        raise typer.Exit(1)

    dotfiles_dir = get_dotfiles_dir(config)

    if not dotfiles_dir.exists():
        typer.echo(
            "Dotfiles repository not found. Run 'freckle sync' first.",
            err=True,
        )
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

    behind_count = report.get("behind_count", 0)

    if dry_run:
        typer.echo("\n--- DRY RUN (no changes will be made) ---\n")
        typer.echo(f"Would pull {behind_count} commit(s) from remote.")
        if report["has_local_changes"]:
            typer.echo("Would discard local changes to:")
            for f in report["changed_files"]:
                typer.echo(f"  - {f}")
        typer.echo("\n--- Dry Run Complete ---")
        return

    typer.echo(f"Fetching {behind_count} new commit(s) from remote...")

    # Backup local files before overwriting
    if report["has_local_changes"]:
        from freckle.backup import BackupManager

        backup_manager = BackupManager()
        point = backup_manager.create_restore_point(
            files=report["changed_files"],
            reason="pre-update",
            home=env.home,
        )
        if point:
            typer.echo(
                f"  (backed up {len(point.files)} files - "
                "use 'freckle restore --list' to recover)"
            )

    dotfiles.force_checkout()
    typer.echo("✓ Updated to latest remote version.")
