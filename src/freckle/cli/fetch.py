"""Fetch command for pulling remote dotfiles changes."""

import typer

from .helpers import env, get_config, require_dotfiles_ready
from .output import muted, plain, success, warning


def register(app: typer.Typer) -> None:
    """Register fetch command with the app."""
    app.command()(fetch)


def fetch(
    force: bool = typer.Option(
        False, "--force", "-f", help="Discard local changes and fetch"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Show what would happen without acting"
    ),
):
    """Fetch and apply changes from the cloud.

    Gets the latest dotfiles from your remote repository and applies them
    locally. If you have unsaved local changes, you'll be prompted to
    save them first or use --force to discard them.

    Examples:
        freckle fetch           # Get latest changes
        freckle fetch --force   # Discard local changes and fetch
    """
    config = get_config()
    dotfiles, _ = require_dotfiles_ready(config)

    report = dotfiles.get_detailed_status()

    # Check for local changes
    if report["has_local_changes"] and not force:
        warning("You have unsaved local changes:")
        for f in report["changed_files"]:
            muted(f"    - {f}")
        plain("\nOptions:")
        plain("  1. Save your changes first: freckle save")
        plain("  2. Discard and fetch anyway: freckle fetch --force")
        raise typer.Exit(1)

    # Check if there's anything to fetch
    if report.get("fetch_failed"):
        warning("Could not connect to cloud (offline?)")
        muted("  Try again when you have internet access.")
        raise typer.Exit(1)

    if not report.get("is_behind", False):
        success("Already up-to-date with cloud.")
        return

    behind_count = report.get("behind_count", 0)

    if dry_run:
        plain("\n--- DRY RUN (no changes will be made) ---\n")
        plain(f"Would fetch {behind_count} change(s) from cloud.")
        if report["has_local_changes"]:
            plain("Would discard local changes to:")
            for f in report["changed_files"]:
                muted(f"  - {f}")
        plain("\n--- Dry Run Complete ---")
        return

    plain(f"Fetching {behind_count} change(s) from cloud...")

    # Backup local files before overwriting (safety net)
    if report["has_local_changes"]:
        from freckle.backup import BackupManager

        backup_manager = BackupManager()
        point = backup_manager.create_restore_point(
            files=report["changed_files"],
            reason="pre-fetch",
            home=env.home,
        )
        if point:
            muted(
                f"  (backed up {len(point.files)} files - "
                "use 'freckle restore --list' to recover)"
            )

    dotfiles.force_checkout()
    success("Fetched latest from cloud.")
