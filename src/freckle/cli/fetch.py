"""Fetch command for pulling remote dotfiles changes."""

import typer

from .helpers import env, get_config, get_dotfiles_dir, get_dotfiles_manager


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
            "Dotfiles repository not found. Run 'freckle init' first.",
            err=True,
        )
        raise typer.Exit(1)

    report = dotfiles.get_detailed_status()

    # Check for local changes
    if report["has_local_changes"] and not force:
        typer.echo("You have unsaved local changes:")
        for f in report["changed_files"]:
            typer.echo(f"    - {f}")
        typer.echo("\nOptions:")
        typer.echo("  1. Save your changes first: freckle save")
        typer.echo("  2. Discard and fetch anyway: freckle fetch --force")
        raise typer.Exit(1)

    # Check if there's anything to fetch
    if report.get("fetch_failed"):
        typer.echo("⚠ Could not connect to cloud (offline?)")
        typer.echo("  Try again when you have internet access.")
        raise typer.Exit(1)

    if not report.get("is_behind", False):
        typer.echo("✓ Already up-to-date with cloud.")
        return

    behind_count = report.get("behind_count", 0)

    if dry_run:
        typer.echo("\n--- DRY RUN (no changes will be made) ---\n")
        typer.echo(f"Would fetch {behind_count} change(s) from cloud.")
        if report["has_local_changes"]:
            typer.echo("Would discard local changes to:")
            for f in report["changed_files"]:
                typer.echo(f"  - {f}")
        typer.echo("\n--- Dry Run Complete ---")
        return

    typer.echo(f"Fetching {behind_count} change(s) from cloud...")

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
            typer.echo(
                f"  (backed up {len(point.files)} files - "
                "use 'freckle restore --list' to recover)"
            )

    dotfiles.force_checkout()
    typer.echo("✓ Fetched latest from cloud.")
