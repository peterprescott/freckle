"""Update command for pulling remote dotfiles changes."""

import typer

from .helpers import env, get_config, get_dotfiles_dir, get_dotfiles_manager


def register(app: typer.Typer) -> None:
    """Register update command with the app."""
    app.command()(update)


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
