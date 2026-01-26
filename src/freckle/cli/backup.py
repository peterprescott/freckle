"""Backup command for committing and pushing dotfiles changes."""

from typing import List, Optional

import typer

from ..secrets import SecretScanner
from .helpers import env, get_config, get_dotfiles_dir, get_dotfiles_manager


def register(app: typer.Typer) -> None:
    """Register backup command with the app."""
    app.command()(backup)


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
